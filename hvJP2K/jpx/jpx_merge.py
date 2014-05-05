
import os
import struct
import sys

if sys.hexversion >= 0x03000000:
    from io import BytesIO
else:
    from cStringIO import StringIO as BytesIO

from glymur import jp2box

from ..jp2.jp2_common import first_box
from . import jpx_common

# override glymur box parsing
jp2box._BOX_WITH_ID[b'jP  '] = jpx_common.hvJPEG2000SignatureBox()
jp2box._BOX_WITH_ID[b'ftyp'] = jpx_common.hvFileTypeBox()
jp2box._BOX_WITH_ID[b'jp2h'] = jpx_common.hvJP2HeaderBox
jp2box._BOX_WITH_ID[b'xml '] = jpx_common.hvXMLBox
jp2box._BOX_WITH_ID[b'jp2c'] = jpx_common.hvContiguousCodestreamBox

def _first_box(boxes, box_id):
    for box in boxes:
        if box.box_id == box_id:
            return box
    return None

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


# @profile
def jpx_merge(names_in, jpxname, links):

    num = len(names_in)

    # ftbl with 1 flst with 1 fragment
    ftbl_flst = struct.pack('>I4sI4sH', 8 + 8 + 2 + 14, b'ftbl', 8 + 2 + 14, b'flst', 1)

    # typical pattern of empty jpch & jplh
    empty_jpch_jplh = struct.pack('>I4sI4s', 8, b'jpch', 8, b'jplh')

    # jpx stream
    jpx = BytesIO()
    jp2box.JPEG2000SignatureBox().write(jpx)
    jp2box.FileTypeBox(brand='jpx ', compatibility_list=('jpx ', 'jp2 ', 'jpxb')).write(jpx)

    # asoc stream
    asoc = BytesIO()
    asoc.write(struct.pack('>4s', b'asoc'))

    # dtbl stream
    dtbl = BytesIO()
    dtbl.write(struct.pack('>4sH', b'dtbl', num)) # failed verification ?

    head0 = None

    for i in range(num):
        jp2name = names_in[i]

        with open(jp2name, 'rb') as ifile:
            box = jp2box.Jp2kBox('', 0, os.path.getsize(jp2name)).parse_superbox(ifile)

            # failed JP2 signature or file type verification
            if box[0] is None or box[1] is None:
                continue

            jp2h = _first_box(box, 'jp2h')
            xml_ = _first_box(box, 'xml ')
            jp2c = _first_box(box, 'jp2c')

            # asoc
            if xml_ is not None:
                # 8 + 16
                asoc.write(struct.pack('>I4s', 24 + xml_.length, b'asoc'))
                # 8 + 4 + 4
                asoc.write(struct.pack('>I4sII', 16, b'nlst', 0x01000000+i, 0x02000000+i))
                asoc.write(xml_.xmlbuf)

            # first is reference
            if head0 is None:
                # parse jp2h to ensure validity
                jp2h.hv_parse(ifile)

                # write jp2h
                head0 = jp2h.header[:]
                jpx.write(head0)

                jpx.write(empty_jpch_jplh)
            # identical JP2 header, typical
            elif head0 == jp2h.header:
                jpx.write(empty_jpch_jplh)
            # different size/colour spec
            else:
                # enable access to jp2h child boxes
                jp2h.hv_parse(ifile)
                write_jpch_jplh(jp2h, jpx)

            if links:
                # ftbl
                jpx.write(ftbl_flst)
                jpx.write(struct.pack('>QIH', jp2c.offset, jp2c.length, i + 1))

                # dtbl
                url_ = b'file://' + jp2name.encode() + b'\0'
                # 8 + 1 + 1 + 1 + 1
                dtbl.write(struct.pack('>I4sI', 12 + len(url_), b'url ', 0))
                dtbl.write(url_)
            else:
                # copy jp2c
                jp2c.hv_copy(ifile, jpx)

    with open(jpxname, 'wb') as ofile:
        ofile.write(jpx.getvalue())

        # asoc size + length field
        ofile.write(struct.pack('>I', asoc.tell() + 4))
        ofile.write(asoc.getvalue())

        if links:
            # dtbl size + length field
            ofile.write(struct.pack('>I', dtbl.tell() + 4))
            ofile.write(dtbl.getvalue())
