
import numpy as np
from glymur import Jp2k
from glymur.lib import openjp2 as opj2
from lxml import etree as et
from PIL import Image

from .jp2_common import first_box


if opj2.OPENJP2 is None:
    raise RuntimeError('You must have at least version 2 of OpenJPEG before using this program.')


def jp2_decode(name_in, name_out, xml=False, rlevel=0, area=None,
               ignore_pclr_cmap_cdef=False, verbose=False):

    jp2 = Jp2k(name_in)

    xml_ = first_box(jp2.box, 'xml ')
    if xml and xml_ is not None:
        print(et.tostring(xml_.xml, encoding='unicode'))

    code = jp2.get_codestream()
    xsiz = code.segment[1].xsiz
    ysiz = code.segment[1].ysiz

    if area is not None:
        # to pixels
        area = [np.clip(n, 0, 1) for n in area]
        area[0] *= ysiz
        area[1] *= xsiz
        area[2] *= ysiz
        area[3] *= xsiz
        area = [int(n + .5) for n in area]

    rlevel = int(np.clip(rlevel, 0, code.segment[2].num_res))

    jp2.verbose = verbose
    jp2.ignore_pclr_cmap_cdef = ignore_pclr_cmap_cdef
    step = 1 << rlevel
    if area is None:
        data = jp2[::step, ::step]
    else:
        data = jp2[area[0]:area[2]:step, area[1]:area[3]:step]
    Image.fromarray(data).save(name_out)
