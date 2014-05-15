
cpdef list hv_parse_superbox(fptr, Py_ssize_t offset, Py_ssize_t length)

cdef class hvJP2HeaderBox(object):
    cdef readonly str box_id
    cdef readonly Py_ssize_t offset
    cdef readonly Py_ssize_t length
    cdef readonly bytes header

    cpdef list hv_parse(hvJP2HeaderBox self, fptr)


cdef class hvXMLBox(object):
    cdef readonly str box_id
    cdef readonly Py_ssize_t offset
    cdef readonly Py_ssize_t length
    cdef readonly bytes xmlbuf


cdef class hvContiguousCodestreamBox(object):
    cdef readonly str box_id
    cdef readonly Py_ssize_t offset
    cdef readonly Py_ssize_t length

    cpdef hv_copy(hvContiguousCodestreamBox self, ifile, ofile)
    cpdef object hv_parse(hvContiguousCodestreamBox self, fptr)
