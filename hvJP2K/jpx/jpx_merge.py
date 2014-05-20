
# cython: profile=False
# cython: infer_types=True
# cython: boundscheck=False
# cython: wraparound=False

import cython
import struct
import sys

from glymur import jp2box

from ..jp2 import jp2_common
from . import jpx_common, jpx_mmap

# override glymur box parsing
jp2box._BOX_WITH_ID[b'jP  '] = jpx_common.hvJPEG2000SignatureBox()
jp2box._BOX_WITH_ID[b'ftyp'] = jpx_common.hvFileTypeBox()
jp2box._BOX_WITH_ID[b'jp2h'] = jpx_common.hvJP2HeaderBox
jp2box._BOX_WITH_ID[b'xml '] = jpx_common.hvXMLBox
jp2box._BOX_WITH_ID[b'jp2c'] = jpx_common.hvContiguousCodestreamBox


def write_jpch_jplh(jp2h, jpx):
    # write all boxes, could be optimized
    ihdr = jp2_common.first_box(jp2h, 'ihdr')
    colr = jp2_common.first_box(jp2h, 'colr')
    pclr = jp2_common.first_box(jp2h, 'pclr')
    cmap = jp2_common.first_box(jp2h, 'cmap')

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

    struct_pack = struct.pack

    # ftbl with 1 flst with 1 fragment
    ftbl_flst = cython.declare(cython.bytes)
    ftbl_flst = struct_pack('>I4sI4sH', 8 + 8 + 2 + 14, b'ftbl', 8 + 2 + 14, b'flst', 1)

    # typical pattern of empty jpch & jplh
    empty_jpch_jplh = cython.declare(cython.bytes)
    empty_jpch_jplh = struct_pack('>I4sI4s', 8, b'jpch', 8, b'jplh')

    # jpx stream
    jpx = open(jpxname, 'wb')
    jpx_write = jpx.write
    jp2box.JPEG2000SignatureBox().write(jpx)
    jp2box.FileTypeBox(brand='jpx ', compatibility_list=('jpx ', 'jp2 ', 'jpxb')).write(jpx)

    # asoc stream
    asoc = []
    # dtbl stream
    dtbl = []

    head0 = cython.declare(cython.bytes)
    head0 = None

    ifile = cython.declare(jpx_mmap.hvMap)
    ifile = jpx_mmap.hvMap()

    for i in range(num):
        jp2name = cython.declare(cython.bytes)
        jp2name = names_in[i]

        try:
            if ifile.open(jp2name):
                continue

            box = cython.declare(cython.list)
            box = jpx_common.hv_parse_superbox(ifile, 0, ifile.size())

            # failed JP2 signature or file type verification
            if not box or box[0] is None or box[1] is None:
                continue

            jp2h = cython.declare(jpx_common.hvJP2HeaderBox)
            jp2h = jp2_common.first_box(box, 'jp2h')

            xml_ = cython.declare(jpx_common.hvXMLBox)
            xml_ = jp2_common.first_box(box, 'xml ')

            jp2c = cython.declare(jpx_common.hvContiguousCodestreamBox)
            jp2c = jp2_common.first_box(box, 'jp2c')

            # asoc
            if xml_ is not None:
                asoc.append(struct_pack('>I4sI4sII',
                                    # asoc 8 + 16
                                    24 + xml_.length, b'asoc',
                                    # nlst 8 + 4 + 4
                                    16, b'nlst', 0x01000000+i, 0x02000000+i))
                asoc.append(xml_.xmlbuf)

            # identical JP2 header, typical
            if head0 == jp2h.header:
                jpx_write(empty_jpch_jplh)
            else:
                # parse jp2h for validity/access to child boxes
                jp2h_box = jp2h.hv_parse(ifile)

                # first is reference
                if head0 is None:
                    head0 = jp2h.header[:]
                    # write jp2h
                    jpx_write(head0 + empty_jpch_jplh)
                # different size/colour spec
                else:
                    write_jpch_jplh(jp2h_box, jpx)

            if links:
                # ftbl
                jpx_write(ftbl_flst + struct_pack('>QIH', jp2c.offset, jp2c.length, i + 1))

                # dtbl
                url_ = cython.declare(cython.bytes)
                url_ = b'file://' + jp2name + b'\0'
                # 8 + 1 + 1 + 1 + 1
                dtbl.append(struct_pack('>I4sI', 12 + len(url_), b'url ', 0) + url_)
            else:
                # copy jp2c
                jp2c.hv_copy(ifile, jpx)
        finally:
            ifile.close()

    # 8 + asoc size
    asoc_full = b''.join(asoc)
    jpx_write(struct_pack('>I4s', 8 + len(asoc_full), b'asoc'))
    jpx_write(asoc_full)

    if links:
        # 8 + 2 + dtbl size
        dtbl_full = b''.join(dtbl)
        jpx_write(struct_pack('>I4sH', 10 + len(dtbl_full), b'dtbl', len(dtbl)))
        jpx_write(dtbl_full)

    jpx.close()
