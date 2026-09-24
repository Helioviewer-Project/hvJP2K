cdef class _BitReader:
    cdef public object data
    cdef public Py_ssize_t pos
    cdef public int buf, ct
    cdef void _fill(self) except *
    cpdef int bit(self)
    cpdef object bits(self, Py_ssize_t n)
    cpdef Py_ssize_t align(self)

cdef class _BitWriter:
    cdef public object out
    cdef public int cur, n, cap
    cdef void _emit(self) except *
    cpdef void bit(self, int b)
    cpdef void bits(self, object v, Py_ssize_t n)
    cpdef object flush(self)

cdef class _TagTree:
    cdef public object value, low, known, paths
    cpdef bint decode(self, _BitReader rd, Py_ssize_t leaf, int threshold)
    cpdef void encode(self, _BitWriter wr, Py_ssize_t leaf, int threshold)

cdef class _Precinct:
    cdef public Py_ssize_t c, r, px, py, ax, ay
    cdef public object bands

cdef class _Block:
    cdef public object zbp, incl, layers
    cdef public int lblock

cpdef Py_ssize_t _ceildiv(Py_ssize_t a, Py_ssize_t b)
cpdef int _read_npasses(_BitReader rd)
cpdef void _write_npasses(_BitWriter wr, int n)
cpdef int _floorlog2(int n)
