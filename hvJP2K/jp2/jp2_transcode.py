import os
import tempfile

import glymur

from .jp2_common import first_box
from .jp2_precincts import transcode_codestream


def _codestream(filepath, box):
    with open(filepath, "rb") as f:
        f.seek(box.offset)
        header = f.read(16)
        size = int.from_bytes(header[:4], "big")
        skip = 16 if size == 1 else 8
        f.seek(box.offset + skip)
        return f.read(box.length - skip) if box.length else f.read()


def jp2_transcode(filepath, cprecincts=(128, 128), xml_rewrite=False):
    """Transcodes JPEG 2000 images to allow support for use with JHelioviewer
    and the JPIP server: RPCL progression, the given precincts and PLT markers,
    without recompressing the image (like kdu_transcode Corder=RPCL
    ORGgen_plt=yes Cprecincts={128,128})"""

    jp2 = glymur.Jp2k(filepath)
    jp2_cs = first_box(jp2.box, "jp2c")
    if jp2_cs is None:
        raise ValueError("no JP2 codestream box: " + filepath)

    fd, tmp = tempfile.mkstemp(suffix=".j2c")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(transcode_codestream(_codestream(filepath, jp2_cs), cprecincts))

        j2c = glymur.Jp2k(tmp)

        # Replace the original codestream box with the transcoded codestream.
        jp2.box[jp2.box.index(jp2_cs)] = glymur.jp2box.ContiguousCodestreamBox(
            j2c.get_codestream()
        )

        if xml_rewrite:
            xml_ = first_box(jp2.box, "xml ")
            if xml_ is not None:
                jp2.box[jp2.box.index(xml_)] = glymur.jp2box.XMLBox(xml_.xml)

        fd, trans = tempfile.mkstemp(
            suffix=".jp2", dir=os.path.dirname(os.path.abspath(filepath))
        )
        os.close(fd)
        os.unlink(trans)
        try:
            j2c.wrap(trans, boxes=jp2.box)
        except Exception:
            if os.path.exists(trans):
                os.remove(trans)
            raise
        return trans
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
