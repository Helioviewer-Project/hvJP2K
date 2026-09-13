from os import stat
import sys
import warnings

from glymur import jp2box

from ..jp2.jp2_common import first_box
from . import jpx_common

# override some glymur box parsing
jp2box._BOX_WITH_ID[b"jp2h"] = jpx_common.hvJP2HeaderBox
jp2box._BOX_WITH_ID[b"xml "] = jpx_common.hvXMLBox
jp2box._BOX_WITH_ID[b"jp2c"] = jpx_common.hvContiguousCodestreamBox


def die(msg):
    warnings.warn(msg, UserWarning)
    sys.exit(1)


def jpx_split(jpxname):

    with open(jpxname, "rb") as ifile:
        jpx = jpx_common.hv_parse_superbox(ifile, 0, stat(jpxname).st_size)

        if len(jpx) < 2 or jpx[0] is None or jpx[1] is None:
            die("File is not a valid JPX file: " + jpxname)

        ftyp = jpx[1]
        if (
            ftyp.box_id != "ftyp"
            or ftyp.brand != "jpx "
            or "jp2 " not in ftyp.compatibility_list
        ):
            die("File is not a valid JPX file: " + jpxname)

        jp2h0 = first_box(jpx, "jp2h")
        jp2c = [x for x in jpx if x.box_id == "jp2c"]
        jpch = [x for x in jpx if x.box_id == "jpch"]
        jplh = [x for x in jpx if x.box_id == "jplh"]
        num = len(jp2c)

        # enforce a jpch and a jplh for each jp2c
        if jp2h0 is None or num == 0 or num != len(jpch) or num != len(jplh):
            die("The file is not a valid JPX file or contains no JP2 codestreams.")

        jp2h0 = jp2h0.hv_parse(ifile)
        ihdr0 = first_box(jp2h0, "ihdr")
        bpcc0 = first_box(jp2h0, "bpcc")
        colr0 = [box for box in jp2h0 if box.box_id == "colr"]
        pclr0 = first_box(jp2h0, "pclr")
        cmap0 = first_box(jp2h0, "cmap")
        cdef0 = first_box(jp2h0, "cdef")
        res0 = first_box(jp2h0, "res ")

        def jp2h_boxes(jpch, jplh):
            # fish for size/colour boxes in jpch and jplh
            ihdr = first_box(jpch, "ihdr")
            bpcc = first_box(jpch, "bpcc")
            pclr = first_box(jpch, "pclr")
            cmap = first_box(jpch, "cmap")

            cgrp = first_box(jplh, "cgrp")
            colr = (
                []
                if cgrp is None
                else [box for box in cgrp.box if box.box_id == "colr"]
            )
            cdef = first_box(jplh, "cdef")
            res = first_box(jplh, "res ")

            # replace missing boxes from the main jp2h
            if ihdr is None:
                ihdr = ihdr0
            if bpcc is None:
                bpcc = bpcc0
            if not colr:
                colr = colr0
            if pclr is None:
                pclr = pclr0
            if cmap is None:
                cmap = cmap0
            if cdef is None:
                cdef = cdef0
            if res is None:
                res = res0

            # no mapping or direct mapping
            if cmap is None or sum(cmap.mapping_type) == 0:
                pclr = None
                cmap = None

            colr = [
                jp2box.ColourSpecificationBox(
                    method=box.method,
                    precedence=box.precedence,
                    approximation=0,
                    colorspace=box.colorspace,
                    icc_profile=box.icc_profile,
                )
                for box in colr
            ]
            return (
                [box for box in (ihdr, bpcc) if box is not None]
                + colr
                + [box for box in (pclr, cmap, cdef, res) if box is not None]
            )

        xmls = [None] * num

        def read_associations(boxes):
            for box in boxes:
                if box.box_id != "asoc":
                    continue
                nlst = first_box(box.box, "nlst")
                xml_ = first_box(box.box, "xml ")
                if nlst is not None and xml_ is not None:
                    for idx in nlst.associations:
                        if (idx >> 24) == 1:
                            codestream_index = idx & 0x00FFFFFF
                            if codestream_index >= num:
                                die("JPX metadata refers to a missing codestream.")
                            xmls[codestream_index] = xml_.xmlbuf
                else:
                    read_associations(box.box)

        read_associations(jpx)

        sign = jp2box.JPEG2000SignatureBox()
        ftyp = jp2box.FileTypeBox()
        jp2h = jp2box.JP2HeaderBox()

        for i in range(num):
            jp2name = "{0:03d}".format(i) + ".jp2"
            with open(jp2name, "wb") as ofile:
                sign.write(ofile)
                ftyp.write(ofile)

                jp2h.box = jp2h_boxes(jpch[i].box, jplh[i].box)
                jp2h.write(ofile)

                if xmls[i] is not None:
                    ofile.write(xmls[i])

                jp2c[i].hv_copy(ifile, ofile)
