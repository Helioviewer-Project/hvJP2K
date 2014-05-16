
ctypedef struct mmap_t:
    char *buf
    Py_ssize_t size
    Py_ssize_t off
    char *name
    Py_ssize_t name_len
    int is_open

cdef class hvMap(object):
    cdef mmap_t *mm

    cpdef int open(hvMap self, bytes name)
    cpdef close(hvMap self)
    cpdef Py_ssize_t size(hvMap self)
    cpdef Py_ssize_t tell(hvMap self)
    cpdef seek(hvMap self, Py_ssize_t off)
    cpdef bytes read(hvMap self, Py_ssize_t num)
