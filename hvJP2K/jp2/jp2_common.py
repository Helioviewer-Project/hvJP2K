
import struct


def first_box(sup, box_id):
    for box in sup.box:
        if box.box_id == box_id:
            return box

    return None


def codestream_size(jp2c):
    offset = jp2c.main_header_offset
    length = jp2c.length + jp2c.offset - offset

    return (offset, length)


def copy_codestream(jp2c, ifile, ofile):
    offset, length = codestream_size(jp2c)

    ifile.seek(offset)
    ofile.write(struct.pack('>I4s', length + 8, b'jp2c'))
    ofile.write(ifile.read(length))
