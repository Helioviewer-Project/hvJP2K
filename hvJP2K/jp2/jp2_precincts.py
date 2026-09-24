"""Pure-Python replacement for the part of ``kdu_transcode`` that hvJP2K uses.

``kdu_transcode Corder=RPCL ORGgen_plt=yes Cprecincts={128,128}`` rewrites a
codestream without touching the entropy-coded data: every code-block keeps
its coding passes, bytes and zero bit-planes, and only the Tier-2 layer
changes.  The code-blocks are regrouped into the requested precincts, a new
packet header is written for every (resolution, precinct, component, layer)
in RPCL order, and the packet lengths are recorded in a PLT marker.

That is possible as long as the new precincts leave the code-block
partition unchanged: precincts smaller than the code-blocks clip them, and
the blocks of one partition must be the blocks of the other.

Supported input: one tile (any number of tile-parts), any progression order,
no COC, RGN, POC, PPM or PPT markers, no coding parameters in tile-part
headers, and code-block styles without selective arithmetic coding bypass or
termination on each coding pass.  SOP/EPH markers in the input are skipped
and not written.
"""

import struct

_SOC, _SIZ, _COD, _COC, _RGN, _POC = 0xFF4F, 0xFF51, 0xFF52, 0xFF53, 0xFF5E, 0xFF5F
_TLM, _PLM, _PLT, _PPM, _COM = 0xFF55, 0xFF57, 0xFF58, 0xFF60, 0xFF64
_SOT, _SOD, _EOC = 0xFF90, 0xFF93, 0xFFD9

_ORDERS = {"LRCP": 0, "RLCP": 1, "RPCL": 2, "PCRL": 3, "CPRL": 4}


def _ceildiv(a, b):
    return -(-a // b)


# ----------------------------------------------------------------------------
# Bit I/O with JPEG 2000 packet-header bit stuffing


class _BitReader:
    __slots__ = ("data", "pos", "buf", "ct")

    def __init__(self, data, pos):
        self.data = data
        self.pos = pos
        self.buf = 0
        self.ct = 0

    def bit(self):
        if self.ct == 0:
            # After 0xFF the next byte carries only 7 bits.
            self.ct = 7 if self.buf == 0xFF else 8
            self.buf = self.data[self.pos]
            self.pos += 1
        self.ct -= 1
        return (self.buf >> self.ct) & 1

    def bits(self, n):
        v = 0
        for _ in range(n):
            v = (v << 1) | self.bit()
        return v

    def align(self):
        """End of packet header: skip the stuffed byte after a final 0xFF."""
        if self.buf == 0xFF:
            self.pos += 1
        self.ct = 0
        self.buf = 0
        return self.pos


class _BitWriter:
    __slots__ = ("out", "cur", "n", "cap")

    def __init__(self):
        self.out = bytearray()
        self.cur = 0
        self.n = 0
        self.cap = 8

    def bit(self, b):
        self.cur = (self.cur << 1) | b
        self.n += 1
        if self.n == self.cap:
            self.out.append(self.cur)
            self.cap = 7 if self.cur == 0xFF else 8
            self.cur = 0
            self.n = 0

    def bits(self, v, n):
        for i in range(n - 1, -1, -1):
            self.bit((v >> i) & 1)

    def flush(self):
        if self.n:
            self.out.append(self.cur << (self.cap - self.n))
        # A packet header must not end with 0xFF.
        if self.out and self.out[-1] == 0xFF:
            self.out.append(0)
        return bytes(self.out)


# ----------------------------------------------------------------------------
# Tag trees (B.10.2)


class _TagTree:
    __slots__ = ("parent", "value", "low", "known", "leaves")

    def __init__(self, w, h, values=None):
        start = 0
        levels = []
        while True:
            levels.append((w, h))
            if w * h == 1:
                break
            w, h = _ceildiv(w, 2), _ceildiv(h, 2)
        offsets = []
        for w, h in levels:
            offsets.append(start)
            start += w * h
        parent = [-1] * start
        for k in range(len(levels) - 1):
            w, h = levels[k]
            pw = levels[k + 1][0]
            for y in range(h):
                for x in range(w):
                    parent[offsets[k] + y * w + x] = (
                        offsets[k + 1] + (y >> 1) * pw + (x >> 1)
                    )
        self.parent = parent
        self.leaves = levels[0][0] * levels[0][1]
        self.low = [0] * start
        self.known = [False] * start
        if values is None:
            self.value = [1 << 30] * start
        else:
            v = list(values) + [0] * (start - len(values))
            for k in range(self.leaves, start):
                v[k] = 1 << 30
            for k in range(start):
                p = parent[k]
                if p >= 0 and v[k] < v[p]:
                    v[p] = v[k]
            self.value = v

    def _path(self, leaf):
        path = []
        n = leaf
        while n >= 0:
            path.append(n)
            n = self.parent[n]
        path.reverse()
        return path

    def decode(self, rd, leaf, threshold):
        low = 0
        value, lows = self.value, self.low
        for n in self._path(leaf):
            if low > lows[n]:
                lows[n] = low
            else:
                low = lows[n]
            while low < threshold and low < value[n]:
                if rd.bit():
                    value[n] = low
                else:
                    low += 1
            lows[n] = low
        return value[leaf] < threshold

    def encode(self, wr, leaf, threshold):
        low = 0
        value, lows, known = self.value, self.low, self.known
        for n in self._path(leaf):
            if low > lows[n]:
                lows[n] = low
            else:
                low = lows[n]
            while low < threshold:
                if low >= value[n]:
                    if not known[n]:
                        wr.bit(1)
                        known[n] = True
                    break
                wr.bit(0)
                low += 1
            lows[n] = low


# ----------------------------------------------------------------------------
# Coding-pass count code words (Table B.4) and Lblock


def _read_npasses(rd):
    if not rd.bit():
        return 1
    if not rd.bit():
        return 2
    n = rd.bits(2)
    if n != 3:
        return 3 + n
    n = rd.bits(5)
    if n != 31:
        return 6 + n
    return 37 + rd.bits(7)


def _write_npasses(wr, n):
    if n == 1:
        wr.bit(0)
    elif n == 2:
        wr.bits(0b10, 2)
    elif n <= 5:
        wr.bits(0b1100 | (n - 3), 4)
    elif n <= 36:
        wr.bits(0b111100000 | (n - 6), 9)
    elif n <= 164:
        wr.bits((0b111111111 << 7) | (n - 37), 16)
    else:
        raise ValueError("too many coding passes: {0}".format(n))


def _floorlog2(n):
    return n.bit_length() - 1


# ----------------------------------------------------------------------------
# Codestream parsing


class _Codestream:
    def __init__(self, cs):
        if struct.unpack(">H", cs[:2])[0] != _SOC:
            raise ValueError("not a JPEG 2000 codestream")
        self.main = []  # (marker, body) in file order, SOC excluded
        self.cod = None
        pos = 2
        while True:
            m = struct.unpack(">H", cs[pos : pos + 2])[0]
            if m == _SOT:
                break
            L = struct.unpack(">H", cs[pos + 2 : pos + 4])[0]
            body = cs[pos + 4 : pos + 2 + L]
            if m in (_COC, _POC, _PPM, _RGN):
                raise ValueError("unsupported main header marker 0x{0:04X}".format(m))
            if m == _COD:
                self.cod = body
            if m == _SIZ:
                self._siz(body)
            self.main.append((m, body))
            pos += 2 + L
        if self.cod is None:
            raise ValueError("no COD marker")
        self._parse_cod(self.cod)

        tiles = _ceildiv(self.X - self.XTO, self.XT) * _ceildiv(
            self.Y - self.YTO, self.YT
        )
        if tiles != 1:
            raise ValueError("only single-tile codestreams are supported")

        body = bytearray()
        while True:
            m = struct.unpack(">H", cs[pos : pos + 2])[0]
            if m == _EOC:
                break
            if m != _SOT:
                raise ValueError("expected SOT at offset {0}".format(pos))
            psot = struct.unpack(">I", cs[pos + 6 : pos + 10])[0]
            end = pos + psot if psot else len(cs) - 2
            p = pos + 12
            while True:
                mm = struct.unpack(">H", cs[p : p + 2])[0]
                if mm == _SOD:
                    p += 2
                    break
                LL = struct.unpack(">H", cs[p + 2 : p + 4])[0]
                if mm not in (_PLT, _COM):
                    raise ValueError(
                        "unsupported tile-part marker 0x{0:04X}".format(mm)
                    )
                p += 2 + LL
            body += cs[p:end]
            pos = end
        self.body = bytes(body)

    def _siz(self, b):
        _, self.X, self.Y, self.XO, self.YO, self.XT, self.YT, self.XTO, self.YTO, C = (
            struct.unpack(">HIIIIIIIIH", b[:36])
        )
        self.comps = [(b[36 + 3 * i + 1], b[36 + 3 * i + 2]) for i in range(C)]

    def _parse_cod(self, b):
        self.scod = b[0]
        self.order, self.layers, self.mct = struct.unpack(">BHB", b[1:5])
        self.levels, cbw, cbh, self.cbstyle, self.xform = b[5:10]
        self.cbw, self.cbh = cbw + 2, cbh + 2
        if self.scod & 1:
            pp = b[10 : 10 + self.levels + 1]
            self.precincts = [(v & 15, v >> 4) for v in pp]
        else:
            self.precincts = [(15, 15)] * (self.levels + 1)
        if self.cbstyle & 0x05:
            raise ValueError(
                "code-block styles with bypass or termall are not supported"
            )


# ----------------------------------------------------------------------------
# Geometry


class _Precinct:
    __slots__ = ("c", "r", "px", "py", "ax", "ay", "bands")

    def __init__(self, c, r, px, py, ax, ay):
        self.c, self.r, self.px, self.py, self.ax, self.ay = c, r, px, py, ax, ay
        self.bands = []  # (grid_w, grid_h, [cblk ids in raster order])


def _geometry(cs, precincts):
    """Precincts per (component, resolution) for the given precinct exponents.

    Code-blocks are identified by (component, resolution, band, x, y, width
    and height exponents) so that both partitions of the same codestream
    refer to the same blocks."""
    tx0, ty0 = max(cs.XTO, cs.XO), max(cs.YTO, cs.YO)
    tx1, ty1 = min(cs.XTO + cs.XT, cs.X), min(cs.YTO + cs.YT, cs.Y)
    NL = cs.levels
    out = {}
    for c, (xr, yr) in enumerate(cs.comps):
        cx0, cy0, cx1, cy1 = (
            _ceildiv(tx0, xr),
            _ceildiv(ty0, yr),
            _ceildiv(tx1, xr),
            _ceildiv(ty1, yr),
        )
        for r in range(NL + 1):
            PPx, PPy = precincts[r]
            s = 1 << (NL - r)
            rx0, ry0, rx1, ry1 = (
                _ceildiv(cx0, s),
                _ceildiv(cy0, s),
                _ceildiv(cx1, s),
                _ceildiv(cy1, s),
            )
            if r == 0:
                bands = [(0, 0, 0, NL)]
                bPPx, bPPy = PPx, PPy
            else:
                bands = [
                    (1, 1, 0, NL - r + 1),
                    (2, 0, 1, NL - r + 1),
                    (3, 1, 1, NL - r + 1),
                ]
                bPPx, bPPy = PPx - 1, PPy - 1
            # Precincts smaller than the code-blocks clip them.
            xcb, ycb = min(cs.cbw, bPPx), min(cs.cbh, bPPy)
            bgeom = []
            for b, xo, yo, nb in bands:
                o = 1 << (nb - 1) if r else 0
                bx0 = _ceildiv(cx0 - o * xo, 1 << nb)
                by0 = _ceildiv(cy0 - o * yo, 1 << nb)
                bx1 = _ceildiv(cx1 - o * xo, 1 << nb)
                by1 = _ceildiv(cy1 - o * yo, 1 << nb)
                bgeom.append((b, bx0, by0, bx1, by1))
            if rx1 > rx0 and ry1 > ry0:
                npx0, npy0 = rx0 >> PPx, ry0 >> PPy
                npx1, npy1 = _ceildiv(rx1, 1 << PPx), _ceildiv(ry1, 1 << PPy)
            else:
                npx0 = npy0 = npx1 = npy1 = 0
            plist = []
            for py in range(npy0, npy1):
                for px in range(npx0, npx1):
                    ax = max(tx0, (px << PPx) * xr * s)
                    ay = max(ty0, (py << PPy) * yr * s)
                    prc = _Precinct(c, r, px, py, ax, ay)
                    for b, bx0, by0, bx1, by1 in bgeom:
                        # precinct region in band coordinates
                        qx0 = max(bx0, px << bPPx)
                        qy0 = max(by0, py << bPPy)
                        qx1 = min(bx1, (px + 1) << bPPx)
                        qy1 = min(by1, (py + 1) << bPPy)
                        if qx1 <= qx0 or qy1 <= qy0:
                            prc.bands.append((0, 0, []))
                            continue
                        cbx0, cby0 = qx0 >> xcb, qy0 >> ycb
                        cbx1, cby1 = _ceildiv(qx1, 1 << xcb), _ceildiv(qy1, 1 << ycb)
                        ids = []
                        for cy in range(cby0, cby1):
                            for cx in range(cbx0, cbx1):
                                ids.append((c, r, b, cx, cy, xcb, ycb))
                        prc.bands.append((cbx1 - cbx0, cby1 - cby0, ids))
                    plist.append(prc)
            out[(c, r)] = plist
    return out


def _packet_order(cs, geom, order):
    """(precinct, layer) pairs in progression order (B.12)."""
    L = cs.layers
    seq = []
    if order in (0, 1):
        for key in sorted(geom):
            c, r = key
            for i, prc in enumerate(geom[key]):
                for l in range(L):
                    k = (l, r, c, i) if order == 0 else (r, l, c, i)
                    seq.append((k, prc, l))
    else:
        for key in sorted(geom):
            c, r = key
            for i, prc in enumerate(geom[key]):
                for l in range(L):
                    if order == 2:
                        k = (r, prc.ay, prc.ax, c, l)
                    elif order == 3:
                        k = (prc.ay, prc.ax, c, r, l)
                    else:
                        k = (c, prc.ay, prc.ax, r, l)
                    seq.append((k, prc, l))
    seq.sort(key=lambda t: t[0])
    return [(prc, l) for _, prc, l in seq]


# ----------------------------------------------------------------------------
# Tier-2 decode / encode


class _Block:
    __slots__ = ("zbp", "lblock", "incl", "layers")

    def __init__(self, nlayers):
        self.zbp = None
        self.lblock = 3
        self.incl = None  # first layer with a contribution
        self.layers = [None] * nlayers  # (npasses, bytes) or None


def _read_packets(cs, blocks):
    geom = _geometry(cs, cs.precincts)
    for plist in geom.values():
        for prc in plist:
            for _, _, ids in prc.bands:
                for key in ids:
                    blocks[key] = _Block(cs.layers)
    trees = {}
    data = cs.body
    pos = 0
    sop, eph = cs.scod & 2, cs.scod & 4
    for prc, l in _packet_order(cs, geom, cs.order):
        if sop and data[pos : pos + 2] == b"\xff\x91":
            pos += 6
        t = trees.get(id(prc))
        if t is None:
            t = [
                (_TagTree(w, h), _TagTree(w, h)) if ids else None
                for w, h, ids in prc.bands
            ]
            trees[id(prc)] = t
        rd = _BitReader(data, pos)
        contrib = []
        if rd.bit():
            for (w, h, ids), tt in zip(prc.bands, t):
                if not ids:
                    continue
                inclt, zbpt = tt
                for leaf, key in enumerate(ids):
                    blk = blocks[key]
                    if blk.incl is None:
                        if not inclt.decode(rd, leaf, l + 1):
                            continue
                        i = 0
                        while not zbpt.decode(rd, leaf, i):
                            i += 1
                        blk.zbp = i - 1
                        blk.incl = l
                    elif not rd.bit():
                        continue
                    n = _read_npasses(rd)
                    while rd.bit():
                        blk.lblock += 1
                    length = rd.bits(blk.lblock + _floorlog2(n))
                    contrib.append((blk, n, length))
        pos = rd.align()
        if eph and data[pos : pos + 2] == b"\xff\x92":
            pos += 2
        for blk, n, length in contrib:
            blk.layers[l] = (n, data[pos : pos + length])
            pos += length
        if pos > len(data):
            raise ValueError("packet data overruns the tile")
    return pos


def _write_packets(cs, blocks, precincts):
    geom = _geometry(cs, precincts)
    state = {}
    packets = []
    for prc, l in _packet_order(cs, geom, _ORDERS["RPCL"]):
        st = state.get(id(prc))
        if st is None:
            st = []
            for w, h, ids in prc.bands:
                if not ids:
                    st.append(None)
                    continue
                try:
                    bl = [blocks[k] for k in ids]
                except KeyError:
                    raise ValueError(
                        "{0}x{1} precincts change the code-block partition".format(
                            1 << precincts[prc.r][0], 1 << precincts[prc.r][1]
                        )
                    ) from None
                inc = [b.incl if b.incl is not None else cs.layers for b in bl]
                zbp = [b.zbp if b.zbp is not None else 0 for b in bl]
                st.append((bl, _TagTree(w, h, inc), _TagTree(w, h, zbp), [3] * len(bl)))
            state[id(prc)] = st
        wr = _BitWriter()
        body = []
        # Like Kakadu, never use the one-bit empty packet; always write the
        # inclusion bits, even when no code-block contributes.
        wr.bit(1)
        for s in st:
            if s is None:
                continue
            bl, inclt, zbpt, lblock = s
            for leaf, blk in enumerate(bl):
                c = blk.layers[l]
                if blk.incl is None or blk.incl > l:
                    inclt.encode(wr, leaf, l + 1)
                    continue
                if blk.incl == l:
                    inclt.encode(wr, leaf, l + 1)
                    zbpt.encode(wr, leaf, 1 << 30)
                else:
                    wr.bit(1 if c is not None else 0)
                if c is None:
                    continue
                n, seg = c
                _write_npasses(wr, n)
                need = max(len(seg).bit_length(), 1) - _floorlog2(n)
                inc = max(0, need - lblock[leaf])
                for _ in range(inc):
                    wr.bit(1)
                wr.bit(0)
                lblock[leaf] += inc
                wr.bits(len(seg), lblock[leaf] + _floorlog2(n))
                body.append(seg)
        packets.append(wr.flush() + b"".join(body))
    return packets


# ----------------------------------------------------------------------------
# Output


def _marker(m, body):
    return struct.pack(">HH", m, len(body) + 2) + body


def _plt_segments(lengths):
    segs = []
    cur = bytearray()
    for n in lengths:
        enc = [n & 0x7F]
        n >>= 7
        while n:
            enc.append(0x80 | (n & 0x7F))
            n >>= 7
        enc.reverse()
        if len(cur) + len(enc) > 65535 - 3:
            segs.append(bytes(cur))
            cur = bytearray()
        cur += bytes(enc)
    segs.append(bytes(cur))
    return [_marker(_PLT, bytes([z]) + s) for z, s in enumerate(segs)]


def transcode_codestream(cs_bytes, cprecincts=(128, 128), comment=None):
    """Return a new codestream in RPCL order with the given precinct size
    (width, height, same for every resolution) and PLT markers.

    comment: None keeps the COM markers of the input; bytes/str replaces
    them with one Latin-1 COM marker; False drops them."""
    cs = _Codestream(cs_bytes)
    pw, ph = cprecincts
    ex, ey = pw.bit_length() - 1, ph.bit_length() - 1
    if (1 << ex) != pw or (1 << ey) != ph or not 1 <= ex <= 15 or not 1 <= ey <= 15:
        raise ValueError("precinct dimensions must be powers of 2")
    precincts = [(ex, ey)] * (cs.levels + 1)

    blocks = {}
    _read_packets(cs, blocks)
    packets = _write_packets(cs, blocks, precincts)

    out = bytearray(struct.pack(">H", _SOC))
    com_done = False
    for m, body in cs.main:
        if m == _COD:
            b = bytearray(body[:10])
            b[0] = (body[0] | 1) & ~0x06
            b[1] = _ORDERS["RPCL"]
            b += bytes([(ey << 4) | ex] * (cs.levels + 1))
            out += _marker(_COD, bytes(b))
        elif m == _COM:
            if comment is None:
                out += _marker(m, body)
            elif comment is not False and not com_done:
                text = (
                    comment.encode("latin-1") if isinstance(comment, str) else comment
                )
                out += _marker(_COM, b"\x00\x01" + text)
                com_done = True
        elif m in (_TLM, _PLM):
            continue
        else:
            out += _marker(m, body)
    if comment not in (None, False) and not com_done:
        text = comment.encode("latin-1") if isinstance(comment, str) else comment
        out += _marker(_COM, b"\x00\x01" + text)

    plt = b"".join(_plt_segments(len(p) for p in packets))
    data = b"".join(packets)
    psot = 12 + len(plt) + 2 + len(data)
    out += struct.pack(">HHHIBB", _SOT, 10, 0, psot, 0, 1)
    out += plt
    out += struct.pack(">H", _SOD)
    out += data
    out += struct.pack(">H", _EOC)
    return bytes(out)
