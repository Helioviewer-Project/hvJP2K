
import os
import struct

from glymur.jp2box import Jp2kBox
from glymur.codestream import Codestream


# singleton essentially
class hvJPEG2000SignatureBox(object):
    box_id = 'jP  '
    @classmethod
    def parse(cls, fptr, offset, length):
        if fptr.read(4) != b'\x0D\x0A\x87\x0A':
            print('JP2 signature verification failed: ' + fptr.name)
            return None
        return cls


# singleton essentially
class hvFileTypeBox(object):
    box_id = 'ftyp'
    @classmethod
    def parse(cls, fptr, offset, length):
        if fptr.read(length - 8) != b'\x6A\x70\x32\x20\x00\x00\x00\x00\x6A\x70\x32\x20':
            print('JP2 file type verification failed: ' + fptr.name)
            return None
        return cls


class hvJP2HeaderBox(Jp2kBox):
    def __init__(self, header, length, offset):
        self.box_id = 'jp2h'
        self.offset = offset
        self.length = length
        self.header = header
        self.box = []

    @classmethod
    def parse(cls, fptr, offset, length):
        # grab entire box
        fptr.seek(offset)
        return cls(fptr.read(length), length, offset)

    def hv_parse(self, fptr):
        fptr.seek(self.offset + 8)
        self.box = self.parse_superbox(fptr)


class hvXMLBox(Jp2kBox):
    def __init__(self, xmlbuf, length, offset):
        self.box_id = 'xml '
        self.offset = offset
        self.length = length
        self.xmlbuf = xmlbuf

    @classmethod
    def parse(cls, fptr, offset, length):
        # grab entire box
        fptr.seek(offset)
        return cls(fptr.read(length), length, offset)


class hvContiguousCodestreamBox(Jp2kBox):
    def __init__(self, length, offset):
        self.box_id = 'jp2c'
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
