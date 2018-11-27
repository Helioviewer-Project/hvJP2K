
# cython: profile=False
# cython: infer_types=True
# cython: boundscheck=False
# cython: wraparound=False

import cython
import struct
import sys

from glymur import jp2box

from ..jp2 import jp2_common
from . import jpx_common, jpx_mmap

import sqlite3
import os.path 
from io import BytesIO
import os
DBNAME = '/data/sqlite/swhv_headers.db'
JPX_HEADER_DB = 'JPX_HEADER_DB'
if JPX_HEADER_DB in os.environ:
    DBNAME = os.environ[JPX_HEADER_DB]

# override glymur box parsing
jp2box._BOX_WITH_ID[b'jP  '] = jpx_common.hvJPEG2000SignatureBox()
jp2box._BOX_WITH_ID[b'ftyp'] = jpx_common.hvFileTypeBox()
jp2box._BOX_WITH_ID[b'jp2h'] = jpx_common.hvJP2HeaderBox
jp2box._BOX_WITH_ID[b'xml '] = jpx_common.hvXMLBox
jp2box._BOX_WITH_ID[b'jp2c'] = jpx_common.hvContiguousCodestreamBox

# write all boxes, could be optimized
def write_jpch_jplh(jp2h, jpx):
    ihdr = jp2_common.first_box(jp2h, 'ihdr')
    colr = jp2_common.first_box(jp2h, 'colr')
    pclr = jp2_common.first_box(jp2h, 'pclr')
    cmap = jp2_common.first_box(jp2h, 'cmap')
    cdef = jp2_common.first_box(jp2h, 'cdef')

    num = ihdr.num_components

    # create direct colour mapping
    if cmap is None:
        cmap = jp2box.ComponentMappingBox(component_index=list(range(num)),
                                          mapping_type=[0]*num,
                                          palette_index=[0]*num)

    # channel definition, wild guess
    if cdef is None:
        if pclr is not None:
            num = pclr.palette.shape[1]
        # [COLOR,...], [GREY|RED,...]
        cdef = jp2box.ChannelDefinitionBox(channel_type=[0]*num,
                                           association=list(range(1,num+1)))

    boxes = (ihdr, cmap) if pclr is None else (ihdr, pclr, cmap)
    jp2box.CodestreamHeaderBox(box=boxes).write(jpx)

    cgrp = jp2box.ColourGroupBox(box=[colr])
    jp2box.CompositingLayerHeaderBox(box=(cgrp, cdef)).write(jpx)


# @profile
def jpx_merge(names_in, jpxname, links):

    num = len(names_in)

    struct_pack = struct.pack

    # ftbl with 1 flst with 1 fragment
    ftbl_flst = cython.declare(cython.bytes)
    ftbl_flst = struct_pack('>I4sI4sH', 8 + 8 + 2 + 14, b'ftbl', 8 + 2 + 14, b'flst', 1)

    # typical pattern of empty jpch & jplh
    empty_jpch_jplh = cython.declare(cython.bytes)
    empty_jpch_jplh = struct_pack('>I4sI4s', 8, b'jpch', 8, b'jplh')

    # jpx stream
    jpx = open(jpxname, 'wb')
    jpx_write = jpx.write
    jp2box.JPEG2000SignatureBox().write(jpx)
    jp2box.FileTypeBox(brand='jpx ', compatibility_list=('jpx ', 'jp2 ', 'jpxb')).write(jpx)

    # asoc stream
    asoc = []
    # dtbl stream
    dtbl = []

    head0 = cython.declare(cython.bytes)
    head0 = None

    ifile = cython.declare(jpx_mmap.hvMap)
    ifile = jpx_mmap.hvMap()

    for i in range(num):
        jp2name = cython.declare(cython.bytes)
        jp2name = names_in[i]

        try:
            if ifile.open(jp2name):
                continue

            box = cython.declare(cython.list)
            box = jpx_common.hv_parse_superbox(ifile, 0, ifile.size())

            # failed JP2 signature or file type verification
            if not box or box[0] is None or box[1] is None:
                continue

            jp2h = cython.declare(jpx_common.hvJP2HeaderBox)
            jp2h = jp2_common.first_box(box, 'jp2h')

            xml_ = cython.declare(jpx_common.hvXMLBox)
            xml_ = jp2_common.first_box(box, 'xml ')

            jp2c = cython.declare(jpx_common.hvContiguousCodestreamBox)
            jp2c = jp2_common.first_box(box, 'jp2c')

            # asoc
            if xml_ is not None:
                asoc.append(struct_pack('>I4sI4sII',
                                    # asoc 8 + 16
                                    24 + xml_.length, b'asoc',
                                    # nlst 8 + 4 + 4
                                    16, b'nlst', 0x01000000+i, 0x02000000+i))
                asoc.append(xml_.xmlbuf)

            # identical JP2 header, typical
            if head0 == jp2h.header:
                jpx_write(empty_jpch_jplh)
            else:
                # parse jp2h for validity/access to child boxes
                jp2h_box = jp2h.hv_parse(ifile)

                # first is reference
                if head0 is None:
                    head0 = jp2h.header[:]
                    # write jp2h
                    jpx_write(head0 + empty_jpch_jplh)
                # different size/colour spec
                else:
                    write_jpch_jplh(jp2h_box, jpx)

            if links:
                # ftbl
                jpx_write(ftbl_flst + struct_pack('>QIH', jp2c.offset, jp2c.length, i + 1))

                # dtbl
                url_ = cython.declare(cython.bytes)
                url_ = b'file://' + jp2name + b'\0'
                # 8 + 1 + 1 + 1 + 1
                dtbl.append(struct_pack('>I4sI', 12 + len(url_), b'url ', 0) + url_)
            else:
                # copy jp2c
                jp2c.hv_copy(ifile, jpx)
        finally:
            ifile.close()

    # 8 + asoc size
    asoc_full = b''.join(asoc)
    jpx_write(struct_pack('>I4s', 8 + len(asoc_full), b'asoc'))
    jpx_write(asoc_full)

    if links:
        # 8 + 2 + dtbl size
        dtbl_full = b''.join(dtbl)
        jpx_write(struct_pack('>I4sH', 10 + len(dtbl_full), b'dtbl', len(dtbl)))
        jpx_write(dtbl_full)

    jpx.close()

def write_jpch_jplh_db(jp2h):
    b = bytes()
    jpx = BytesIO(b)
    ihdr = jp2_common.first_box(jp2h, 'ihdr')
    colr = jp2_common.first_box(jp2h, 'colr')
    pclr = jp2_common.first_box(jp2h, 'pclr')
    cmap = jp2_common.first_box(jp2h, 'cmap')
    cdef = jp2_common.first_box(jp2h, 'cdef')

    num = ihdr.num_components

    # create direct colour mapping
    if cmap is None:
        cmap = jp2box.ComponentMappingBox(component_index=list(range(num)),
                                          mapping_type=[0]*num,
                                          palette_index=[0]*num)

    # channel definition, wild guess
    if cdef is None:
        if pclr is not None:
            num = pclr.palette.shape[1]
        # [COLOR,...], [GREY|RED,...]
        cdef = jp2box.ChannelDefinitionBox(channel_type=[0]*num,
                                           association=list(range(1,num+1)))

    boxes = (ihdr, cmap) if pclr is None else (ihdr, pclr, cmap)
    jp2box.CodestreamHeaderBox(box=boxes).write(jpx)

    cgrp = jp2box.ColourGroupBox(box=[colr])
    jp2box.CompositingLayerHeaderBox(box=(cgrp, cdef)).write(jpx)
    return b


# @profile
def jpx_merge_to_db(names_in):
    dbexists = os.path.isfile(DBNAME)
    conn = sqlite3.connect(DBNAME, timeout=120)
    if not dbexists:
        conn.execute('''CREATE TABLE JP2DATA (jp2name TEXT PRIMARY KEY, jpch_jplh BLOB, jpch_jplhdiff, ftbl_offset INTEGER, ftbl_length INTEGER, dtbl BLOB, asoc BLOB);''')

    num = len(names_in)

    struct_pack = struct.pack

    # ftbl with 1 flst with 1 fragment
    ftbl_flst = cython.declare(cython.bytes)
    ftbl_flst = struct_pack('>I4sI4sH', 8 + 8 + 2 + 14, b'ftbl', 8 + 2 + 14, b'flst', 1)

    # typical pattern of empty jpch & jplh
    empty_jpch_jplh = cython.declare(cython.bytes)
    empty_jpch_jplh = struct_pack('>I4sI4s', 8, b'jpch', 8, b'jplh')

    # asoc stream
    asoc = []
    # dtbl stream
    dtbl = []

    head0 = cython.declare(cython.bytes)
    head0 = None

    ifile = cython.declare(jpx_mmap.hvMap)
    ifile = jpx_mmap.hvMap()

    for i in range(num):
        jp2name = cython.declare(cython.bytes)
        jp2name = names_in[i]

        try:
            if ifile.open(jp2name):
                continue
            box = cython.declare(cython.list)
            box = jpx_common.hv_parse_superbox(ifile, 0, ifile.size())

            # failed JP2 signature or file type verification
            if not box or box[0] is None or box[1] is None:
                continue

            jp2h = cython.declare(jpx_common.hvJP2HeaderBox)
            jp2h = jp2_common.first_box(box, 'jp2h')

            xml_ = cython.declare(jpx_common.hvXMLBox)
            xml_ = jp2_common.first_box(box, 'xml ')

            jp2c = cython.declare(jpx_common.hvContiguousCodestreamBox)
            jp2c = jp2_common.first_box(box, 'jp2c')

            # asoc
            if xml_ is not None:
                asoc.append(struct_pack('>I4sI4sII',
                                    # asoc 8 + 16
                                    24 + xml_.length, b'asoc',
                                    # nlst 8 + 4 + 4
                                    16, b'nlst', 0x01000000+i, 0x02000000+i))
                asoc.append(xml_.xmlbuf)
                asoci = struct_pack('>I4sI4sII',
                                    # asoc 8 + 16
                                    24 + xml_.length, b'asoc',
                                    # nlst 8 + 4 + 4
                                    16, b'nlst', 0x01000000+i, 0x02000000+i) + xml_.xmlbuf

            # identical JP2 header, typical
            jpch_jplh = jp2h.header[:] + empty_jpch_jplh
            jp2h_box = jp2h.hv_parse(ifile)
            jpch_jplhdiff = write_jpch_jplh_db(jp2h_box)

            # ftbl
            ftbl_i = ftbl_flst + struct_pack('>QIH', jp2c.offset, jp2c.length, i + 1)
            ftbl_offset = jp2c.offset
            ftbl_length = jp2c.length

            # dtbl
            url_ = cython.declare(cython.bytes)
            url_ = b'file://' + jp2name + b'\0'
            # 8 + 1 + 1 + 1 + 1
            dtbl.append(struct_pack('>I4sI', 12 + len(url_), b'url ', 0) + url_)
            dtbli = struct_pack('>I4sI', 12 + len(url_), b'url ', 0) + url_

            v = (
                    sqlite3.Binary(bytes(jp2name)),
                    sqlite3.Binary(bytes(jpch_jplh)), 
                    sqlite3.Binary(bytes(jpch_jplhdiff)), 
                    ftbl_offset, ftbl_length, 
                    sqlite3.Binary(bytes(dtbli)), 
                    sqlite3.Binary(bytes(asoci)))
            conn.execute("INSERT OR REPLACE INTO JP2DATA VALUES (?,?,?,?,?,?,?)", v)
        finally:
            ifile.close()
    conn.commit()
    conn.close()

def jpx_merge_from_db(names_in, jpxname):
    conn = sqlite3.connect(DBNAME, timeout=120)
    cur = conn.cursor()
    first = True
    names_list = b""
    for name in names_in:
        if first:
            first = False
            names_list += b"("
        else:
            names_list += b","
        names_list += b"'" + name + b"'"
    names_list += b")"
    if sys.version_info[0] >= 3:
        names_list = str(names_list,'utf-8')
    cur.execute("SELECT * FROM JP2DATA WHERE CAST(jp2name AS TEXT) in " + names_list + " order by jp2name")
    results = cur.fetchall()
    struct_pack = struct.pack
    ftbl_flst = struct_pack('>I4sI4sH', 8 + 8 + 2 + 14, b'ftbl', 8 + 2 + 14, b'flst', 1)
    empty_jpch_jplh = struct_pack('>I4sI4s', 8, b'jpch', 8, b'jplh')

    # jpx stream
    jpx = open(jpxname, 'wb')
    jpx_write = jpx.write
    jp2box.JPEG2000SignatureBox().write(jpx)
    jp2box.FileTypeBox(brand='jpx ', compatibility_list=('jpx ', 'jp2 ', 'jpxb')).write(jpx)

    # asoc stream
    asoc = []
    dtbl = []
    # dtbl stream
    #dtblfull = b''
    #asocfull = b''
    ftbl = []

    head0 = None
    i = 0
    for r in results:
        jp2name_i = r[0]
        jpch_jplh_i = r[1]
        jpch_jplh_diff_i = r[2]
        ftbl_offset = r[3]
        ftbl_length = r[4]
        dtbl_i = r[5]
        asoc_i = r[6]
        if head0 == jpch_jplh_i:
            jpx_write(empty_jpch_jplh)
        else:
            if head0 is None:
                head0 = jpch_jplh_i
                jpx_write(head0)
            else:
                jpx_write(jpch_jplh_diff_i)
        ftbl_i = ftbl_flst + struct_pack('>QIH', ftbl_offset, ftbl_length, i + 1)
        #ftbl.append(ftbl_i)
        jpx_write(ftbl_i)
        dtbl.append(dtbl_i)
        asoc.append(asoc_i)
        i = i + 1

    # 8 + asoc size
    asocfull = join_buffers(asoc)
    jpx_write(struct_pack('>I4s', 8 + len(asocfull), b'asoc'))
    jpx_write(asocfull)

    dtblfull = join_buffers(dtbl)
    jpx_write(struct_pack('>I4sH', 10 + len(dtblfull), b'dtbl', len(results)))
    jpx_write(dtblfull)
    jpx.close()
    conn.close()
"""    
    ftbl_full = b''.join(ftbl)
    jpx_write(ftbl_full)
"""

def join_buffers(bufs):
    if sys.version_info[0] < 3:
        bufs = [str(buf) for buf in bufs]
    return b''.join(bufs)
