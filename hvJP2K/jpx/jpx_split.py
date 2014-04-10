
import sys
import warnings

from glymur import Jp2k, jp2box

from ..jp2.jp2_common import first_box, copy_codestream
import jpx_common


def die(msg):
    warnings.warn(msg, UserWarning)
    sys.exit(1)


def jpx_split(name_in):
    jpx = Jp2k(name_in)

    ftyp = jpx.box[1]
    if ftyp.brand != 'jpx ' or 'jp2 ' not in ftyp.compatibility_list:
        die('The file is not a valid JPX file.')

    jp2h0 = first_box(jpx, b'jp2h')
    jp2c = [x for x in jpx.box if x.box_id == b'jp2c']
    jpch = [x for x in jpx.box if x.box_id == b'jpch']
    jplh = [x for x in jpx.box if x.box_id == b'jplh']
    num = len(jp2c)

    # enforce a jpch and a jplh for each jp2c
    if jp2h0 is None or num == 0 or num != len(jpch) or num != len(jplh):
        die('The file is not a valid JPX file or contains no JP2 codestreams.')

    ihdr0 = first_box(jp2h0, b'ihdr')
    colr0 = first_box(jp2h0, b'colr')
    pclr0 = first_box(jp2h0, b'pclr')
    cmap0 = first_box(jp2h0, b'cmap')

    def jp2h_boxes(jpch, jplh):
        # fish for size/colour boxes in CodestreamHeader and CompositingLayerHeader
        ihdr = first_box(jpch, b'ihdr')
        pclr = first_box(jpch, b'pclr')
        cmap = first_box(jpch, b'cmap')

        cgrp = first_box(jplh, b'cgrp')
        colr = None if cgrp is None else first_box(cgrp, b'colr')

        # replace missing boxes from the main JP2Header
        if ihdr is None: ihdr = ihdr0
        if colr is None: colr = colr0
        if pclr is None: pclr = pclr0
        if cmap is None: cmap = cmap0

        # no mapping or direct mapping
        if cmap is None or sum(cmap.mapping_type) == 0:
            pclr = None
            cmap = None

        return filter(None, (ihdr, colr, pclr, cmap))

    xmls = {}
    asoc_super = first_box(jpx, b'asoc')
    if asoc_super is not None:
        for box in [x for x in asoc_super.box if x.box_id == b'asoc']:
            nlst = first_box(box, b'nlst')
            xml_ = first_box(box, b'xml ')
            if nlst is None or xml_ is None:
                continue

            for asoc in nlst.associations:
                # codestream
                if (asoc >> 24) == 1:
                    xmls[asoc & 0x00FFFFFF] = xml_

    sign = jp2box.JPEG2000SignatureBox()
    ftyp = jp2box.FileTypeBox()
    jp2h = jp2box.JP2HeaderBox()

    for i in range(num):
        name = '{0:03d}'.format(i) + '.jp2'
        with open(name, 'wb') as ofile:
            sign.write(ofile)
            ftyp.write(ofile)

            jp2h.box = jp2h_boxes(jpch[i], jplh[i])
            jp2h.write(ofile)

            if i in xmls:
                xmls[i].write(ofile)

            with open(name_in, 'rb') as ifile:
                copy_codestream(jp2c[i], ifile, ofile)
