cdef class _Precinct:
    cdef public Py_ssize_t c, r, px, py, ax, ay
    cdef public object bands

cpdef Py_ssize_t _ceildiv(Py_ssize_t a, Py_ssize_t b)
