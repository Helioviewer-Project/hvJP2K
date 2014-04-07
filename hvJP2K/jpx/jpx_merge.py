
import warnings
from glymur import Jp2k
from glymur.jp2box import *

from jpx_common import *

def jpx_merge(names_in, name_out, links):
    asoc = AssociationBox()
    ftbl = FragmentTableBox()
    dtbl = DataReferenceBox()

    with open(name_out, 'wb') as ofile:
        JPEG2000SignatureBox().write(ofile)
        FileTypeBox(brand='jpx ', compatibility_list=('jpx ', 'jp2 ', 'jpxb')).write(ofile)

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
                    # CodestreamHeaderBox().write(ofile)
                    # CompositingLayerHeaderBox().write(ofile)
                    ofile.write(struct.pack('>I4sI4s', 8, b'jpch', 8, b'jplh'))
                elif head0 == head:  # identical JP2 header
                    # CodestreamHeaderBox().write(ofile)
                    # CompositingLayerHeaderBox().write(ofile)
                    ofile.write(struct.pack('>I4sI4s', 8, b'jpch', 8, b'jplh'))
                else:  # different size/colour spec
                    # write all boxes, could be optimized
                    ihdr = first_box(jp2h, b'ihdr')
                    colr = first_box(jp2h, b'colr')
                    pclr = first_box(jp2h, b'pclr')
                    cmap = first_box(jp2h, b'cmap')

                    if cmap is None:  # create direct colour mapping
                        num = ihdr.num_components
                        cmap = ComponentMappingBox(component_index=range(num), mapping_type=(0,)*num, palette_index=(0,)*num)

                    boxes = (ihdr, cmap) if pclr is None else (ihdr, pclr, cmap)
                    CodestreamHeaderBox(box=boxes).write(ofile)

                    cgrp = ColourGroupBox(box=(colr,))
                    CompositingLayerHeaderBox(box=(cgrp,)).write(ofile)

                if links:
                    ftbl.box = (FragmentListBox((jp2c.offset,), (jp2c.length,), (i+1,)),)
                    ftbl.write(ofile)

                    url_ = DataEntryURLBox(0, (0, 0, 0),
                               'file://' + os.path.abspath(names_in[i]) + chr(0))  # null terminated
                    dtbl.DR.append(url_)
                else:
                    jp2c.write(ifile, ofile)

            if xml_:
                nlst = NumberListBox(associations=(0x01000000+i, 0x02000000+i))  # codestream, compositing layer
                asocj = AssociationBox(box=(nlst, xml_))
                asoc.box.append(asocj)
            else:
                msg = 'JP2 file ' + names_in[i] + ' contains no XML box.'
                warnings.warn(msg, UserWarning)

        asoc.write(ofile)

        if links:
            dtbl.write(ofile)
