
import glymur
import tempfile
import os

from .jp2_common import first_box

def jp2_transcode(filepath, corder='RPCL', orggen_plt='yes', cprecincts=[128, 128], xml_rewrite=False):
    """Transcodes JPEG 2000 images to allow support for use with JHelioviewer
    and the JPIP server"""

    tmp = tempfile.NamedTemporaryFile(suffix='.j2c').name

    # Base command
    command ='kdu_transcode -i %s -o %s' % (filepath, tmp)

    # Corder
    if corder is not None:
        command += " Corder=%s" % corder
    # ORGgen_plt
    if orggen_plt is not None:
        command += " ORGgen_plt=%s" % orggen_plt
    # Cprecincts
    if cprecincts is not None:
        command += " Cprecincts=\{%d,%d\}" % (cprecincts[0], cprecincts[1])

    # Hide output
    command += " >/dev/null"

    # Execute kdu_transcode
    os.system(command)
    if not os.path.isfile(tmp):
        raise Exception('kdu_transcode: ' + filepath)

    j2c = glymur.Jp2k(tmp)
    jp2 = glymur.Jp2k(filepath)

    # replace original codestream box with one derived from the transcoded codestream
    jp2_cs = first_box(jp2.box, 'jp2c')
    jp2.box[jp2.box.index(jp2_cs)] = glymur.jp2box.ContiguousCodestreamBox(j2c.get_codestream())

    # rewrite original XML box
    if xml_rewrite:
        xml_ = first_box(jp2.box, 'xml ')
        if xml_ is not None:
            jp2.box[jp2.box.index(xml_)] = glymur.jp2box.XMLBox(xml_.xml)

    # wrap transcoded codestream with the boxes of the original JP2
    trans = tempfile.NamedTemporaryFile().name
    j2c.wrap(trans, boxes=jp2.box)
    os.remove(tmp)

    return trans
