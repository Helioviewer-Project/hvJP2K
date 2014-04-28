
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

# @profile
def jpx_merge(names_in, jpxname, links):

    jp2num = len(names_in)

    flst = jp2box.FragmentListBox([1], [1], [1])
    ftbl = struct.pack('>I4s', 0, b'ftbl')
    xmls = [None]*jp2num

    # typical pattern of empty jpch, jplh, e.g.
    # jp2box.CodestreamHeaderBox().write(jpx)
    # jp2box.CompositingLayerHeaderBox().write(jpx)
    jpch_jplh = struct.pack('>I4sI4s', 8, b'jpch', 8, b'jplh')

    jpx = BytesIO()
    jp2box.JPEG2000SignatureBox().write(jpx)
    jp2box.FileTypeBox(brand='jpx ', compatibility_list=('jpx ', 'jp2 ', 'jpxb')).write(jpx)

    for i in range(jp2num):
        jp2name = names_in[i]
        jp2 = Jp2k(jp2name)

        jp2h = first_box(jp2, 'jp2h')
        xmls[i] = first_box(jp2, 'xml ')
        jp2c = first_box(jp2, 'jp2c')

        with open(jp2name, 'rb') as ifile:
            ifile.seek(jp2h.offset)
            head = ifile.read(jp2h.length)

            if i == 0:  # reference first
                head0 = head
                # parse to ensure validity
                jp2h.hv_parse(ifile)
                # jp2h.write(jpx)
                jpx.write(head)
                jpx.write(jpch_jplh)
            elif head0 == head:  # identical JP2 header, typical
                jpx.write(jpch_jplh)
            else:  # different size/colour spec
                # parse to access child boxes
                jp2h.hv_parse(ifile)
                # write all boxes, could be optimized
                ihdr = first_box(jp2h, 'ihdr')
                colr = first_box(jp2h, 'colr')
                pclr = first_box(jp2h, 'pclr')
                cmap = first_box(jp2h, 'cmap')

                if cmap is None:  # create direct colour mapping
                    num = ihdr.num_components
                    cmap = jp2box.ComponentMappingBox(component_index=list(range(num)),
                                                      mapping_type=(0,)*num,
                                                      palette_index=(0,)*num)

                boxes = (ihdr, cmap) if pclr is None else (ihdr, pclr, cmap)
                jp2box.CodestreamHeaderBox(box=boxes).write(jpx)

                cgrp = jp2box.ColourGroupBox(box=(colr,))
                jp2box.CompositingLayerHeaderBox(box=(cgrp,)).write(jpx)

            if links:
                orig_pos = jpx.tell()
                jpx.write(ftbl)

                flst.fragment_offset[0], flst.fragment_length[0] = codestream_size(jp2c)
                flst.data_reference[0] = i + 1
                flst.write(jpx)

                end_pos = jpx.tell()
                jpx.seek(orig_pos)
                jpx.write(struct.pack('>I', end_pos - orig_pos))
                jpx.seek(end_pos)
            else:
                copy_codestream(jp2c, ifile, jpx)

    # write 'asoc' box manually to avoid object creation overhead
    orig_pos = jpx.tell()
    jpx.write(struct.pack('>I4s', 0, b'asoc'))

    nlst = jp2box.NumberListBox(associations=[0, 0])
    asoc = jp2box.AssociationBox(box=[nlst, None])
    for i in range(jp2num):
        if xmls[i] is not None:
            nlst.associations[0] = 0x01000000+i
            nlst.associations[1] = 0x02000000+i
            asoc.box[1] = xmls[i]
            asoc.write(jpx)

    end_pos = jpx.tell()
    jpx.seek(orig_pos)
    jpx.write(struct.pack('>I', end_pos - orig_pos))
    jpx.seek(end_pos)

    if links:
        # write 'dtbl' box manually to avoid object creation overhead
        url_ = jp2box.DataEntryURLBox(0, (0, 0, 0), None)

        orig_pos = jpx.tell()
        jpx.write(struct.pack('>I4sH', 0, b'dtbl', jp2num))

        for i in range(jp2num):
            url_.url = 'file://'+names_in[i]+chr(0)
            url_.write(jpx)

        end_pos = jpx.tell()
        jpx.seek(orig_pos)
        jpx.write(struct.pack('>I', end_pos - orig_pos))
        jpx.seek(end_pos)

    with open(jpxname, 'wb') as ofile:
        ofile.write(jpx.getvalue())
