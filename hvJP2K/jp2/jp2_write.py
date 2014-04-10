
import os
import sys
import ctypes
import struct
import warnings
from cStringIO import StringIO

# Exitstack not found in contextlib in 2.7
# pylint: disable=E0611
if sys.hexversion >= 0x03030000:
    from contextlib import ExitStack
else:
    from contextlib2 import ExitStack

import numpy as np
from glymur import jp2box
from glymur.lib import openjp2 as opj2
from glymur.core import PROGRESSION_ORDER, GREYSCALE


def hv_write_openjp2(name, img, bpp, xml, **kwargs):

    head = StringIO()

    nrows, ncols = img.shape
    jp2h = jp2box.JP2HeaderBox(
                    box=(jp2box.ImageHeaderBox(height=nrows, width=ncols, bits_per_component=bpp),
                         jp2box.ColourSpecificationBox(colorspace=GREYSCALE)))
    boxes = (jp2box.JPEG2000SignatureBox(), jp2box.FileTypeBox(), jp2h, jp2box.XMLBox(xml))

    for b in boxes:
        b.write(head)
    pos = head.tell()

    __write_openjp2(img, name, pos + 8, comp_prec=bpp, **kwargs)
    head.write(struct.pack('>I4s', os.stat(name).st_size - pos, b'jp2c'))

    with open(name, 'r+b') as ofile:
        ofile.write(head.getvalue())


def __populate_comptparms(img_array, comp_prec, cparams):

    numrows, numcols = img_array.shape
    comptparms = (opj2.ImageComptParmType * 1)()

    comptparms[0].dx = cparams.subsampling_dx
    comptparms[0].dy = cparams.subsampling_dy
    comptparms[0].w = numcols
    comptparms[0].h = numrows
    comptparms[0].x0 = cparams.image_offset_x0
    comptparms[0].y0 = cparams.image_offset_y0
    comptparms[0].prec = comp_prec
    comptparms[0].bpp = 16
    comptparms[0].sgnd = 0

    return comptparms


def __populate_image_struct(image, imgdata, comp_prec, cparams):

    numrows, numcols = imgdata.shape
    # set image offset and reference grid
    image.contents.x0 = cparams.image_offset_x0
    image.contents.y0 = cparams.image_offset_y0
    image.contents.x1 = (image.contents.x0 +
                         (numcols - 1) * cparams.subsampling_dx + 1)
    image.contents.y1 = (image.contents.y0 +
                         (numrows - 1) * cparams.subsampling_dy + 1)

    # Stage the image data to the openjpeg data structure.
    image.contents.comps[0].prec = comp_prec
    image.contents.comps[0].bpp = 16
    image.contents.comps[0].sgnd = 0

    layer = np.ascontiguousarray(imgdata, dtype=np.int32)
    dest = image.contents.comps[0].data
    src = layer.ctypes.data
    ctypes.memmove(dest, src, layer.nbytes)

    return image


def __populate_cparams(**kwargs):

    cparams = opj2.set_default_encoder_parameters()
    cparams.prog_order = PROGRESSION_ORDER['RPCL']
    cparams.codec_fmt = opj2.CODEC_J2K

    # Set defaults to lossless to begin.
    cparams.tcp_rates[0] = 0
    cparams.tcp_numlayers = 1
    cparams.cp_disto_alloc = 1

    if 'irreversible' in kwargs:
        cparams.irreversible = kwargs['irreversible']

    if 'cbsize' in kwargs:
        cparams.cblockw_init = kwargs['cbsize'][1]
        cparams.cblockh_init = kwargs['cbsize'][0]

    if 'cratios' in kwargs:
        cparams.tcp_numlayers = len(kwargs['cratios'])
        for j, cratio in enumerate(kwargs['cratios']):
            cparams.tcp_rates[j] = cratio
        cparams.cp_disto_alloc = 1

    if 'eph' in kwargs:
        cparams.csty |= 0x04

    if 'numres' in kwargs:
        cparams.numresolution = kwargs['numres']

    if 'prog' in kwargs:
        prog = kwargs['prog'].upper()
        cparams.prog_order = PROGRESSION_ORDER[prog]

    if 'psnr' in kwargs:
        cparams.tcp_numlayers = len(kwargs['psnr'])
        for j, snr_layer in enumerate(kwargs['psnr']):
            cparams.tcp_distoratio[j] = snr_layer
        cparams.cp_fixed_quality = 1

    if 'psizes' in kwargs:
        for j, (prch, prcw) in enumerate(kwargs['psizes']):
            cparams.prcw_init[j] = prcw
            cparams.prch_init[j] = prch
        cparams.csty |= 0x01
        cparams.res_spec = len(kwargs['psizes'])

    if 'sop' in kwargs:
        cparams.csty |= 0x02

    return cparams


def __write_openjp2(img_array, filename, offset, comp_prec=8, verbose=False, **kwargs):

    cparams = __populate_cparams(**kwargs)
    comptparms = __populate_comptparms(img_array, comp_prec, cparams)

    with ExitStack() as stack:
        image = opj2.image_create(comptparms, opj2.CLRSPC_GRAY)
        stack.callback(opj2.image_destroy, image)

        __populate_image_struct(image, img_array, comp_prec, cparams)

        codec = opj2.create_compress(cparams.codec_fmt)
        stack.callback(opj2.destroy_codec, codec)

        info_handler = _INFO_CALLBACK if verbose else None
        opj2.set_info_handler(codec, info_handler)
        opj2.set_warning_handler(codec, _WARNING_CALLBACK)
        opj2.set_error_handler(codec, _ERROR_CALLBACK)

        opj2.setup_encoder(codec, cparams, image)

        strm = opj2.stream_create_default_file_stream_v3(filename, False)
        stack.callback(opj2.stream_destroy_v3, strm)

        stream_seek(strm, offset)

        opj2.start_compress(codec, image, strm)
        opj2.encode(codec, strm)
        opj2.end_compress(codec, strm)


from glymur.lib.config import glymur_config
OPENJP2, OPENJPEG = glymur_config()

class OPJStreamPrivate(ctypes.Structure):
    _fields_ = [
        ('m_user_data',          ctypes.c_void_p),
        ('m_free_user_data_fn',  ctypes.c_void_p),
        ('m_user_data_length',   ctypes.c_uint64),
        ('m_read_fn',            ctypes.c_void_p),
        ('m_write_fn',           ctypes.c_void_p),
        ('m_skip_fn',            ctypes.c_void_p),
        ('m_seek_fn',            ctypes.c_void_p)]

def stream_seek(stream, offset):
    strm = ctypes.cast(stream, ctypes.POINTER(OPJStreamPrivate))
    seek = ctypes.cast(strm.contents.m_seek_fn, ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_void_p))

    ARGTYPES = (ctypes.c_int64, ctypes.c_void_p)
    seek.argtypes = ARGTYPES
    seek.restype = ctypes.c_int32
    return seek(offset, strm.contents.m_user_data)

_CMPFUNC = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_char_p, ctypes.c_void_p)

def _default_error_handler(msg, _):
    """Default error handler callback for libopenjp2."""
    msg = "OpenJPEG library error:  {0}".format(msg.decode('utf-8').rstrip())
    opj2.set_error_message(msg)

def _default_info_handler(msg, _):
    """Default info handler callback."""
    print("[INFO] {0}".format(msg.decode('utf-8').rstrip()))

def _default_warning_handler(library_msg, _):
    """Default warning handler callback."""
    library_msg = library_msg.decode('utf-8').rstrip()
    msg = "OpenJPEG library warning:  {0}".format(library_msg)
    warnings.warn(msg)

_ERROR_CALLBACK = _CMPFUNC(_default_error_handler)
_INFO_CALLBACK = _CMPFUNC(_default_info_handler)
_WARNING_CALLBACK = _CMPFUNC(_default_warning_handler)
