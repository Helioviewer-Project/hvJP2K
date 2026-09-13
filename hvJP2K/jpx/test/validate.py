#!/usr/bin/env python3

import argparse
from pathlib import Path
from urllib.parse import unquote, urlparse

from glymur import Jp2k


def codestreams(path):
    data = Path(path).read_bytes()
    result = []
    offset = 0
    while offset < len(data):
        length = int.from_bytes(data[offset : offset + 4], "big")
        box_id = data[offset + 4 : offset + 8]
        header_length = 8
        if length == 1:
            length = int.from_bytes(data[offset + 8 : offset + 16], "big")
            header_length = 16
        elif length == 0:
            length = len(data) - offset
        assert length >= header_length and offset + length <= len(data)
        if box_id == b"jp2c":
            result.append(data[offset + header_length : offset + length])
        offset += length
    assert offset == len(data)
    return result


parser = argparse.ArgumentParser()
parser.add_argument("mode", choices=("embedded", "linked"))
parser.add_argument("jpx")
parser.add_argument("sources", nargs="+")
args = parser.parse_args()

sources = [Path(path).resolve() for path in args.sources]
jpx = Jp2k(args.jpx)
boxes = jpx.box
assert [box.box_id for box in boxes[:3]] == ["jP  ", "ftyp", "rreq"]
assert sum(box.box_id == "rreq" for box in boxes) == 1

ftyp = boxes[1]
if args.mode == "embedded":
    assert ftyp.compatibility_list == ["jpx ", "jp2 ", "jpxb"]
    assert 12 in boxes[2].standard_flag
else:
    assert ftyp.compatibility_list == ["jpx "]
    assert 15 in boxes[2].standard_flag

assert sum(box.box_id == "jpch" for box in boxes) == len(sources)
assert sum(box.box_id == "jplh" for box in boxes) == len(sources)


def check_colr(boxes):
    for box in boxes:
        if box.box_id == "colr":
            assert box.approximation in (1, 2, 3, 4)
        check_colr(box.box)


check_colr(boxes)

associations = [box for box in boxes if box.box_id == "asoc"]
for box in associations:
    assert [child.box_id for child in box.box] == ["nlst", "xml "]
    index = box.box[0].associations[0] & 0x00FFFFFF
    assert box.box[0].associations == (0x01000000 + index, 0x02000000 + index)

source_codestreams = [codestreams(path)[0] for path in sources]
if args.mode == "embedded":
    assert codestreams(args.jpx) == source_codestreams
else:
    fragments = [box.box[0] for box in boxes if box.box_id == "ftbl"]
    assert len(fragments) == len(sources)
    dtbl = next(box for box in boxes if box.box_id == "dtbl")
    assert len(dtbl.DR) == len(sources)
    for i, (fragment, reference, source, codestream) in enumerate(
        zip(fragments, dtbl.DR, sources, source_codestreams), 1
    ):
        assert fragment.data_reference == (i,)
        assert fragment.fragment_length == (len(codestream),)
        assert (
            source.read_bytes()[
                fragment.fragment_offset[0] : fragment.fragment_offset[0]
                + len(codestream)
            ]
            == codestream
        )
        url = urlparse(reference.url)
        assert url.scheme == "file" and not url.netloc
        assert Path(unquote(url.path)) == source
