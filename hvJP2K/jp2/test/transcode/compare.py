"""Compare decoded pixels and a transcoded JP2 with the Kakadu reference.

Every box must be byte-identical, except that COM marker segments in the
codestream are ignored: hvJP2K keeps the input's comment, while Kakadu
writes its own version string."""

import re
import struct
import sys
import warnings
from pathlib import Path

import glymur
import numpy as np


def boxes(data):
    pos = 0
    while pos < len(data):
        size, box_id = struct.unpack(">I4s", data[pos : pos + 8])
        header = 8
        if size == 1:
            size = struct.unpack(">Q", data[pos + 8 : pos + 16])[0]
            header = 16
        elif size == 0:
            size = len(data) - pos
        yield box_id, data[pos + header : pos + size]
        pos += size


def without_comments(cs):
    out = bytearray(cs[:2])
    pos = 2
    while True:
        marker, length = struct.unpack(">HH", cs[pos : pos + 4])
        if marker == 0xFF90:  # SOT: the rest of the codestream
            return bytes(out + cs[pos:])
        if marker != 0xFF64:
            out += cs[pos : pos + 2 + length]
        pos += 2 + length


def main(original, output, reference):
    with warnings.catch_warnings():
        # Glymur compares IHDR with Xsiz/Ysiz without subtracting the origin.
        if re.search(r"_origin\d+_", Path(original).name):
            warnings.filterwarnings(
                "ignore",
                message=r"The IHDR dimensions .* do not match the codestream dimensions .*",
                category=UserWarning,
                module=r"glymur\.jp2kr",
            )
        source_pixels = glymur.Jp2k(original)[:]
        output_pixels = glymur.Jp2k(output)[:]
    # Fixture names with dimensions must keep exercising those exact sizes.
    dimensions = re.search(r"_(\d+)x(\d+)_", Path(original).name)
    if dimensions and source_pixels.shape[:2] != (
        int(dimensions.group(2)),
        int(dimensions.group(1)),
    ):
        sys.exit("fixture dimensions differ from filename")
    if not np.array_equal(source_pixels, output_pixels):
        sys.exit("decoded pixels differ from input")

    with open(output, "rb") as f:
        out = list(boxes(f.read()))
    with open(reference, "rb") as f:
        ref = list(boxes(f.read()))
    if [b for b, _ in out] != [b for b, _ in ref]:
        sys.exit("box structure differs")
    for (box_id, a), (_, b) in zip(out, ref):
        if box_id == b"jp2c":
            a, b = without_comments(a), without_comments(b)
        if a != b:
            sys.exit("{0} box differs".format(box_id.decode("latin-1")))


if __name__ == "__main__":
    main(*sys.argv[1:])
