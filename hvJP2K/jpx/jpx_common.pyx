
# cython: profile=False
# cython: infer_types=True
# cython: boundscheck=False
# cython: wraparound=False

cimport cython

from libc.stdint cimport uint32_t
from libc.string cimport memcpy
from cpython.bytes cimport PyBytes_GET_SIZE, PyBytes_AS_STRING, PyBytes_FromStringAndSize
cdef extern from 'arpa/inet.h':
    uint32_t ntohl(uint32_t)

import warnings
from struct import error as StructError, pack, unpack

from glymur.jp2box import UnknownBox, _BOX_WITH_ID
from glymur.codestream import Codestream


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
    except (ValueError, StructError) as err:
        msg = ('Encountered an unrecoverable error while parsing a {0} '
               'box at byte offset {1}.  The original error message was "{2}"')
        msg = msg.format(box_id.decode('utf-8'), start, str(err))
        warnings.warn(msg, UserWarning)
        box = UnknownBox(box_id.decode('utf-8'), length=num_bytes, offset=start)

    return box


cpdef list hv_parse_superbox(fptr, Py_ssize_t offset, Py_ssize_t length):

    cdef Py_ssize_t box_length, header_length, num_bytes, cur_pos, start
    cdef uint32_t raw_box_length
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
            break

        read_buffer = <bytes> fptr_read(8)
        if PyBytes_GET_SIZE(read_buffer) < 8:
            msg = 'Extra bytes at end of file ignored.'
            warnings.warn(msg)
            break

        # (box_length, box_id) = unpack('>I4s', read_buffer)
        c_read_buffer = PyBytes_AS_STRING(read_buffer)
        memcpy(&raw_box_length, c_read_buffer, sizeof(raw_box_length))
        box_length = ntohl(raw_box_length)
        box_id = PyBytes_FromStringAndSize(c_read_buffer + 4, 4)

        if box_length == 0:
            # The length of the box is presumed to last until the end of
            # the file.  Compute the effective length of the box.
            num_bytes = offset + length - start
        elif box_length == 1:
            # The length of the box is in the XL field, a 64-bit value.
            read_buffer = <bytes> fptr_read(8)
            if PyBytes_GET_SIZE(read_buffer) < 8:
                warnings.warn('Incomplete extended box length ignored.')
                break
            num_bytes, = unpack('>Q', read_buffer)
        else:
            # The box_length value really is the length of the box!
            num_bytes = box_length

        header_length = 16 if box_length == 1 else 8
        if num_bytes < header_length or start + num_bytes > offset + length:
            msg = '{0} box has incorrect box length ({1})'
            warnings.warn(msg.format(box_id, num_bytes))
            break

        box = hv_parse_this_box(fptr, box_id, start, num_bytes)
        superbox.append(box)

        if box_length == 0:
            # We're done, box lasted until the end of the file.
            break

        # Position to the start of the next box.
        start += num_bytes
        cur_pos = fptr_tell()

        if cur_pos == start:
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


cpdef hv_copy_codestream(ifile, ofile, Py_ssize_t offset, Py_ssize_t length):
    cdef Py_ssize_t chunk_length, remaining = length
    cdef bytes chunk

    if length < 0:
        raise ValueError('negative JPEG 2000 codestream length')

    ifile.seek(offset)
    if length <= 0xFFFFFFFF - 8:
        ofile.write(pack('>I4s', length + 8, b'jp2c'))
    else:
        ofile.write(pack('>I4sQ', 1, b'jp2c', length + 16))

    while remaining:
        chunk_length = min(remaining, 1024 * 1024)
        chunk = <bytes> ifile.read(chunk_length)
        if not chunk:
            raise EOFError('unexpected end of JPEG 2000 codestream')
        ofile.write(chunk)
        remaining -= PyBytes_GET_SIZE(chunk)


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
    @classmethod
    def parse(cls, fptr, Py_ssize_t offset, Py_ssize_t length):
        # grab entire box
        fptr.seek(offset)

        cdef hvJP2HeaderBox self = <hvJP2HeaderBox> cls.__new__(cls)
        self.box_id = 'jp2h'
        self.offset = offset
        self.length = length
        self.header = <bytes> fptr.read(length)
        return self

    cpdef list hv_parse(hvJP2HeaderBox self, fptr):
        fptr.seek(self.offset + 8)
        return hv_parse_superbox(fptr, self.offset, self.length)


@cython.freelist(4)
cdef class hvXMLBox(object):
    @classmethod
    def parse(cls, fptr, Py_ssize_t offset, Py_ssize_t length):
        # grab entire box
        fptr.seek(offset)

        cdef hvXMLBox self = <hvXMLBox> cls.__new__(cls)
        self.box_id = 'xml '
        self.offset = offset
        self.length = length
        self.xmlbuf = <bytes> fptr.read(length)
        return self


@cython.freelist(4)
cdef class hvContiguousCodestreamBox(object):
    @classmethod
    def parse(cls, fptr, Py_ssize_t offset, Py_ssize_t length):
        cdef Py_ssize_t main_header_offset = fptr.tell()

        cdef hvContiguousCodestreamBox self = <hvContiguousCodestreamBox> cls.__new__(cls)
        self.box_id = 'jp2c'
        self.offset = main_header_offset
        self.length = length + offset - main_header_offset
        return self

    cpdef hv_copy(hvContiguousCodestreamBox self, ifile, ofile):
        hv_copy_codestream(ifile, ofile, self.offset, self.length)

    cpdef object hv_parse(hvContiguousCodestreamBox self, fptr):
        fptr.seek(self.offset)
        return Codestream(fptr, self.length, header_only=True)
