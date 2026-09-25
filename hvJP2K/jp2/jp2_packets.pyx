# cython: boundscheck=False, wraparound=False, initializedcheck=False, cdivision=True
"""Tier-2 packet loops of ``jp2_precincts`` in typed Cython.

``jp2_precincts`` works out the geometry and the progression order and passes
them here as flat arrays; this module decodes and encodes the packet headers.
Every access to the tile data is checked explicitly against its length, so
bounds checking is disabled for the typed arrays, whose indices come from the
geometry built by ``jp2_precincts``.
"""

from libc.stdint cimport int32_t, int64_t, uint8_t, uint64_t
from libc.stdlib cimport free, malloc, realloc
from libc.string cimport memcpy

cdef int32_t _INF = 1 << 30
cdef int64_t _HUGE = (<int64_t>1) << 62


# ----------------------------------------------------------------------------
# Bit I/O with JPEG 2000 packet-header bit stuffing


cdef struct _Reader:
    const uint8_t *data
    Py_ssize_t size
    Py_ssize_t pos
    int buf
    int ct


cdef int _bit(_Reader *rd) except -1:
    if rd.ct == 0:
        # After 0xFF the next byte carries only 7 bits.
        rd.ct = 7 if rd.buf == 0xFF else 8
        if rd.pos >= rd.size:
            raise ValueError(
                "truncated input is not supported: incomplete packet header"
            )
        rd.buf = rd.data[rd.pos]
        rd.pos += 1
    rd.ct -= 1
    return (rd.buf >> rd.ct) & 1


cdef int64_t _bits(_Reader *rd, int64_t n) except -1:
    # Saturate instead of overflowing: a value this large cannot fit in the
    # tile, and the caller then reports the overrun.
    cdef int64_t value = 0
    cdef int b
    while n > 0:
        b = _bit(rd)
        if value < _HUGE:
            # value < 2**62, so this cannot overflow.
            value = value * 2 + b
            if value > _HUGE:
                value = _HUGE
        n -= 1
    return value


cdef Py_ssize_t _align(_Reader *rd) noexcept:
    # End of packet header: skip the stuffed byte after a final 0xFF.
    if rd.buf == 0xFF:
        rd.pos += 1
    rd.ct = 0
    rd.buf = 0
    return rd.pos


cdef struct _Writer:
    uint8_t *out
    Py_ssize_t size
    Py_ssize_t cap_bytes
    int cur
    int n
    int cap


cdef int _reserve(_Writer *wr, Py_ssize_t extra) except -1:
    cdef Py_ssize_t need = wr.size + extra
    cdef Py_ssize_t cap = wr.cap_bytes
    cdef uint8_t *grown
    if need <= cap:
        return 0
    while cap < need:
        cap = cap * 2 if cap else 4096
    grown = <uint8_t *>realloc(wr.out, cap)
    if grown == NULL:
        raise MemoryError()
    wr.out = grown
    wr.cap_bytes = cap
    return 0


cdef int _emit(_Writer *wr) except -1:
    _reserve(wr, 1)
    wr.out[wr.size] = <uint8_t>wr.cur
    wr.size += 1
    wr.cap = 7 if wr.cur == 0xFF else 8
    wr.cur = 0
    wr.n = 0
    return 0


cdef int _put(_Writer *wr, int b) except -1:
    wr.cur = (wr.cur << 1) | b
    wr.n += 1
    if wr.n == wr.cap:
        _emit(wr)
    return 0


cdef int _put_bits(_Writer *wr, uint64_t v, int n) except -1:
    while n > 0:
        n -= 1
        _put(wr, <int>((v >> n) & 1))
    return 0


cdef int _flush(_Writer *wr) except -1:
    if wr.n:
        _reserve(wr, 1)
        wr.out[wr.size] = <uint8_t>(wr.cur << (wr.cap - wr.n))
        wr.size += 1
    # A packet header must not end with 0xFF.
    if wr.size and wr.out[wr.size - 1] == 0xFF:
        _reserve(wr, 1)
        wr.out[wr.size] = 0
        wr.size += 1
    wr.cur = 0
    wr.n = 0
    wr.cap = 8
    return 0


# ----------------------------------------------------------------------------
# Tag trees (B.10.2), all of them stored in shared flat arrays


cdef struct _Trees:
    int32_t *parent
    int32_t *value
    int32_t *low
    uint8_t *known


cdef Py_ssize_t _tree_size(int w, int h) noexcept:
    cdef Py_ssize_t total = 0
    while True:
        total += <Py_ssize_t>w * h
        if w * h == 1:
            return total
        w = (w + 1) >> 1
        h = (h + 1) >> 1


cdef void _tree_init(_Trees *t, Py_ssize_t base, int w, int h) noexcept:
    # Node indices are absolute; each level follows the previous one.
    cdef Py_ssize_t level = base, nxt = base, k
    cdef int x, y, pw
    while True:
        nxt = level + <Py_ssize_t>w * h
        if w * h == 1:
            t.parent[level] = -1
            break
        pw = (w + 1) >> 1
        for y in range(h):
            for x in range(w):
                t.parent[level + y * w + x] = <int32_t>(nxt + (y >> 1) * pw + (x >> 1))
        level = nxt
        w = pw
        h = (h + 1) >> 1
    for k in range(base, nxt):
        t.value[k] = _INF
        t.low[k] = 0
        t.known[k] = 0


cdef void _tree_propagate(_Trees *t, Py_ssize_t base, Py_ssize_t size) noexcept:
    # Parents have larger indices, so one forward pass sets every minimum.
    cdef Py_ssize_t k
    cdef int32_t p
    for k in range(base, base + size):
        p = t.parent[k]
        if p >= 0 and t.value[k] < t.value[p]:
            t.value[p] = t.value[k]


cdef int _path(_Trees *t, Py_ssize_t leaf, int32_t *stack) noexcept:
    cdef int depth = 0
    cdef Py_ssize_t n = leaf
    while n >= 0:
        stack[depth] = <int32_t>n
        depth += 1
        n = t.parent[n]
    return depth


cdef int _tree_decode(_Trees *t, _Reader *rd, Py_ssize_t leaf, int32_t threshold) except -1:
    cdef int32_t stack[64]
    cdef int depth = _path(t, leaf, stack)
    cdef int32_t low = 0, n
    cdef int i
    for i in range(depth - 1, -1, -1):
        n = stack[i]
        if low > t.low[n]:
            t.low[n] = low
        else:
            low = t.low[n]
        while low < threshold and low < t.value[n]:
            if _bit(rd):
                t.value[n] = low
            else:
                low += 1
        t.low[n] = low
    return t.value[leaf] < threshold


cdef int _tree_encode(_Trees *t, _Writer *wr, Py_ssize_t leaf, int32_t threshold) except -1:
    cdef int32_t stack[64]
    cdef int depth = _path(t, leaf, stack)
    cdef int32_t low = 0, n
    cdef int i
    for i in range(depth - 1, -1, -1):
        n = stack[i]
        if low > t.low[n]:
            t.low[n] = low
        else:
            low = t.low[n]
        while low < threshold:
            if low >= t.value[n]:
                if not t.known[n]:
                    _put(wr, 1)
                    t.known[n] = 1
                break
            _put(wr, 0)
            low += 1
        t.low[n] = low
    return 0


cdef int _trees_alloc(_Trees *t, Py_ssize_t size) except -1:
    # The caller's finally frees any partial allocation.
    t.parent = <int32_t *>malloc(max(size, 1) * sizeof(int32_t))
    t.value = <int32_t *>malloc(max(size, 1) * sizeof(int32_t))
    t.low = <int32_t *>malloc(max(size, 1) * sizeof(int32_t))
    t.known = <uint8_t *>malloc(max(size, 1))
    if t.parent == NULL or t.value == NULL or t.low == NULL or t.known == NULL:
        raise MemoryError()
    return 0


cdef void _trees_free(_Trees *t) noexcept:
    free(t.parent)
    free(t.value)
    free(t.low)
    free(t.known)
    t.parent = t.value = t.low = NULL
    t.known = NULL


# ----------------------------------------------------------------------------
# Coding-pass count code words (Table B.4)


cdef int _read_npasses(_Reader *rd) except -1:
    cdef int64_t n
    if not _bit(rd):
        return 1
    if not _bit(rd):
        return 2
    n = _bits(rd, 2)
    if n != 3:
        return <int>(3 + n)
    n = _bits(rd, 5)
    if n != 31:
        return <int>(6 + n)
    return <int>(37 + _bits(rd, 7))


cdef int _write_npasses(_Writer *wr, int n) except -1:
    if n == 1:
        _put(wr, 0)
    elif n == 2:
        _put_bits(wr, 0b10, 2)
    elif n <= 5:
        _put_bits(wr, 0b1100 | (n - 3), 4)
    elif n <= 36:
        _put_bits(wr, 0b111100000 | (n - 6), 9)
    elif n <= 164:
        _put_bits(wr, (0b111111111 << 7) | (n - 37), 16)
    else:
        raise ValueError("too many coding passes: {0}".format(n))
    return 0


cdef inline int _floorlog2(uint64_t n) noexcept:
    cdef int r = -1
    while n:
        n >>= 1
        r += 1
    return r


# ----------------------------------------------------------------------------
# Packets


def read_packets(
    const uint8_t[::1] data,
    const int64_t[::1] tile_part_ends,
    bint zero_psot,
    bint sop,
    bint eph,
    int nlayers,
    const int32_t[::1] band_w,
    const int32_t[::1] band_h,
    const int32_t[::1] band_start,
    const int32_t[::1] blk_ids,
    const int32_t[::1] prc_band_start,
    const int32_t[::1] order_prc,
    const int32_t[::1] order_layer,
    int32_t[::1] zbp,
    int32_t[::1] incl,
    int32_t[::1] npasses,
    int64_t[::1] offset,
    int64_t[::1] length,
):
    """Decode every packet header of the tile.

    zbp and incl (one entry per code-block) must hold -1; npasses, offset and
    length (code-block * nlayers + layer) receive each contribution, with
    npasses 0 where a code-block has none."""
    cdef Py_ssize_t nbands = band_w.shape[0]
    cdef Py_ssize_t nblocks = zbp.shape[0]
    cdef Py_ssize_t size = data.shape[0]
    cdef Py_ssize_t nparts = tile_part_ends.shape[0]
    cdef Py_ssize_t b, k, i, j, leaf, pos = 0, part = 0, node_total = 0
    cdef Py_ssize_t pkt, npkts = order_prc.shape[0]
    cdef int32_t prc, l, blk, n
    cdef int64_t len_bits, seg
    cdef _Reader rd
    cdef _Trees incl_t = _Trees(parent=NULL, value=NULL, low=NULL, known=NULL)
    cdef _Trees zbp_t = _Trees(parent=NULL, value=NULL, low=NULL, known=NULL)
    cdef Py_ssize_t *base = NULL
    cdef int64_t *lblock = NULL
    cdef int32_t *contrib = NULL
    cdef int ncontrib

    if size == 0:
        rd.data = NULL
    else:
        rd.data = &data[0]
    rd.size = size

    base = <Py_ssize_t *>malloc(max(nbands, 1) * sizeof(Py_ssize_t))
    lblock = <int64_t *>malloc(max(nblocks, 1) * sizeof(int64_t))
    contrib = <int32_t *>malloc(max(nblocks, 1) * sizeof(int32_t))
    try:
        if base == NULL or lblock == NULL or contrib == NULL:
            raise MemoryError()
        for b in range(nbands):
            base[b] = node_total
            if band_start[b + 1] > band_start[b]:
                node_total += _tree_size(band_w[b], band_h[b])
        _trees_alloc(&incl_t, node_total)
        _trees_alloc(&zbp_t, node_total)
        for b in range(nbands):
            if band_start[b + 1] > band_start[b]:
                _tree_init(&incl_t, base[b], band_w[b], band_h[b])
                _tree_init(&zbp_t, base[b], band_w[b], band_h[b])
        for k in range(nblocks):
            lblock[k] = 3

        for pkt in range(npkts):
            prc = order_prc[pkt]
            l = order_layer[pkt]
            # For Psot=0, another SOT can only be identified at a packet
            # boundary.
            if zero_psot and pos + 1 < size and data[pos] == 0xFF and data[pos + 1] == 0x90:
                raise ValueError("Psot=0 is only valid for the last tile-part")
            # Empty tile-parts share an end offset with the preceding part.
            while part < nparts and pos == tile_part_ends[part]:
                part += 1
            if part == nparts:
                raise ValueError("truncated input is not supported: missing packets")
            if sop and pos + 1 < size and data[pos] == 0xFF and data[pos + 1] == 0x91:
                pos += 6

            rd.pos = pos
            rd.buf = 0
            rd.ct = 0
            ncontrib = 0
            if _bit(&rd):
                for b in range(prc_band_start[prc], prc_band_start[prc + 1]):
                    for i in range(band_start[b], band_start[b + 1]):
                        leaf = i - band_start[b]
                        blk = blk_ids[i]
                        if incl[blk] < 0:
                            if not _tree_decode(&incl_t, &rd, base[b] + leaf, l + 1):
                                continue
                            _tree_decode(&zbp_t, &rd, base[b] + leaf, _INF)
                            zbp[blk] = zbp_t.value[base[b] + leaf]
                            incl[blk] = l
                        elif not _bit(&rd):
                            continue
                        n = _read_npasses(&rd)
                        while _bit(&rd):
                            lblock[blk] += 1
                        len_bits = lblock[blk] + _floorlog2(<uint64_t>n)
                        j = <Py_ssize_t>blk * nlayers + l
                        npasses[j] = n
                        length[j] = _bits(&rd, len_bits)
                        contrib[ncontrib] = blk
                        ncontrib += 1
            pos = _align(&rd)
            if eph and pos + 1 < size and data[pos] == 0xFF and data[pos + 1] == 0x92:
                pos += 2
            for i in range(ncontrib):
                j = <Py_ssize_t>contrib[i] * nlayers + l
                offset[j] = pos
                seg = length[j]
                if seg >= _HUGE or pos + seg > size:
                    pos = size + 1
                else:
                    pos += seg
            if pos > size:
                raise ValueError(
                    "truncated input is not supported: packet data overruns the tile"
                )
            if pos > tile_part_ends[part]:
                raise ValueError("packet crosses a tile-part boundary")
        if pos != size:
            if zero_psot and pos + 1 < size and data[pos] == 0xFF and data[pos + 1] == 0x90:
                raise ValueError("Psot=0 is only valid for the last tile-part")
            raise ValueError("{0} unparsed tile bytes".format(size - pos))
    finally:
        free(base)
        free(lblock)
        free(contrib)
        _trees_free(&incl_t)
        _trees_free(&zbp_t)


def write_packets(
    const uint8_t[::1] data,
    int nlayers,
    const int32_t[::1] band_w,
    const int32_t[::1] band_h,
    const int32_t[::1] band_start,
    const int32_t[::1] blk_ids,
    const int32_t[::1] prc_band_start,
    const int32_t[::1] order_prc,
    const int32_t[::1] order_layer,
    const int32_t[::1] zbp,
    const int32_t[::1] incl,
    const int32_t[::1] npasses,
    const int64_t[::1] offset,
    const int64_t[::1] length,
    int64_t[::1] packet_lengths,
):
    """Encode the packets for the given geometry and order; return their
    concatenation and fill packet_lengths."""
    cdef Py_ssize_t nbands = band_w.shape[0]
    cdef Py_ssize_t nblocks = zbp.shape[0]
    cdef Py_ssize_t b, k, i, j, leaf, node_total = 0, start
    cdef Py_ssize_t pkt, npkts = order_prc.shape[0]
    cdef int32_t prc, l, blk, n, log_n, need, inc
    cdef int64_t seg
    cdef _Writer wr
    cdef _Trees incl_t = _Trees(parent=NULL, value=NULL, low=NULL, known=NULL)
    cdef _Trees zbp_t = _Trees(parent=NULL, value=NULL, low=NULL, known=NULL)
    cdef Py_ssize_t *base = NULL
    cdef int32_t *lblock = NULL
    cdef int32_t *contrib = NULL
    cdef int ncontrib

    wr.out = NULL
    wr.size = 0
    wr.cap_bytes = 0
    wr.cur = 0
    wr.n = 0
    wr.cap = 8
    base = <Py_ssize_t *>malloc(max(nbands, 1) * sizeof(Py_ssize_t))
    lblock = <int32_t *>malloc(max(nblocks, 1) * sizeof(int32_t))
    contrib = <int32_t *>malloc(max(nblocks, 1) * sizeof(int32_t))
    try:
        if base == NULL or lblock == NULL or contrib == NULL:
            raise MemoryError()
        for b in range(nbands):
            base[b] = node_total
            if band_start[b + 1] > band_start[b]:
                node_total += _tree_size(band_w[b], band_h[b])
        _trees_alloc(&incl_t, node_total)
        _trees_alloc(&zbp_t, node_total)
        for b in range(nbands):
            if band_start[b + 1] > band_start[b]:
                _tree_init(&incl_t, base[b], band_w[b], band_h[b])
                _tree_init(&zbp_t, base[b], band_w[b], band_h[b])
                for i in range(band_start[b], band_start[b + 1]):
                    leaf = i - band_start[b]
                    blk = blk_ids[i]
                    incl_t.value[base[b] + leaf] = incl[blk] if incl[blk] >= 0 else nlayers
                    zbp_t.value[base[b] + leaf] = zbp[blk] if zbp[blk] >= 0 else 0
                k = _tree_size(band_w[b], band_h[b])
                _tree_propagate(&incl_t, base[b], k)
                _tree_propagate(&zbp_t, base[b], k)
        for k in range(nblocks):
            lblock[k] = 3
        _reserve(&wr, data.shape[0] + 16 * npkts + 4096)

        for pkt in range(npkts):
            prc = order_prc[pkt]
            l = order_layer[pkt]
            start = wr.size
            ncontrib = 0
            # Like Kakadu, never use the one-bit empty packet; always write
            # the inclusion bits, even when no code-block contributes.
            _put(&wr, 1)
            for b in range(prc_band_start[prc], prc_band_start[prc + 1]):
                for i in range(band_start[b], band_start[b + 1]):
                    leaf = i - band_start[b]
                    blk = blk_ids[i]
                    j = <Py_ssize_t>blk * nlayers + l
                    if incl[blk] < 0 or incl[blk] > l:
                        _tree_encode(&incl_t, &wr, base[b] + leaf, l + 1)
                        continue
                    if incl[blk] == l:
                        _tree_encode(&incl_t, &wr, base[b] + leaf, l + 1)
                        _tree_encode(&zbp_t, &wr, base[b] + leaf, _INF)
                    else:
                        _put(&wr, 1 if npasses[j] else 0)
                    if not npasses[j]:
                        continue
                    n = npasses[j]
                    _write_npasses(&wr, n)
                    log_n = _floorlog2(<uint64_t>n)
                    need = (_floorlog2(<uint64_t>length[j]) + 1) - log_n
                    inc = need - lblock[blk]
                    if inc < 0:
                        inc = 0
                    # Unary Lblock increment: inc one bits followed by a zero.
                    for k in range(inc):
                        _put(&wr, 1)
                    _put(&wr, 0)
                    lblock[blk] += inc
                    _put_bits(&wr, <uint64_t>length[j], lblock[blk] + log_n)
                    contrib[ncontrib] = blk
                    ncontrib += 1
            _flush(&wr)
            for i in range(ncontrib):
                j = <Py_ssize_t>contrib[i] * nlayers + l
                seg = length[j]
                _reserve(&wr, seg)
                if seg:
                    memcpy(wr.out + wr.size, &data[offset[j]], seg)
                wr.size += seg
            packet_lengths[pkt] = wr.size - start
        return (<char *>wr.out)[: wr.size] if wr.size else b""
    finally:
        free(wr.out)
        free(base)
        free(lblock)
        free(contrib)
        _trees_free(&incl_t)
        _trees_free(&zbp_t)
