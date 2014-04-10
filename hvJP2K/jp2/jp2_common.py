
import struct

from glymur.jp2box import Jp2kBox, ContiguousCodestreamBox


def first_box(sup, box_id):
    return next((x for x in sup.box if x.box_id == box_id), None)


def copy_codestream(box, ifile, ofile):
    if isinstance(box, ContiguousCodestreamBox):
        offset = box.main_header_offset
        length = box.length + box.offset - offset

        ifile.seek(offset)
        ofile.write(struct.pack('>I4s', length + 8, b'jp2c'))
        ofile.write(ifile.read(length))


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
