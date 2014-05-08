
import os
import struct
import warnings

from glymur.jp2box import Jp2kBox, _BOX_WITH_ID, UnknownBox
from glymur.codestream import Codestream


cdef object hv_parse_this_box(fptr, bytes box_id, int start, int num_bytes):
    cdef dict BOX_WITH_ID = _BOX_WITH_ID

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
        msg = "Encountered an unrecoverable ValueError while parsing a {0} "
        msg += "box at byte offset {1}.  The original error message was "
        msg += "\"{2}\""
        msg = msg.format(box_id.decode('utf-8'), start, str(err))
        warnings.warn(msg, UserWarning)
        box = UnknownBox(box_id.decode('utf-8'), length=num_bytes, offset=start)

    return box


cpdef list hv_parse_superbox(fptr, int offset, int length):

    cdef int box_length, num_bytes, cur_pos, start
    cdef bytes read_buffer, box_id

    superbox = []

    start = fptr.tell()

    while True:

        # Are we at the end of the superbox?
        if start >= offset + length:
            break

        read_buffer = fptr.read(8)
        if len(read_buffer) < 8:
            msg = "Extra bytes at end of file ignored."
            warnings.warn(msg)
            return superbox

        (box_length, box_id) = struct.unpack('>I4s', read_buffer)

        if box_length == 0:
            # The length of the box is presumed to last until the end of
            # the file.  Compute the effective length of the box.
            # num_bytes = os.path.getsize(fptr.name) - fptr.tell() + 8
            num_bytes = length - start # length + 8 - (start + 8)

        elif box_length == 1:
            # The length of the box is in the XL field, a 64-bit value.
            read_buffer = fptr.read(8)
            num_bytes, = struct.unpack('>Q', read_buffer)
        else:
            # The box_length value really is the length of the box!
            num_bytes = box_length

        superbox.append(hv_parse_this_box(fptr, box_id, start, num_bytes))

        # Position to the start of the next box.
        start += num_bytes
        cur_pos = fptr.tell()

        if num_bytes > length:
            # Length of the current box goes past the end of the
            # enclosing superbox.
            msg = '{0} box has incorrect box length ({1})'
            msg = msg.format(box_id, num_bytes)
            warnings.warn(msg)
        elif cur_pos > start:
            # The box must be invalid somehow, as the file pointer is
            # positioned past the end of the box.
            msg = '{0} box may be invalid, the file pointer is positioned '
            msg += '{1} bytes past the end of the box.'
            msg = msg.format(box_id, cur_pos - start)
            warnings.warn(msg)

        fptr.seek(start)

    return superbox


# singleton essentially
cdef class hvJPEG2000SignatureBox(object):
    box_id = 'jP  '
    @classmethod
    def parse(cls, fptr, offset, length):
        if fptr.read(4) != b'\x0D\x0A\x87\x0A':
            print('JP2 signature verification failed: ' + fptr.name)
            return None
        return cls


# singleton essentially
cdef class hvFileTypeBox(object):
    box_id = 'ftyp'
    @classmethod
    def parse(cls, fptr, offset, length):
        if fptr.read(length - 8) != b'\x6A\x70\x32\x20\x00\x00\x00\x00\x6A\x70\x32\x20':
            print('JP2 file type verification failed: ' + fptr.name)
            return None
        return cls


cdef class hvJP2HeaderBox(object):
    cdef public const char *box_id
    cdef public int offset
    cdef public int length
    cdef public bytes header

    @staticmethod
    def parse(fptr, int offset, int length):
        # grab entire box
        fptr.seek(offset)

        cdef hvJP2HeaderBox self = hvJP2HeaderBox.__new__(hvJP2HeaderBox)
        self.box_id = 'jp2h'
        self.offset = offset
        self.length = length
        self.header = fptr.read(length)
        return self

    cpdef hv_parse(self, fptr):
        fptr.seek(self.offset + 8)
        return hv_parse_superbox(fptr, self.offset, self.length)


cdef class hvXMLBox(object):
    cdef public const char *box_id
    cdef public int offset
    cdef public int length
    cdef public bytes xmlbuf

    @staticmethod
    def parse(fptr, int offset, int length):
        # grab entire box
        fptr.seek(offset)

        cdef hvXMLBox self = hvXMLBox.__new__(hvXMLBox)
        self.box_id = 'xml '
        self.offset = offset
        self.length = length
        self.xmlbuf = fptr.read(length)
        return self


cdef class hvContiguousCodestreamBox(object):
    cdef public const char *box_id
    cdef public int offset
    cdef public int length

    @staticmethod
    def parse(fptr, int offset, int length):
        cdef int main_header_offset = fptr.tell()

        cdef hvContiguousCodestreamBox self = hvContiguousCodestreamBox.__new__(hvContiguousCodestreamBox)
        self.box_id = 'jp2c'
        self.offset = main_header_offset
        self.length = length + offset - main_header_offset
        return self

    cpdef hv_copy(self, ifile, ofile):
        ifile.seek(self.offset)
        ofile.write(struct.pack('>I4s', self.length + 8, b'jp2c'))
        ofile.write(ifile.read(self.length))

    cpdef hv_parse(self, fptr):
        fptr.seek(self.offset)
        return Codestream(fptr, self.length, header_only=True)
