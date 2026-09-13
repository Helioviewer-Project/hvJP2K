from glymur import Jp2k
from lxml import etree as et
from PIL import Image

from .jp2_common import first_box, require_openjpeg


def jp2_decode(
    name_in,
    name_out,
    xml=False,
    rlevel=0,
    area=None,
    ignore_pclr_cmap_cdef=False,
    verbose=False,
):

    require_openjpeg()
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
    nrows, ncols = jp2.shape[:2]

    if area is not None:
        # to pixels
        area = [min(1, max(0, value)) for value in area]
        area[0] *= nrows
        area[1] *= ncols
        area[2] *= nrows
        area[3] *= ncols
        area = [int(n + 0.5) for n in area]

    rlevel = min(cod.num_res, max(0, rlevel))

    jp2.verbose = verbose
    jp2.ignore_pclr_cmap_cdef = ignore_pclr_cmap_cdef
    step = 1 << rlevel
    if area is None:
        data = jp2[::step, ::step]
    else:
        data = jp2[area[0] : area[2] : step, area[1] : area[3] : step]
    Image.fromarray(data).save(name_out)
