
# cython: profile=False
# cython: infer_types=True
# cython: boundscheck=False
# cython: wraparound=False

import cython
from hvJP2K.jpx cimport jpx_common as jpx_common_c

from io import BytesIO
import os
import struct
from pathlib import Path

from glymur import jp2box

from ..jp2 import jp2_common
from . import jpx_common

# override glymur box parsing
jp2box._BOX_WITH_ID[b'jP  '] = jpx_common.hvJPEG2000SignatureBox()
jp2box._BOX_WITH_ID[b'ftyp'] = jpx_common.hvFileTypeBox()
jp2box._BOX_WITH_ID[b'jp2h'] = jpx_common.hvJP2HeaderBox
jp2box._BOX_WITH_ID[b'xml '] = jpx_common.hvXMLBox
jp2box._BOX_WITH_ID[b'jp2c'] = jpx_common.hvContiguousCodestreamBox

def jpx_colr(colr):
    if colr is None:
        return None
    return jp2box.ColourSpecificationBox(method=colr.method,
                                          precedence=colr.precedence,
                                          approximation=max(1, colr.approximation),
                                          colorspace=colr.colorspace,
                                          icc_profile=colr.icc_profile)


def jpx_header(boxes):
    return [jpx_colr(box) if box.box_id == 'colr' else box for box in boxes]


@cython.infer_types(False)
def box_bytes(box):
    if box is None:
        return None
    buffer = BytesIO()
    box.write(buffer)
    return buffer.getvalue()


@cython.infer_types(False)
def reader_requirements(headers, rsiz, links):
    features = {1}
    opacity_features = set()

    for header in headers:
        channel_definition = jp2_common.first_box(header, 'cdef')
        if channel_definition is not None:
            if 1 in channel_definition.channel_type:
                opacity_features.add(9)
            if 2 in channel_definition.channel_type:
                opacity_features.add(10)

    if 2 in rsiz:
        features.add(4)
    if any(value not in (1, 2) for value in rsiz):
        features.add(5)
    if len(headers) > 1:
        features.add(2)
    features.update(opacity_features)
    if links:
        features.add(15)

    features = sorted(features)
    mask_length = (len(features) + 7) // 8

    masks = [(1 << (mask_length * 8 - i - 1)).to_bytes(mask_length, 'big')
             for i in range(len(features))]
    required = ((1 << len(features)) - 1) << (mask_length * 8 - len(features))
    required = required.to_bytes(mask_length, 'big')
    parts = [bytes((mask_length,)), required, required,
             struct.pack('>H', len(features))]
    for feature, mask in zip(features, masks):
        parts.extend((struct.pack('>H', feature), mask))
    parts.append(b'\0\0')
    payload = b''.join(parts)
    return struct.pack('>I4s', 8 + len(payload), b'rreq') + payload


def write_jpch_jplh(jp2h, defaults, jpx):
    ihdr = jp2_common.first_box(jp2h, 'ihdr')
    bpcc = jp2_common.first_box(jp2h, 'bpcc')
    colr = [jpx_colr(box) for box in jp2h if box.box_id == 'colr']
    pclr = jp2_common.first_box(jp2h, 'pclr')
    cmap = jp2_common.first_box(jp2h, 'cmap')
    channel_definition = jp2_common.first_box(jp2h, 'cdef')
    res = jp2_common.first_box(jp2h, 'res ')

    default_bpcc = jp2_common.first_box(defaults, 'bpcc')
    default_colr = [jpx_colr(box) for box in defaults if box.box_id == 'colr']
    default_pclr = jp2_common.first_box(defaults, 'pclr')
    default_cmap = jp2_common.first_box(defaults, 'cmap')
    default_channel_definition = jp2_common.first_box(defaults, 'cdef')
    default_res = jp2_common.first_box(defaults, 'res ')

    if pclr is None and default_pclr is not None:
        num = ihdr.num_components
        cmap = jp2box.ComponentMappingBox(component_index=list(range(num)),
                                          mapping_type=[0]*num,
                                          palette_index=[0]*num)

    boxes = [ihdr]
    if box_bytes(bpcc) != box_bytes(default_bpcc) and bpcc is not None:
        boxes.append(bpcc)
    if box_bytes(pclr) != box_bytes(default_pclr) and pclr is not None:
        boxes.append(pclr)
    if box_bytes(cmap) != box_bytes(default_cmap) and cmap is not None:
        boxes.append(cmap)
    jp2box.CodestreamHeaderBox(box=boxes).write(jpx)

    boxes = []
    if [box_bytes(box) for box in colr] != [box_bytes(box) for box in default_colr]:
        boxes.append(jp2box.ColourGroupBox(box=colr))
    if (box_bytes(channel_definition) != box_bytes(default_channel_definition)
            and channel_definition is not None):
        boxes.append(channel_definition)
    if box_bytes(res) != box_bytes(default_res) and res is not None:
        boxes.append(res)
    jp2box.CompositingLayerHeaderBox(box=boxes).write(jpx)


# @profile
def jpx_merge(names_in, jpxname, links):

    num = len(names_in)
    if num == 0:
        raise ValueError('no JP2 input files')
    if links and num > 0xFFFF:
        raise ValueError('linked JPX supports at most 65535 input files')

    struct_pack = struct.pack

    # ftbl with 1 flst with 1 fragment
    ftbl_flst = cython.declare(cython.bytes)
    ftbl_flst = struct_pack('>I4sI4sH', 8 + 8 + 2 + 14, b'ftbl', 8 + 2 + 14, b'flst', 1)

    # typical pattern of empty jpch & jplh
    empty_jpch_jplh = cython.declare(cython.bytes)
    empty_jpch_jplh = struct_pack('>I4sI4s', 8, b'jpch', 8, b'jplh')

    inputs = []
    rsiz = []
    # dtbl stream
    dtbl = []
    dtbl_length = 0

    for i in range(num):
        jp2name = cython.declare(cython.bytes)
        jp2name = names_in[i]

        with open(jp2name, 'rb') as ifile:
            box = cython.declare(cython.list)
            box = jpx_common.hv_parse_superbox(ifile, 0, os.fstat(ifile.fileno()).st_size)

            if (len(box) < 2
                    or box[0] is None or box[0].box_id != 'jP  '
                    or box[1] is None or box[1].box_id != 'ftyp'):
                raise ValueError('invalid JP2 file: {0}'.format(os.fsdecode(jp2name)))

            jp2h = cython.declare(jpx_common_c.hvJP2HeaderBox)
            jp2h = jp2_common.first_box(box, 'jp2h')

            xml_ = cython.declare(jpx_common_c.hvXMLBox)
            xml_ = jp2_common.first_box(box, 'xml ')

            jp2c = cython.declare(jpx_common_c.hvContiguousCodestreamBox)
            jp2c = jp2_common.first_box(box, 'jp2c')
            if jp2h is None or jp2c is None:
                raise ValueError('missing required JP2 box: {0}'.format(os.fsdecode(jp2name)))
            if links and jp2c.length > 0xFFFFFFFF:
                raise ValueError(
                    'linked JPX cannot reference a codestream larger than '
                    '4 GiB: {0}'.format(os.fsdecode(jp2name)))

            ifile.seek(jp2c.offset)
            codestream_header = ifile.read(8)
            if (len(codestream_header) != 8
                    or codestream_header[:4] != b'\xff\x4f\xff\x51'):
                raise ValueError(
                    'invalid JPEG 2000 main header: {0}'.format(
                        os.fsdecode(jp2name)))
            rsiz.append(struct.unpack('>H', codestream_header[6:])[0])

            inputs.append((jp2name, jp2h.header, jp2h.hv_parse(ifile),
                           None if xml_ is None else xml_.xmlbuf,
                           jp2c.offset, jp2c.length))

    compatibility = ('jpx ',) if links else ('jpx ', 'jp2 ', 'jpxb')
    with open(jpxname, 'wb') as jpx:
        jpx_write = jpx.write
        jp2box.JPEG2000SignatureBox().write(jpx)
        jp2box.FileTypeBox(brand='jpx ', minor_version=1,
                           compatibility_list=compatibility).write(jpx)
        jpx_write(reader_requirements([item[2] for item in inputs],
                                      rsiz, links))

        head0 = inputs[0][1]
        jp2box.JP2HeaderBox(box=jpx_header(inputs[0][2])).write(jpx)

        for i, item in enumerate(inputs):
            jp2name, header, parsed_header, xmlbuf, jp2c_offset, jp2c_length = item
            if header == head0:
                jpx_write(empty_jpch_jplh)
            else:
                write_jpch_jplh(parsed_header, inputs[0][2], jpx)

            if links:
                jpx_write(ftbl_flst + struct_pack('>QIH', jp2c_offset,
                                                   jp2c_length, i + 1))

                url_ = Path(os.fsdecode(jp2name)).resolve().as_uri().encode('ascii') + b'\0'
                url_box = struct_pack('>I4sI', 12 + len(url_), b'url ', 0) + url_
                dtbl.append(url_box)
                dtbl_length += len(url_box)
            else:
                with open(jp2name, 'rb') as ifile:
                    jpx_common_c.hv_copy_codestream(
                        ifile, jpx, jp2c_offset, jp2c_length)

            if xmlbuf is not None:
                association = struct_pack('>I4sI4sII',
                                          24 + len(xmlbuf), b'asoc',
                                          16, b'nlst', 0x01000000+i,
                                          0x02000000+i)
                jpx_write(association)
                jpx_write(xmlbuf)

        if links:
            jpx_write(struct_pack('>I4sH', 10 + dtbl_length, b'dtbl', len(dtbl)))
            for part in dtbl:
                jpx_write(part)
