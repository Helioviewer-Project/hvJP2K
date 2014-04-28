
import struct


def first_box(sup, box_id):
    return next((x for x in sup.box if x.box_id == box_id), None)


def codestream_size(jp2c):
    offset = jp2c.main_header_offset
    length = jp2c.length + jp2c.offset - offset

    return (offset, length)


def copy_codestream(jp2c, ifile, ofile):
    offset, length = codestream_size(jp2c)

    ifile.seek(offset)
    ofile.write(struct.pack('>I4s', length + 8, b'jp2c'))
    ofile.write(ifile.read(length))
