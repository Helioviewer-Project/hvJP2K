
import os
import struct

from glymur.jp2box import Jp2kBox


class hvJp2k(Jp2kBox):
    def __init__(self, filename):
        self.offset = 0
        self.length = os.path.getsize(filename)

        with open(filename, 'rb') as fptr:
            self.box = self.parse_superbox(fptr)


class hvJPEG2000SignatureBox(Jp2kBox):
    def __init__(self, length=0, offset=-1):
        self.box_id = 'jP  '
        self.offset = offset
        self.length = length

    @classmethod
    def parse(cls, fptr, offset, length):
        if fptr.read(4) != b'\x0D\x0A\x87\x0A':
            print('JP2 signature verification failed: ' + fptr.name)
            return None

        return cls(length=length, offset=offset)


class hvFileTypeBox(Jp2kBox):
    def __init__(self, length=0, offset=-1):
        self.box_id = 'ftyp'
        self.offset = offset
        self.length = length

    @classmethod
    def parse(cls, fptr, offset, length):
        if fptr.read(length - 8) != b'\x6A\x70\x32\x20\x00\x00\x00\x00\x6A\x70\x32\x20':
            print('JP2 file type verification failed: ' + fptr.name)
            return None

        return cls(length=length, offset=offset)


class hvJP2HeaderBox(Jp2kBox):
    def __init__(self, length=0, offset=-1):
        self.box_id = 'jp2h'
        self.offset = offset
        self.length = length
        self.box = []

    @classmethod
    def parse(cls, fptr, offset, length):
        return cls(length=length, offset=offset)

    def hv_parse(self, fptr):
        fptr.seek(self.offset + 8)
        self.box = self.parse_superbox(fptr)


class hvXMLBox(Jp2kBox):
    def __init__(self, xmlbuf=None, length=0, offset=-1):
        self.box_id = 'xml '
        self.offset = offset
        self.length = length
        self.xmlbuf = xmlbuf

    @classmethod
    def parse(cls, fptr, offset, length):
        # grab entire box
        fptr.seek(offset)
        return cls(xmlbuf=fptr.read(length), length=length, offset=offset)


class hvContiguousCodestreamBox(Jp2kBox):
    def __init__(self, length=0, offset=-1):
        self.box_id = 'jp2c'
        self.offset = offset
        self.length = length

    @classmethod
    def parse(cls, fptr, offset=0, length=0):
        main_header_offset = fptr.tell()
        return cls(length=length+offset-main_header_offset, offset=main_header_offset)

    def copy(self, ifile, ofile):
        ifile.seek(self.offset)
        ofile.write(struct.pack('>I4s', self.length + 8, b'jp2c'))
        ofile.write(ifile.read(self.length))
