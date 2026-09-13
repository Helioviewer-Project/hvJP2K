import os
import subprocess
import tempfile

import glymur

from .jp2_common import first_box


def jp2_transcode(
    filepath, corder="RPCL", orggen_plt="yes", cprecincts=(128, 128), xml_rewrite=False
):
    """Transcodes JPEG 2000 images to allow support for use with JHelioviewer
    and the JPIP server"""

    fd, tmp = tempfile.mkstemp(suffix=".j2c")
    os.close(fd)
    os.unlink(tmp)

    command = ["kdu_transcode", "-i", filepath, "-o", tmp]

    # Corder
    if corder is not None:
        command.append("Corder={0}".format(corder))
    # ORGgen_plt
    if orggen_plt is not None:
        command.append("ORGgen_plt={0}".format(orggen_plt))
    # Cprecincts
    if cprecincts is not None:
        command.append("Cprecincts={{{0},{1}}}".format(cprecincts[0], cprecincts[1]))

    try:
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL)

        j2c = glymur.Jp2k(tmp)
        jp2 = glymur.Jp2k(filepath)

        # Replace the original codestream box with the transcoded codestream.
        jp2_cs = first_box(jp2.box, "jp2c")
        if jp2_cs is None:
            raise ValueError("no JP2 codestream box: " + filepath)
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
