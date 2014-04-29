
import struct
import sys

if sys.hexversion >= 0x03000000:
    from io import BytesIO
else:
    from cStringIO import StringIO as BytesIO

from glymur import Jp2k, jp2box

from ..jp2.jp2_common import first_box, copy_codestream, codestream_size
from . import jpx_common

# override some glymur box parsing
jp2box._BOX_WITH_ID[b'ftyp'] = jpx_common.hvFileTypeBox
jp2box._BOX_WITH_ID[b'jp2h'] = jpx_common.hvJP2HeaderBox
jp2box._BOX_WITH_ID[b'xml '] = jpx_common.hvXMLBox


def write_jpch_jplh(jp2h, jpx):
    # write all boxes, could be optimized
    ihdr = first_box(jp2h, 'ihdr')
    colr = first_box(jp2h, 'colr')
    pclr = first_box(jp2h, 'pclr')
    cmap = first_box(jp2h, 'cmap')

    # create direct colour mapping
    if cmap is None:
        num = ihdr.num_components
        cmap = jp2box.ComponentMappingBox(component_index=list(range(num)),
                                          mapping_type=[0]*num,
                                          palette_index=[0]*num)

    boxes = (ihdr, cmap) if pclr is None else (ihdr, pclr, cmap)
    jp2box.CodestreamHeaderBox(box=boxes).write(jpx)

    cgrp = jp2box.ColourGroupBox(box=[colr])
    jp2box.CompositingLayerHeaderBox(box=[cgrp]).write(jpx)


def write_asoc(xmls, jpx):
    num = len(xmls)

    orig_pos = jpx.tell()
    jpx.write(struct.pack('>I4s', 0, b'asoc'))

    for i in range(num):
        if xmls[i] is not None:
            # 8 + 16
            jpx.write(struct.pack('>I4s', 24 + xmls[i].length, b'asoc'))
            # 8 + 4 + 4
            jpx.write(struct.pack('>I4sII', 16, b'nlst', 0x01000000+i, 0x02000000+i))
            jpx.write(xmls[i].xmlbuf)

    end_pos = jpx.tell()
    jpx.seek(orig_pos)
    jpx.write(struct.pack('>I', end_pos - orig_pos))
    jpx.seek(end_pos)


def write_dtbl(files, jpx):
    num = len(files)

    orig_pos = jpx.tell()
    jpx.write(struct.pack('>I4sH', 0, b'dtbl', num))

    for i in range(num):
        url_ = b'file://' + files[i].encode() + b'\0'
        # 8 + 1 + 1 + 1 + 1
        jpx.write(struct.pack('>I4sI', 12 + len(url_), b'url ', 0))
        jpx.write(url_)

    end_pos = jpx.tell()
    jpx.seek(orig_pos)
    jpx.write(struct.pack('>I', end_pos - orig_pos))
    jpx.seek(end_pos)


# @profile
def jpx_merge(names_in, jpxname, links):

    num = len(names_in)

    # ftbl with 1 flst with 1 fragment
    ftbl_flst = struct.pack('>I4sI4sH', 8 + 8 + 2 + 14, b'ftbl', 8 + 2 + 14, b'flst', 1)
    xmls = [None]*num

    # typical pattern of empty jpch, jplh, e.g.
    # jp2box.CodestreamHeaderBox().write(jpx)
    # jp2box.CompositingLayerHeaderBox().write(jpx)
    empty_jpch_jplh = struct.pack('>I4sI4s', 8, b'jpch', 8, b'jplh')

    jpx = BytesIO()
    jp2box.JPEG2000SignatureBox().write(jpx)
    jp2box.FileTypeBox(brand='jpx ', compatibility_list=('jpx ', 'jp2 ', 'jpxb')).write(jpx)

    for i in range(num):
        jp2name = names_in[i]
        jp2 = Jp2k(jp2name)

        jp2h = first_box(jp2, 'jp2h')
        xmls[i] = first_box(jp2, 'xml ')
        jp2c = first_box(jp2, 'jp2c')

        with open(jp2name, 'rb') as ifile:
            ifile.seek(jp2h.offset)
            head = ifile.read(jp2h.length)

            # first is reference
            if i == 0:
                head0 = head
                # parse to ensure validity
                jp2h.hv_parse(ifile)
                # equivalent to jp2h.write(jpx)
                jpx.write(head)
                jpx.write(empty_jpch_jplh)
            # identical JP2 header, typical
            elif head0 == head:
                jpx.write(empty_jpch_jplh)
            # different size/colour spec
            else:
                # enable access to jp2h child boxes
                jp2h.hv_parse(ifile)
                write_jpch_jplh(jp2h, jpx)

            if links:
                jpx.write(ftbl_flst)
                offset, length = codestream_size(jp2c)
                jpx.write(struct.pack('>QIH', offset, length, i + 1))
            else:
                copy_codestream(jp2c, ifile, jpx)

    write_asoc(xmls, jpx)

    if links:
        write_dtbl(names_in, jpx)

    with open(jpxname, 'wb') as ofile:
        ofile.write(jpx.getvalue())
