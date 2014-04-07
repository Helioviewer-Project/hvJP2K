
import struct
from glymur.jp2box import Jp2kBox

def first_box(sup, box_id):
    return next((x for x in sup.box if x.box_id == box_id), None)

class hvXMLBox(Jp2kBox):
    def __init__(self, buffer=None, length=0, offset=-1):
        Jp2kBox.__init__(self, box_id='xml ', longname='XML')
        self.buffer = buffer
        self.length = length
        self.offset = offset

    def write(self, fptr):
        fptr.write(self.buffer)

    @classmethod
    def parse(cls, fptr, offset, length):
        # grab entire box
        fptr.seek(offset)
        return cls(buffer=fptr.read(length), length=length, offset=offset)

class hvContiguousCodestreamBox(Jp2kBox):
    def __init__(self, length=0, offset=-1):
        Jp2kBox.__init__(self, box_id='jp2c', longname='Contiguous Codestream')
        self.length = length
        self.offset = offset

    def write(self, ifile, ofile):
        ifile.seek(self.offset)
        ofile.write(struct.pack('>I4s', self.length + 8, b'jp2c'))
        ofile.write(ifile.read(self.length))

    @classmethod
    def parse(cls, fptr, offset, length):
        # true offset if box was encoded with extended length
        off = fptr.tell()
        length += offset - off

        return cls(length=length, offset=off)
