
from glymur.jp2box import _BOX_WITH_ID
from ..jp2.jp2_common import hvXMLBox, hvContiguousCodestreamBox

# override glymur
_BOX_WITH_ID[b'xml '] = hvXMLBox
_BOX_WITH_ID[b'jp2c'] = hvContiguousCodestreamBox
