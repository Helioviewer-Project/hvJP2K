"""In-process replacement for the part of ``kdu_transcode`` that hvJP2K uses.

``kdu_transcode Corder=RPCL ORGgen_plt=yes Cprecincts={128,128}`` rewrites a
codestream without touching the entropy-coded data: every code-block keeps
its coding passes, bytes and zero bit-planes, and only the Tier-2 layer
changes.  The code-blocks are regrouped into the requested precincts, a new
packet header is written for every (resolution, precinct, component, layer)
in RPCL order, and the packet lengths are recorded in a PLT marker.

That is possible as long as the new precincts leave the code-block
partition unchanged: precincts smaller than the code-blocks clip them, and
the blocks of one partition must be the blocks of the other.

Supported input: complete one-tile codestreams (any number of tile-parts),
any progression order, no COC, RGN, POC, PPM or PPT markers, no coding
parameters in tile-part headers, and code-block styles without selective
arithmetic coding bypass or termination on each coding pass.  SOP/EPH
markers in the input are skipped and not written.
"""

import struct
from array import array

try:
    from . import jp2_packets as _packets
except ImportError as exc:
    raise ImportError(
        "hvJP2K's Cython packet extension is unavailable; run `pip install .`"
    ) from exc

_SOC, _SIZ, _COD, _COC, _RGN, _POC = 0xFF4F, 0xFF51, 0xFF52, 0xFF53, 0xFF5E, 0xFF5F
_TLM, _PLM, _PLT, _PPM, _COM = 0xFF55, 0xFF57, 0xFF58, 0xFF60, 0xFF64
_SOT, _SOD, _EOC = 0xFF90, 0xFF93, 0xFFD9

_ORDERS = {"LRCP": 0, "RLCP": 1, "RPCL": 2, "PCRL": 3, "CPRL": 4}


def _ceildiv(a, b):
    return -(-a // b)


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
        self.tile_part_ends = []  # cumulative offsets in the packet data
        self.zero_psot = False
        declared_parts = None
        while True:
            if pos + 2 > len(cs):
                raise ValueError("missing EOC marker")
            m = struct.unpack(">H", cs[pos : pos + 2])[0]
            if m == _EOC:
                if pos + 2 != len(cs):
                    raise ValueError("data after EOC marker")
                break
            if m != _SOT:
                raise ValueError("expected SOT at offset {0}".format(pos))
            if pos + 12 > len(cs) - 2:
                raise ValueError("truncated SOT marker")
            if struct.unpack(">H", cs[pos + 2 : pos + 4])[0] != 10:
                raise ValueError("invalid SOT marker length")
            isot, psot, tpsot, tnsot = struct.unpack_from(">HIBB", cs, pos + 4)
            if isot != 0:
                raise ValueError("tile index must be 0")
            if tpsot != len(self.tile_part_ends) or tpsot == 255:
                raise ValueError("out-of-order tile-part index")
            if tnsot:
                if declared_parts is not None and tnsot != declared_parts:
                    raise ValueError("inconsistent tile-part count")
                declared_parts = tnsot
                if tpsot >= tnsot:
                    raise ValueError("tile-part index exceeds declared count")
            if psot == 0:
                if declared_parts is not None and tpsot != declared_parts - 1:
                    raise ValueError("Psot=0 is only valid for the last tile-part")
                if cs[-2:] != b"\xff\xd9":
                    raise ValueError("missing EOC marker")
                self.zero_psot = True
            end = pos + psot if psot else len(cs) - 2
            if end < pos + 14 or end > len(cs) - 2:
                raise ValueError("invalid tile-part length")
            p = pos + 12
            while True:
                if p + 2 > end:
                    raise ValueError("tile-part has no SOD marker")
                mm = struct.unpack(">H", cs[p : p + 2])[0]
                if mm == _SOD:
                    p += 2
                    break
                if p + 4 > end:
                    raise ValueError("truncated tile-part marker")
                LL = struct.unpack(">H", cs[p + 2 : p + 4])[0]
                if mm not in (_PLT, _COM):
                    raise ValueError(
                        "unsupported tile-part marker 0x{0:04X}".format(mm)
                    )
                if LL < 2 or p + 2 + LL > end:
                    raise ValueError("invalid tile-part marker length")
                p += 2 + LL
            body += cs[p:end]
            self.tile_part_ends.append(len(body))
            pos = end
        if not self.tile_part_ends:
            raise ValueError("no tile-parts")
        if declared_parts is not None and len(self.tile_part_ends) != declared_parts:
            raise ValueError("tile-part count differs from TNsot")
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
    prc: _Precinct
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
    layers = range(cs.layers)
    resolutions = range(cs.levels + 1)
    components = range(len(cs.comps))
    # COC is unsupported, so all components have the same resolution count.
    if order == 0:
        return [
            (prc, l)
            for l in layers
            for r in resolutions
            for c in components
            for prc in geom[c, r]
        ]
    if order == 1:
        return [
            (prc, l)
            for r in resolutions
            for l in layers
            for c in components
            for prc in geom[c, r]
        ]
    # Layers come last here; (component, resolution, anchor) identifies a precinct.
    precincts = [prc for key in sorted(geom) for prc in geom[key]]
    if order == 2:
        precincts.sort(key=lambda prc: (prc.r, prc.ay, prc.ax, prc.c))
    elif order == 3:
        precincts.sort(key=lambda prc: (prc.ay, prc.ax, prc.c, prc.r))
    else:
        precincts.sort(key=lambda prc: (prc.c, prc.ay, prc.ax, prc.r))
    return [(prc, l) for prc in precincts for l in layers]


# ----------------------------------------------------------------------------
# Packet layout for the compiled Tier-2 engine


def _flatten(geom, order, index, precincts):
    """Flat int32 arrays describing geom and order for jp2_packets."""
    band_w, band_h, band_start, blk_ids, prc_band_start = [], [], [0], [], [0]
    prc_index = {}
    for key in sorted(geom):
        for prc in geom[key]:
            prc_index[id(prc)] = len(prc_band_start) - 1
            for w, h, ids in prc.bands:
                band_w.append(w)
                band_h.append(h)
                try:
                    blk_ids.extend([index[k] for k in ids])
                except KeyError:
                    raise ValueError(
                        "{0}x{1} precincts change the code-block partition".format(
                            1 << precincts[prc.r][0], 1 << precincts[prc.r][1]
                        )
                    ) from None
                band_start.append(len(blk_ids))
            prc_band_start.append(len(band_w))
    order_prc = [prc_index[id(prc)] for prc, _ in order]
    order_layer = [l for _, l in order]
    return tuple(
        [
            array("i", a)
            for a in (
                band_w,
                band_h,
                band_start,
                blk_ids,
                prc_band_start,
                order_prc,
                order_layer,
            )
        ]
    )


def _transcode_packets(cs, precincts):
    """Decode and repackage packets with the compiled Tier-2 engine."""
    geom = _geometry(cs, cs.precincts)
    index = {}
    for key in sorted(geom):
        for prc in geom[key]:
            for _, _, ids in prc.bands:
                for k in ids:
                    index[k] = len(index)
    nblocks, nlayers = len(index), cs.layers
    zbp = array("i", [-1]) * nblocks
    incl = array("i", [-1]) * nblocks
    npasses = array("i", [0]) * (nblocks * nlayers)
    offset = array("q", [0]) * (nblocks * nlayers)
    length = array("q", [0]) * (nblocks * nlayers)
    _packets.read_packets(
        cs.body,
        array("q", cs.tile_part_ends),
        cs.zero_psot,
        bool(cs.scod & 2),
        bool(cs.scod & 4),
        nlayers,
        *_flatten(geom, _packet_order(cs, geom, cs.order), index, cs.precincts),
        zbp,
        incl,
        npasses,
        offset,
        length,
    )
    geom = _geometry(cs, precincts)
    tables = _flatten(geom, _packet_order(cs, geom, _ORDERS["RPCL"]), index, precincts)
    lengths = array("q", [0]) * len(tables[-1])
    data = _packets.write_packets(
        cs.body, nlayers, *tables, zbp, incl, npasses, offset, length, lengths
    )
    return data, lengths


# ----------------------------------------------------------------------------
# Output


def _marker(m, body):
    return struct.pack(">HH", m, len(body) + 2) + body


def _plt_segments(lengths):
    segs = []
    cur = bytearray()
    for n in lengths:
        if n < 0x80:
            if len(cur) == 65535 - 3:
                segs.append(bytes(cur))
                cur = bytearray()
            cur.append(n)
            continue
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

    data, lengths = _transcode_packets(cs, precincts)

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

    plt = b"".join(_plt_segments(lengths))
    psot = 12 + len(plt) + 2 + len(data)
    out += struct.pack(">HHHIBB", _SOT, 10, 0, psot, 0, 1)
    out += plt
    out += struct.pack(">H", _SOD)
    out += data
    out += struct.pack(">H", _EOC)
    return bytes(out)
