
import glymur
from glymur.jp2box import Jp2kBox

# do not parse the codestreams
glymur.set_parseoptions(codestream=False)


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


class hvJP2HeaderBox(Jp2kBox):
    def __init__(self, box=None, length=0, offset=-1):
        Jp2kBox.__init__(self, box_id='jp2h', longname='JP2 Header')
        self.length = length
        self.offset = offset
        self.box = box if box is not None else []

    '''
    def write(self, fptr):
        self._write_superbox(fptr, b'jp2h')
    '''

    @classmethod
    def parse(cls, fptr, offset, length):
        return cls(length=length, offset=offset)

    def hv_parse(self, fptr):
        fptr.seek(self.offset + 8)
        self.box = self.parse_superbox(fptr)


class hvFileTypeBox(Jp2kBox):
    def __init__(self, brand='jp2 ', minor_version=0,
                 compatibility_list=None, length=0, offset=-1):
        Jp2kBox.__init__(self, box_id='ftyp', longname='File Type')
        self.brand = brand
        self.minor_version = minor_version
        if compatibility_list is None:
            self.compatibility_list = ['jp2 ']
        else:
            self.compatibility_list = compatibility_list
        self.length = length
        self.offset = offset

    @classmethod
    def parse(cls, fptr, offset, length):
        return cls(length=length, offset=offset)
