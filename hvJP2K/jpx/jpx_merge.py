
import os
import struct
from cStringIO import StringIO

from glymur import Jp2k, jp2box

from ..jp2.jp2_common import first_box, copy_codestream, codestream_size
import jpx_common


def jpx_merge(names_in, jpxname, links):

    jp2num = len(names_in)

    ftbl = jp2box.FragmentTableBox(box=[jp2box.FragmentListBox([1], [1], [1])])
    asoc = [jp2box.AssociationBox(box=[jp2box.NumberListBox(associations=(0x01000000+i, 0x02000000+i)), None]) for i in range(jp2num)]

    # The typical pattern of empty jpch, jplh, e.g.
    # jp2box.CodestreamHeaderBox().write(jpx)
    # jp2box.CompositingLayerHeaderBox().write(jpx)
    jpch_jplh = struct.pack('>I4sI4s', 8, b'jpch', 8, b'jplh')

    jpx = StringIO()
    jp2box.JPEG2000SignatureBox().write(jpx)
    jp2box.FileTypeBox(brand='jpx ', compatibility_list=('jpx ', 'jp2 ', 'jpxb')).write(jpx)

    for i in range(jp2num):
        jp2name = names_in[i]
        jp2 = Jp2k(jp2name)

        jp2h = first_box(jp2, b'jp2h')
        asoc[i].box[1] = first_box(jp2, b'xml ')
        jp2c = first_box(jp2, b'jp2c')

        with open(jp2name, 'rb') as ifile:
            ifile.seek(jp2h.offset)
            head = ifile.read(jp2h.length)

            if i == 0:  # reference first
                head0 = head
                # jp2h.write(jpx)
                jpx.write(head)
                jpx.write(jpch_jplh)
            elif head0 == head:  # identical JP2 header, typical
                jpx.write(jpch_jplh)
            else:  # different size/colour spec
                # write all boxes, could be optimized
                ihdr = first_box(jp2h, b'ihdr')
                colr = first_box(jp2h, b'colr')
                pclr = first_box(jp2h, b'pclr')
                cmap = first_box(jp2h, b'cmap')

                if cmap is None:  # create direct colour mapping
                    num = ihdr.num_components
                    cmap = jp2box.ComponentMappingBox(component_index=range(num),
                                                      mapping_type=(0,)*num,
                                                      palette_index=(0,)*num)

                boxes = (ihdr, cmap) if pclr is None else (ihdr, pclr, cmap)
                jp2box.CodestreamHeaderBox(box=boxes).write(jpx)

                cgrp = jp2box.ColourGroupBox(box=(colr,))
                jp2box.CompositingLayerHeaderBox(box=(cgrp,)).write(jpx)

            if links:
                offset, length = codestream_size(jp2c)
                ftbl.box[0].fragment_offset[0] = offset
                ftbl.box[0].fragment_length[0] = length
                ftbl.box[0].data_reference[0] = i + 1
                ftbl.write(jpx)
            else:
                copy_codestream(jp2c, ifile, jpx)

    jp2box.AssociationBox(box=[box for box in asoc if box.box[1] is not None]).write(jpx)

    if links:
        # I.7.3.2: null terminated
        url_ = [jp2box.DataEntryURLBox(0, (0, 0, 0), 'file://'+os.path.abspath(names_in[i])+chr(0)) for i in range(jp2num)]
        jp2box.DataReferenceBox(data_entry_url_boxes=url_).write(jpx)

    with open(jpxname, 'wb') as ofile:
        ofile.write(jpx.getvalue())
