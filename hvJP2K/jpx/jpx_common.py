
import glymur
from glymur.jp2box import Jp2kBox

# do not parse the codestreams
glymur.set_parseoptions(codestream=False)


class hvJPEG2000SignatureBox(Jp2kBox):
    def __init__(self, length=0, offset=-1):
        Jp2kBox.__init__(self, box_id='jP  ', longname='JPEG 2000 Signature')
        self.length = length
        self.offset = offset

    @classmethod
    def parse(cls, fptr, offset, length):
        if fptr.read(4) != b'\x0D\x0A\x87\x0A':
            print('JP2 signature verification failed: ' + fptr.name)
            return None

        return cls(length=length, offset=offset)


class hvFileTypeBox(Jp2kBox):
    def __init__(self, length=0, offset=-1):
        Jp2kBox.__init__(self, box_id='ftyp', longname='File Type')
        self.brand = 'jp2 '
        self.length = length
        self.offset = offset

    @classmethod
    def parse(cls, fptr, offset, length):
        if fptr.read(length - 8) != b'\x6A\x70\x32\x20\x00\x00\x00\x00\x6A\x70\x32\x20':
            print('JP2 file type verification failed: ' + fptr.name)
            return None

        return cls(length=length, offset=offset)


class hvJP2HeaderBox(Jp2kBox):
    def __init__(self, box=None, length=0, offset=-1):
        Jp2kBox.__init__(self, box_id='jp2h', longname='JP2 Header')
        self.length = length
        self.offset = offset
        self.box = box if box is not None else []

    @classmethod
    def parse(cls, fptr, offset, length):
        return cls(length=length, offset=offset)

    def hv_parse(self, fptr):
        fptr.seek(self.offset + 8)
        self.box = self.parse_superbox(fptr)


class hvXMLBox(Jp2kBox):
    def __init__(self, xmlbuf=None, length=0, offset=-1):
        Jp2kBox.__init__(self, box_id='xml ', longname='XML')
        self.xmlbuf = xmlbuf
        self.length = length
        self.offset = offset

    def write(self, fptr):
        fptr.write(self.xmlbuf)

    @classmethod
    def parse(cls, fptr, offset, length):
        # grab entire box
        fptr.seek(offset)
        return cls(xmlbuf=fptr.read(length), length=length, offset=offset)
