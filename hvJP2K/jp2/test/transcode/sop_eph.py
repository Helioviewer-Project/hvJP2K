"""Check SOP/EPH handling without changing decoded pixels."""

import sys

import glymur
import numpy as np


def markers(jp2):
    return [
        segment.marker_id
        for segment in jp2.get_codestream(header_only=False).segment
        if segment.marker_id in ("SOP", "EPH")
    ]


original = glymur.Jp2k(sys.argv[1])
output = glymur.Jp2k(sys.argv[2])
mode = sys.argv[3] if len(sys.argv) > 3 else "drop"
if mode not in ("drop", "keep"):
    raise ValueError("expected drop or keep")
source_pixels = original[:]
if source_pixels.shape != (129, 129, 3):
    raise AssertionError("SOP/EPH fixture dimensions changed")
if not np.array_equal(source_pixels, output[:]):
    raise AssertionError("SOP/EPH transcode changed decoded pixels")
source_markers = markers(original)
if "SOP" not in source_markers or "EPH" not in source_markers:
    raise AssertionError("SOP/EPH fixture is missing its markers")
output_markers = markers(output)
if mode == "drop" and output_markers:
    raise AssertionError("transcoded output still has SOP/EPH markers")
if mode == "keep" and not {"SOP", "EPH"}.issubset(output_markers):
    raise AssertionError("Kakadu output lost SOP/EPH markers")
