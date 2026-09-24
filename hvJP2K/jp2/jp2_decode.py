import math
from pathlib import Path

from glymur import Jp2k, get_option, set_option
from lxml import etree as et
from PIL import Image

from .jp2_common import MAX_THREADS, first_box, require_openjpeg


def jp2_decode(
    name_in,
    name_out=None,
    xml=False,
    rlevel=0,
    area=None,
    ignore_pclr_cmap_cdef=False,
    record=None,
    threads=1,
    verbose=False,
):

    if not 1 <= threads <= MAX_THREADS:
        raise ValueError(f"threads must be between 1 and {MAX_THREADS}")
    require_openjpeg()
    if threads != get_option("lib.num_threads"):
        set_option("lib.num_threads", threads)
    jp2 = Jp2k(name_in)

    xml_ = first_box(jp2.box, "xml ")
    if xml and xml_ is not None:
        print(et.tostring(xml_.xml, encoding="unicode"))

    code = jp2.get_codestream()
    cod = next(
        (segment for segment in code.segment if segment.marker_id == "COD"), None
    )
    if cod is None:
        raise ValueError("JPEG 2000 codestream has no COD marker")

    if record is not None:
        Path(record).write_text(f"Clevels={cod.num_res}\n", encoding="ascii")
    if name_out is None:
        return

    nrows, ncols = jp2.shape[:2]

    if area is not None:
        # Kakadu's -region rounds the upper left down and the lower right up.
        top, left, bottom, right = area
        area = [
            max(0, min(nrows, math.floor(top * nrows))),
            max(0, min(ncols, math.floor(left * ncols))),
            max(0, min(nrows, math.ceil(bottom * nrows))),
            max(0, min(ncols, math.ceil(right * ncols))),
        ]

    rlevel = min(cod.num_res, max(0, rlevel))

    jp2.verbose = verbose
    jp2.ignore_pclr_cmap_cdef = ignore_pclr_cmap_cdef
    step = 1 << rlevel
    if area is None:
        data = jp2[::step, ::step]
    else:
        data = jp2[area[0] : area[2] : step, area[1] : area[3] : step]

    Image.fromarray(data).save(name_out)
