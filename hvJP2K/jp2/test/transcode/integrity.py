"""Exercise packet accounting with the bundled Kakadu AIA codestream."""

import importlib.util
import struct
import sys
from pathlib import Path

from hvJP2K.jp2 import jp2_precincts
from hvJP2K.jp2.jp2_precincts import _BitReader, _BitWriter, transcode_codestream

from compare import boxes

source_path = Path(jp2_precincts.__file__).with_name("jp2_precincts.py")
source_spec = importlib.util.spec_from_file_location(
    "jp2_precincts_source", source_path
)
source = importlib.util.module_from_spec(source_spec)
source_spec.loader.exec_module(source)


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


wr = _BitWriter()
for _ in range(8):
    wr.bit(1)
wr.bits(0x7F, 7)
wr.bits(0xFFFF, 16)
wr.bit(0)
wr.bits(0x3F, 6)
wr.bits(0xFF, 8)
header = wr.flush()
matches(header, b"\xff\x7f\xff\x7f\xbf\xff\x00", "packet-header stuffing differs")
rd = _BitReader(header, 0)
for _ in range(8):
    matches(rd.bit(), 1, "packet-header bit differs")
for n, value in ((7, 0x7F), (16, 0xFFFF)):
    matches(rd.bits(n), value, "packet-header bits differ")
matches(rd.bit(), 0, "packet-header bit differs")
for n, value in ((6, 0x3F), (8, 0xFF)):
    matches(rd.bits(n), value, "packet-header bits differ")
matches(rd.align(), len(header), "stuffed end byte was not consumed")

wide_header = b"\x7f" * 20
wide_value = int.from_bytes(wide_header[:9], "big") >> 2
for module in (jp2_precincts, source):
    matches(
        module._BitReader(wide_header, 0).bits(70),
        wide_value,
        "70-bit packet-header read differs from Python integer arithmetic",
    )


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
fixture_dir = Path(__file__).resolve().parent
fixtures = sorted(
    list(fixture_dir.glob("orig/*.jp2"))
    + list(fixture_dir.glob("trans/*.jp2"))
    + list(fixture_dir.glob("sop_eph/*.jp2"))
    + list(fixture_dir.glob("sop_eph/trans/*.jp2"))
    + list((fixture_dir.parents[2] / "jpx/test").glob("*-ref/*.jp2"))
)
for path in fixtures:
    codestream = next(
        data for box_id, data in boxes(path.read_bytes()) if box_id == b"jp2c"
    )
    matches(
        source.transcode_codestream(codestream),
        transcode_codestream(codestream),
        "compiled and source output differ for " + str(path),
    )
print("pass: packet-header stuffing and tile-part integrity")
print("pass: source and active transcode agree on {0} JP2 files".format(len(fixtures)))
