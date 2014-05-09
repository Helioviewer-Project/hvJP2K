
# cython: profile=False
# cython: infer_types=True
# cython: boundscheck=False
# cython: wraparound=False

import os
import struct
import warnings

from glymur.jp2box import Jp2kBox, _BOX_WITH_ID, UnknownBox
from glymur.codestream import Codestream

cimport cython

from libc.stdint cimport uint32_t, uint64_t
from cpython.bytes cimport PyBytes_GET_SIZE, PyBytes_AS_STRING, PyBytes_FromString
cdef extern from 'arpa/inet.h':
    uint32_t ntohl(uint32_t)


cdef dict BOX_WITH_ID = <dict> _BOX_WITH_ID

cdef object hv_parse_this_box(fptr, bytes box_id, Py_ssize_t start, Py_ssize_t num_bytes):
    try:
        parser = BOX_WITH_ID[box_id].parse
    except KeyError:
        # We don't recognize the box ID, so create an UnknownBox and be
        # done with it.
        msg = 'Unrecognized box ({0}) encountered.'.format(box_id)
        warnings.warn(msg)
        return UnknownBox(box_id, offset=start, length=num_bytes)

    try:
        box = parser(fptr, start, num_bytes)
    except ValueError as err:
        msg = ('Encountered an unrecoverable ValueError while parsing a {0} '
              'box at byte offset {1}.  The original error message was "{2}"')
        msg = msg.format(box_id.decode('utf-8'), start, str(err))
        warnings.warn(msg, UserWarning)
        box = UnknownBox(box_id.decode('utf-8'), length=num_bytes, offset=start)

    return box


cpdef list hv_parse_superbox(fptr, Py_ssize_t offset, Py_ssize_t length):

    cdef Py_ssize_t box_length, num_bytes, cur_pos, start
    cdef bytes read_buffer, box_id
    cdef const char *c_read_buffer

    fptr_read = fptr.read
    fptr_seek = fptr.seek
    fptr_tell = fptr.tell

    cdef list superbox = []

    # start = fptr.tell()
    if offset == 0:
        start = 0
    else:
        start = fptr_tell()

    while True:

        # Are we at the end of the superbox?
        if start >= offset + length:
            # break
            return superbox

        read_buffer = <bytes> fptr_read(8)
        if PyBytes_GET_SIZE(read_buffer) < 8:
            msg = 'Extra bytes at end of file ignored.'
            warnings.warn(msg)
            return superbox

        # (box_length, box_id) = struct_unpack('>I4s', read_buffer)
        c_read_buffer = PyBytes_AS_STRING(read_buffer)
        box_length = ntohl((<uint32_t *> c_read_buffer)[0])
        box_id = PyBytes_FromString(c_read_buffer + 4)

        if box_length == 0:
            # The length of the box is presumed to last until the end of
            # the file.  Compute the effective length of the box.
            # num_bytes = os.path.getsize(fptr.name) - fptr.tell() + 8

            # !!! does not work if not top level box, unlikely to occur
            num_bytes = length - start # length - (start + 8) + 8
        elif box_length == 1:
            # The length of the box is in the XL field, a 64-bit value.
            read_buffer = <bytes> fptr_read(8)
            num_bytes, = struct.unpack('>Q', read_buffer)
        else:
            # The box_length value really is the length of the box!
            num_bytes = box_length

        superbox.append(hv_parse_this_box(fptr, box_id, start, num_bytes))

        if box_length == 0:
            # We're done, box lasted until the end of the file.
            return superbox

        # Position to the start of the next box.
        start += num_bytes
        cur_pos = fptr_tell()

        if num_bytes > length:
            # Length of the current box goes past the end of the
            # enclosing superbox.
            msg = '{0} box has incorrect box length ({1})'
            msg = msg.format(box_id, num_bytes)
            warnings.warn(msg)
        elif cur_pos == start:
            # At the start of the next box, jump to it.
            continue
        elif cur_pos > start:
            # The box must be invalid somehow, as the file pointer is
            # positioned past the end of the box.
            msg = ('{0} box may be invalid, the file pointer is positioned '
                   '{1} bytes past the end of the box.')
            msg = msg.format(box_id, cur_pos - start)
            warnings.warn(msg)

        fptr_seek(start)

    return superbox


# singleton essentially
@cython.freelist(4)
cdef class hvJPEG2000SignatureBox(object):
    box_id = 'jP  '
    @classmethod
    def parse(cls, fptr, Py_ssize_t offset, Py_ssize_t length):
        cdef bytes read_buffer = <bytes> fptr.read(4)
        if read_buffer != b'\x0D\x0A\x87\x0A':
            msg = 'JP2 signature verification failed for file {0}.'.format(fptr.name)
            warnings.warn(msg)
            return None
        return cls


# singleton essentially
@cython.freelist(4)
cdef class hvFileTypeBox(object):
    box_id = 'ftyp'
    @classmethod
    def parse(cls, fptr, Py_ssize_t offset, Py_ssize_t length):
        cdef bytes read_buffer = <bytes> fptr.read(length - 8)
        if read_buffer != b'\x6A\x70\x32\x20\x00\x00\x00\x00\x6A\x70\x32\x20':
            msg = 'JP2 file type verification failed for file {0}.'.format(fptr.name)
            warnings.warn(msg)
            return None
        return cls


@cython.freelist(4)
cdef class hvJP2HeaderBox(object):
    cdef readonly str box_id
    cdef readonly Py_ssize_t offset
    cdef readonly Py_ssize_t length
    cdef readonly bytes header

    @staticmethod
    def parse(fptr, Py_ssize_t offset, Py_ssize_t length):
        # grab entire box
        fptr.seek(offset)

        cdef hvJP2HeaderBox self = <hvJP2HeaderBox> hvJP2HeaderBox.__new__(hvJP2HeaderBox)
        self.box_id = 'jp2h'
        self.offset = offset
        self.length = length
        self.header = <bytes> fptr.read(length)
        return self

    cpdef list hv_parse(self, fptr):
        fptr.seek(self.offset + 8)
        return hv_parse_superbox(fptr, self.offset, self.length)


@cython.freelist(4)
cdef class hvXMLBox(object):
    cdef readonly str box_id
    cdef readonly Py_ssize_t offset
    cdef readonly Py_ssize_t length
    cdef readonly bytes xmlbuf

    @staticmethod
    def parse(fptr, Py_ssize_t offset, Py_ssize_t length):
        # grab entire box
        fptr.seek(offset)

        cdef hvXMLBox self = <hvXMLBox> hvXMLBox.__new__(hvXMLBox)
        self.box_id = 'xml '
        self.offset = offset
        self.length = length
        self.xmlbuf = <bytes> fptr.read(length)
        return self


@cython.freelist(4)
cdef class hvContiguousCodestreamBox(object):
    cdef readonly str box_id
    cdef readonly Py_ssize_t offset
    cdef readonly Py_ssize_t length

    @staticmethod
    def parse(fptr, Py_ssize_t offset, Py_ssize_t length):
        cdef Py_ssize_t main_header_offset = fptr.tell()

        cdef hvContiguousCodestreamBox self = <hvContiguousCodestreamBox> hvContiguousCodestreamBox.__new__(hvContiguousCodestreamBox)
        self.box_id = 'jp2c'
        self.offset = main_header_offset
        self.length = length + offset - main_header_offset
        return self

    cpdef hv_copy(self, ifile, ofile):
        ifile.seek(self.offset)
        ofile.write(struct.pack('>I4s', self.length + 8, b'jp2c'))
        ofile.write(ifile.read(self.length))

    cpdef object hv_parse(self, fptr):
        fptr.seek(self.offset)
        return Codestream(fptr, self.length, header_only=True)
