
import glymur
from glymur.jp2box import _BOX_WITH_ID

from ..jp2.jp2_common import hvXMLBox


# do not parse the codestreams
glymur.set_parseoptions(codestream=False)

# override XML box parsing
_BOX_WITH_ID[b'xml '] = hvXMLBox
