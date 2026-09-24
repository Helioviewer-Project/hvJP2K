"""Exercise packet accounting with the bundled Kakadu AIA codestream."""

import struct
import sys
from pathlib import Path

from hvJP2K.jp2.jp2_precincts import transcode_codestream

from compare import boxes


def tile_part(index, total, data, tile=0):
    return (
        struct.pack(">HHHIBB", 0xFF90, 10, tile, 14 + len(data), index, total)
        + b"\xff\x93"
        + data
    )


def matches(actual, expected, description):
    if actual != expected:
        raise AssertionError(description)


def rejects(data, reason):
    try:
        transcode_codestream(data)
    except ValueError as e:
        if reason not in str(e):
            raise AssertionError(str(e)) from e
    else:
        raise AssertionError("invalid codestream was accepted: " + reason)


cs = next(
    data for box_id, data in boxes(Path(sys.argv[1]).read_bytes()) if box_id == b"jp2c"
)
pos = 2
while cs[pos : pos + 2] != b"\xff\x90":
    pos += 2 + struct.unpack_from(">H", cs, pos + 2)[0]
main = cs[:pos]
pos += 12
lengths = []
length = 0
while cs[pos : pos + 2] != b"\xff\x93":
    marker_length = struct.unpack_from(">H", cs, pos + 2)[0]
    if cs[pos : pos + 2] == b"\xff\x58":
        for value in cs[pos + 5 : pos + 2 + marker_length]:
            length = (length << 7) | (value & 0x7F)
            if value < 0x80:
                lengths.append(length)
                length = 0
    pos += 2 + marker_length
body = cs[pos + 2 : -2]
matches(sum(lengths), len(body), "PLT lengths do not cover the AIA tile")
first_packet = lengths[0]
expected = transcode_codestream(cs)
multi = (
    main
    + tile_part(0, 4, b"")
    + tile_part(1, 4, body[:first_packet])
    + tile_part(2, 4, body[first_packet:])
    + tile_part(3, 4, b"")
    + b"\xff\xd9"
)
matches(transcode_codestream(multi), expected, "multi-part output differs")

last = bytearray(tile_part(1, 2, body[first_packet:]))
last[6:10] = b"\x00" * 4  # Psot=0 means the last tile-part reaches EOC.
unknown_last_length = main + tile_part(0, 2, body[:first_packet]) + last + b"\xff\xd9"
matches(transcode_codestream(unknown_last_length), expected, "Psot=0 output differs")
rejects(unknown_last_length[:-2], "missing EOC marker")

unspecified_count = main + tile_part(0, 0, body) + b"\xff\xd9"
matches(transcode_codestream(unspecified_count), expected, "TNsot=0 output differs")

crossing = (
    main
    + tile_part(0, 2, body[: first_packet - 1])
    + tile_part(1, 2, body[first_packet - 1 :])
    + b"\xff\xd9"
)
rejects(crossing, "packet crosses a tile-part boundary")
rejects(main + tile_part(0, 1, body + b"\x00") + b"\xff\xd9", "unparsed tile bytes")
rejects(cs + b"\x00", "data after EOC marker")
rejects(cs[:-2], "invalid tile-part length")
rejects(main + tile_part(0, 1, body, tile=1) + b"\xff\xd9", "tile index")
rejects(main + tile_part(1, 1, body) + b"\xff\xd9", "tile-part index")
rejects(main + tile_part(0, 2, body) + b"\xff\xd9", "tile-part count")
rejects(
    main
    + tile_part(0, 2, body[:first_packet])
    + tile_part(1, 3, body[first_packet:])
    + b"\xff\xd9",
    "inconsistent tile-part count",
)
rejects(
    main + tile_part(0, 1, body[: -lengths[-1]]) + b"\xff\xd9",
    "truncated input is not supported",
)
rejects(
    main + tile_part(0, 1, body[:-1]) + b"\xff\xd9",
    "truncated input is not supported",
)

zero_first = bytearray(tile_part(0, 0, body[:first_packet]))
zero_first[6:10] = b"\x00" * 4
rejects(
    main + zero_first + tile_part(1, 0, body[first_packet:]) + b"\xff\xd9",
    "Psot=0 is only valid for the last tile-part",
)
zero_first[11] = 2
rejects(
    main + zero_first + tile_part(1, 2, body[first_packet:]) + b"\xff\xd9",
    "Psot=0 is only valid for the last tile-part",
)
print("pass: tile-part boundaries and complete packet consumption")
