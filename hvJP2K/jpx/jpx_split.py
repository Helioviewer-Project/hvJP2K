
import os
import sys
import warnings

if sys.hexversion >= 0x03000000:
    from io import BytesIO
else:
    from cStringIO import StringIO as BytesIO

from glymur import jp2box

from ..jp2.jp2_common import first_box
from . import jpx_common

# override some glymur box parsing
jp2box._BOX_WITH_ID[b'jp2h'] = jpx_common.hvJP2HeaderBox
jp2box._BOX_WITH_ID[b'xml '] = jpx_common.hvXMLBox
jp2box._BOX_WITH_ID[b'jp2c'] = jpx_common.hvContiguousCodestreamBox

def die(msg):
    warnings.warn(msg, UserWarning)
    sys.exit(1)


def jpx_split(jpxname):

    with open(jpxname, 'rb') as ifile:
        jpx = jpx_common.hv_parse_superbox(ifile, 0, os.stat(jpxname).st_size)

        ftyp = jpx[1]
        if ftyp.brand != 'jpx ' or 'jp2 ' not in ftyp.compatibility_list:
            die('File is not a valid JPX file: ' + jpxname)

        jp2h0 = first_box(jpx, 'jp2h')
        jp2c = [x for x in jpx if x.box_id == 'jp2c']
        jpch = [x for x in jpx if x.box_id == 'jpch']
        jplh = [x for x in jpx if x.box_id == 'jplh']
        num = len(jp2c)

        # enforce a jpch and a jplh for each jp2c
        if jp2h0 is None or num == 0 or num != len(jpch) or num != len(jplh):
            die('The file is not a valid JPX file or contains no JP2 codestreams.')

        jp2h0 = jp2h0.hv_parse(ifile)
        ihdr0 = first_box(jp2h0, 'ihdr')
        colr0 = first_box(jp2h0, 'colr')
        pclr0 = first_box(jp2h0, 'pclr')
        cmap0 = first_box(jp2h0, 'cmap')

        def jp2h_boxes(jpch, jplh):
            # fish for size/colour boxes in jpch and jplh
            ihdr = first_box(jpch, 'ihdr')
            pclr = first_box(jpch, 'pclr')
            cmap = first_box(jpch, 'cmap')

            cgrp = first_box(jplh, 'cgrp')
            colr = None if cgrp is None else first_box(cgrp.box, 'colr')

            # replace missing boxes from the main jp2h
            if ihdr is None: ihdr = ihdr0
            if colr is None: colr = colr0
            if pclr is None: pclr = pclr0
            if cmap is None: cmap = cmap0

            # no mapping or direct mapping
            if cmap is None or sum(cmap.mapping_type) == 0:
                pclr = None
                cmap = None

            return [box for box in (ihdr, colr, pclr, cmap) if box is not None]

        xmls = [None]*num
        asoc_super = first_box(jpx, 'asoc')
        if asoc_super is not None:
            asoc = [x.box for x in asoc_super.box if x.box_id == 'asoc']
            for box in asoc:
                nlst = first_box(box, 'nlst')
                xml_ = first_box(box, 'xml ')
                if nlst is None or xml_ is None:
                    continue

                for idx in nlst.associations:
                    # codestream
                    if (idx >> 24) == 1:
                        xmls[idx & 0x00FFFFFF] = xml_.xmlbuf

        sign = jp2box.JPEG2000SignatureBox()
        ftyp = jp2box.FileTypeBox()
        jp2h = jp2box.JP2HeaderBox()

        for i in range(num):
            jp2 = BytesIO()
            sign.write(jp2)
            ftyp.write(jp2)

            jp2h.box = jp2h_boxes(jpch[i].box, jplh[i].box)
            jp2h.write(jp2)

            if xmls[i] is not None:
                jp2.write(xmls[i])

            jp2c[i].hv_copy(ifile, jp2)

            jp2name = '{0:03d}'.format(i) + '.jp2'
            with open(jp2name, 'wb') as ofile:
                ofile.write(jp2.getvalue())
