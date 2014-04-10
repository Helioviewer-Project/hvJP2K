
import os
import struct
import warnings

from glymur import Jp2k, jp2box

from ..jp2.jp2_common import first_box, copy_codestream, codestream_size
import jpx_common


def jpx_merge(names_in, name_out, links):
    asoc = jp2box.AssociationBox()
    ftbl = jp2box.FragmentTableBox()
    dtbl = jp2box.DataReferenceBox()

    with open(name_out, 'wb') as ofile:
        jp2box.JPEG2000SignatureBox().write(ofile)
        jp2box.FileTypeBox(brand='jpx ', compatibility_list=('jpx ', 'jp2 ', 'jpxb')).write(ofile)

        for i in range(len(names_in)):
            jp2 = Jp2k(names_in[i])

            jp2h = first_box(jp2, b'jp2h')
            xml_ = first_box(jp2, b'xml ')
            jp2c = first_box(jp2, b'jp2c')

            with open(names_in[i], 'rb') as ifile:
                ifile.seek(jp2h.offset)
                head = ifile.read(jp2h.length)

                if i == 0:  # reference first
                    head0 = head
                    # jp2h.write(ofile)
                    ofile.write(head)
                    # jp2box.CodestreamHeaderBox().write(ofile)
                    # jp2box.CompositingLayerHeaderBox().write(ofile)
                    ofile.write(struct.pack('>I4sI4s', 8, b'jpch', 8, b'jplh'))
                elif head0 == head:  # identical JP2 header
                    # jp2box.CodestreamHeaderBox().write(ofile)
                    # jp2box.CompositingLayerHeaderBox().write(ofile)
                    ofile.write(struct.pack('>I4sI4s', 8, b'jpch', 8, b'jplh'))
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
                    jp2box.CodestreamHeaderBox(box=boxes).write(ofile)

                    cgrp = jp2box.ColourGroupBox(box=(colr,))
                    jp2box.CompositingLayerHeaderBox(box=(cgrp,)).write(ofile)

                if links:
                    offset, length = codestream_size(jp2c)
                    ftbl.box = (jp2box.FragmentListBox((offset,), (length,), (i+1,)),)
                    ftbl.write(ofile)

                    # I.7.3.2: null terminated
                    url_ = jp2box.DataEntryURLBox(0, (0, 0, 0),
                                                  'file://'+os.path.abspath(names_in[i])+chr(0))
                    dtbl.DR.append(url_)
                else:
                    copy_codestream(jp2c, ifile, ofile)

            if xml_ is not None:
                # codestream, compositing layer
                nlst = jp2box.NumberListBox(associations=(0x01000000+i, 0x02000000+i))
                asocj = jp2box.AssociationBox(box=(nlst, xml_))
                asoc.box.append(asocj)
            else:
                msg = 'JP2 file ' + names_in[i] + ' contains no XML box.'
                warnings.warn(msg, UserWarning)

        asoc.write(ofile)

        if links:
            dtbl.write(ofile)
