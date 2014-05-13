
# cython: profile=False
# cython: infer_types=True
# cython: boundscheck=False
# cython: wraparound=False

cimport cython

from cpython.bytes cimport PyBytes_AS_STRING, PyBytes_FromStringAndSize
from libc.stdlib cimport calloc, malloc, free
from libc.string cimport strlen, memcpy, memset
from posix.fcntl cimport open, O_RDONLY
from posix.unistd cimport close

ctypedef Py_ssize_t size_t
ctypedef Py_ssize_t off_t

cdef extern from 'sys/stat.h' nogil:
    struct stat_t 'stat':
        off_t     st_size

    int stat(const char *, stat_t *)

cdef extern from 'sys/mman.h' nogil:
    enum: PROT_READ
    enum: MAP_SHARED
    enum: MAP_FAILED
    void *mmap(void *, size_t, int, int, int, off_t)
    int munmap(void *, size_t)

cdef int mmap_open(const char *name, mmap_t *mm) nogil:
    cdef stat_t st
    cdef Py_ssize_t size, name_len
    cdef int fd
    cdef void *buf

    if stat(name, &st) !=0:
        return -1
    size = st.st_size

    fd = open(name, O_RDONLY)
    if fd == -1:
        return 0

    buf = mmap(NULL, size, PROT_READ, MAP_SHARED, fd, 0)
    close(fd)
    if buf == <void *> MAP_FAILED:
        return -1

    mm.buf = <char *> buf
    mm.size = size
    mm.off = 0

    name_len = strlen(name)
    mm.name = <char *> malloc(name_len + 1)
    memcpy(mm.name, name, name_len)
    mm.name[name_len] = 0
    mm.name_len = name_len

    return 0

cdef void mmap_close(mmap_t *mm) nogil:
    munmap(mm.buf, mm.size) # != 0

    if mm.name != NULL:
        free(mm.name)
    memset(mm, 0, sizeof(mmap_t))

@cython.freelist(4)
cdef class hvMap(object):
    def __cinit__(self):
        self.mm = <mmap_t *> calloc(1, sizeof(mmap_t))

    def __dealloc__(self):
        free(self.mm)

    # used in error path, slow unicode
    def __getattr__(self, name):
        if name == 'name':
            return <str> PyBytes_FromStringAndSize(self.mm.name, self.mm.name_len).decode('utf-8')

    cpdef open(hvMap self, bytes name):
        mmap_open(PyBytes_AS_STRING(name), self.mm)

    cpdef close(hvMap self):
        mmap_close(self.mm)

    cpdef Py_ssize_t size(hvMap self):
        return self.mm.size

    cpdef Py_ssize_t tell(hvMap self):
        return self.mm.off

    cpdef seek(hvMap self, Py_ssize_t off):
        self.mm.off = off

    cpdef bytes read(hvMap self, Py_ssize_t num):
        cdef Py_ssize_t new_off = self.mm.off + num
        if new_off > self.mm.size - 1:
            new_off = self.mm.size - 1
            num = new_off - self.mm.off + 1

        cdef bytes buf = <bytes> PyBytes_FromStringAndSize(self.mm.buf + self.mm.off, num)
        self.mm.off = new_off

        return buf
