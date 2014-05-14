
# cython: profile=False
# cython: infer_types=True
# cython: boundscheck=False
# cython: wraparound=False

import os
import struct
import warnings

from glymur.jp2box import UnknownBox, _BOX_WITH_ID
from glymur.codestream import Codestream


def hv_parse_this_box(fptr, box_id, start, num_bytes):
    try:
        parser = _BOX_WITH_ID[box_id].parse
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

# @profile
def hv_parse_superbox(fptr, offset, length):

    fptr_read = fptr.read
    fptr_seek = fptr.seek
    fptr_tell = fptr.tell

    superbox = []

    # start = fptr.tell()
    if offset == 0:
        start = 0
    else:
        start = fptr_tell()

    while True:

        # Are we at the end of the superbox?
        if start >= offset + length:
            break

        read_buffer = fptr_read(8)
        if len(read_buffer) < 8:
            msg = 'Extra bytes at end of file ignored.'
            warnings.warn(msg)
            break

        (box_length, box_id) = struct.unpack('>I4s', read_buffer)
        if box_length == 0:
            # The length of the box is presumed to last until the end of
            # the file.  Compute the effective length of the box.
            # num_bytes = os.path.getsize(fptr.name) - fptr.tell() + 8

            # !!! does not work if not top level box, unlikely to occur
            num_bytes = length - start # length - (start + 8) + 8
        elif box_length == 1:
            # The length of the box is in the XL field, a 64-bit value.
            read_buffer = fptr_read(8)
            num_bytes, = struct.unpack('>Q', read_buffer)
        else:
            # The box_length value really is the length of the box!
            num_bytes = box_length

        box = hv_parse_this_box(fptr, box_id, start, num_bytes)
        superbox.append(box)

        if box_length == 0:
            # We're done, box lasted until the end of the file.
            break

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
class hvJPEG2000SignatureBox(object):
    box_id = 'jP  '

    @classmethod
    def parse(cls, fptr, offset, length):
        if fptr.read(4) != b'\x0D\x0A\x87\x0A':
            msg = 'JP2 signature verification failed for file {0}.'.format(fptr.name)
            warnings.warn(msg)
            return None
        return cls


# singleton essentially
class hvFileTypeBox(object):
    box_id = 'ftyp'

    @classmethod
    def parse(cls, fptr, offset, length):
        if fptr.read(length - 8) != b'\x6A\x70\x32\x20\x00\x00\x00\x00\x6A\x70\x32\x20':
            msg = 'JP2 file type verification failed for file {0}.'.format(fptr.name)
            warnings.warn(msg)
            return None
        return cls


class hvJP2HeaderBox(object):
    box_id = 'jp2h'
    def __init__(self, header, length, offset):
        self.offset = offset
        self.length = length
        self.header = header

    @classmethod
    def parse(cls, fptr, offset, length):
        # grab entire box
        fptr.seek(offset)
        return cls(fptr.read(length), length, offset)

    def hv_parse(self, fptr):
        fptr.seek(self.offset + 8)
        return hv_parse_superbox(fptr, self.offset, self.length)


class hvXMLBox(object):
    box_id = 'xml '
    def __init__(self, xmlbuf, length, offset):
        self.offset = offset
        self.length = length
        self.xmlbuf = xmlbuf

    @classmethod
    def parse(cls, fptr, offset, length):
        # grab entire box
        fptr.seek(offset)
        return cls(fptr.read(length), length, offset)


class hvContiguousCodestreamBox(object):
    box_id = 'jp2c'
    def __init__(self, length, offset):
        self.offset = offset
        self.length = length

    @classmethod
    def parse(cls, fptr, offset, length):
        main_header_offset = fptr.tell()
        return cls(length + offset - main_header_offset, main_header_offset)

    def hv_copy(self, ifile, ofile):
        ifile.seek(self.offset)
        ofile.write(struct.pack('>I4s', self.length + 8, b'jp2c'))
        ofile.write(ifile.read(self.length))

    def hv_parse(self, fptr):
        fptr.seek(self.offset)
        return Codestream(fptr, self.length, header_only=True)
