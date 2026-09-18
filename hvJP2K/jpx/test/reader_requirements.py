#!/usr/bin/env python3

from types import SimpleNamespace

from hvJP2K.jpx.jpx_merge import reader_requirements


def parse(data):
    assert data[4:8] == b"rreq"
    mask_length = data[8]
    offset = 9
    fully_understand = data[offset : offset + mask_length]
    offset += mask_length
    decode_completely = data[offset : offset + mask_length]
    offset += mask_length
    num_features = int.from_bytes(data[offset : offset + 2], "big")
    offset += 2

    features = []
    masks = []
    for _ in range(num_features):
        features.append(int.from_bytes(data[offset : offset + 2], "big"))
        offset += 2
        masks.append(data[offset : offset + mask_length])
        offset += mask_length

    assert data[offset:] == b"\0\0"
    return features, masks, fully_understand, decode_completely


def check(headers, rsiz, links, expected):
    features, masks, fully_understand, decode_completely = parse(
        reader_requirements(headers, rsiz, links)
    )
    assert features == expected
    assert fully_understand == decode_completely
    assert len(set(masks)) == len(masks)
    assert int.from_bytes(fully_understand, "big") == sum(
        int.from_bytes(mask, "big") for mask in masks
    )


check([[]], [1], False, [1])
check([[]], [2], False, [1, 4])
check([[]], [0], False, [1, 5])

opacity = SimpleNamespace(box_id="cdef", channel_type=[1, 2])
check([[opacity], []], [0, 0], True, [1, 2, 5, 9, 10, 15])
