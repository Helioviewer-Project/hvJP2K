"""Exercise packet accounting and corrupted inputs."""

import random
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


def with_tile(codestream, tile):
    sot = codestream.index(b"\xff\x90")
    sod = codestream.index(b"\xff\x93", sot) + 2
    out = bytearray(codestream[:sod] + tile + b"\xff\xd9")
    out[sot + 6 : sot + 10] = (len(out) - 2 - sot).to_bytes(4, "big")
    return bytes(out)


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
# A run of 0xFF raises Lblock past 62 bits. The packet reader must report
# the overrun without wrapping the length around.
origin = (
    Path(__file__).resolve().parent / "orig/synthetic_rgb_129x129_origin129_CPRL.jp2"
)
rgb = next(data for box_id, data in boxes(origin.read_bytes()) if box_id == b"jp2c")
sot = rgb.index(b"\xff\x90")
sod = rgb.index(b"\xff\x93", sot) + 2
tile = rgb[sod:-2]
rejects(
    with_tile(rgb, tile[:2917] + b"\xff" * 11 + tile[2932:]),
    "packet data overruns the tile",
)
print("pass: packet-header and tile-part integrity")


def header_field(offset, value):
    damaged = bytearray(rgb)
    damaged[offset : offset + len(value)] = value
    return bytes(damaged)


siz = 2
cod = siz + 2 + struct.unpack_from(">H", rgb, siz + 2)[0]
rejects(b"", "not a JPEG 2000 codestream")
rejects(rgb[:4], "truncated main header marker")
rejects(rgb[:2] + rgb[cod:], "SIZ marker must follow SOC")
rejects(rgb[:cod] + rgb[sot:], "no COD marker")
rejects(rgb[:cod] + rgb[siz:cod] + rgb[cod:], "duplicate SIZ marker")
rejects(rgb[:sot] + rgb[cod:sot] + rgb[sot:], "duplicate COD marker")
rejects(header_field(siz + 2, b"\x00\x02"), "invalid SIZ marker length")
rejects(header_field(siz + 2, b"\xff\xff"), "invalid main header marker length")
rejects(header_field(siz + 4 + 34, b"\x00\x00"), "invalid SIZ component count")
rejects(header_field(siz + 4 + 34, b"\x00\x04"), "invalid SIZ component count")
rejects(header_field(siz + 4 + 10, (258).to_bytes(4, "big")), "invalid SIZ image")
rejects(header_field(siz + 4 + 18, b"\x00" * 4), "invalid SIZ tile size")
rejects(header_field(siz + 4 + 37, b"\x00"), "invalid SIZ component subsampling")
empty_component = bytearray(rgb)
# Large subsampling leaves these components empty at coarse resolutions.
empty_component[siz + 4 + 40] = 174  # component 1 XRsiz
empty_component[siz + 4 + 44] = 255  # component 2 YRsiz
rejects(bytes(empty_component), "unparsed tile bytes")
rejects(header_field(cod + 2, b"\x00\x00"), "invalid main header marker length")
short_cod = bytearray(rgb)
cod_length = struct.unpack_from(">H", short_cod, cod + 2)[0]
del short_cod[cod + cod_length + 1]
short_cod[cod + 2 : cod + 4] = (cod_length - 1).to_bytes(2, "big")
rejects(bytes(short_cod), "invalid COD marker length")
rejects(header_field(cod + 4, b"\x08"), "invalid COD style flags")
rejects(header_field(cod + 4 + 1, b"\x05"), "invalid COD progression")
rejects(header_field(cod + 4 + 2, b"\x00\x00"), "invalid COD progression")
rejects(header_field(cod + 4 + 5, b"\x42"), "invalid COD decomposition")
rejects(header_field(cod + 4 + 6, b"\x09"), "invalid COD code-block")
rejects(header_field(cod + 4 + 7, b"\x05"), "invalid COD code-block")
rejects(header_field(cod + 4 + 11, b"\x08"), "zero COD precinct exponent")
huge = bytearray(rgb)
huge[siz + 4 + 2 : siz + 4 + 6] = (0x7FFFFFFF).to_bytes(4, "big")
huge[siz + 4 + 18 : siz + 4 + 22] = (0x7FFFFFFF).to_bytes(4, "big")
huge[cod + 4 + 2 : cod + 4 + 4] = (60164).to_bytes(2, "big")
rejects(bytes(huge), "packet count exceeds tile data")
sparse = bytearray(rgb)
for offset in (2, 6, 18, 22):
    sparse[siz + 4 + offset : siz + 8 + offset] = (65536).to_bytes(4, "big")
sparse[cod + 4 + 10 : cod + 4 + 13] = b"\xff" * 3
rejects(bytes(sparse), "code-block count exceeds supported limit")
sparse[cod + 4 + 2 : cod + 4 + 4] = (200).to_bytes(2, "big")
rejects(bytes(sparse), "code-block layer count exceeds supported limit")
print("pass: malformed SIZ and COD headers")

fixture_dir = Path(__file__).resolve().parent
small = [
    next(data for box_id, data in boxes(path.read_bytes()) if box_id == b"jp2c")
    for path in (
        fixture_dir / "orig/solo_fsi174_127x129_RLCP_PLT.jp2",
        origin,
        fixture_dir / "sop_eph/synthetic_rgb_129x129_CPRL_SOP_EPH.jp2",
    )
]
rng = random.Random(0)
rejected = accepted = 0
for _ in range(2000):
    original = rng.choice(small)
    sot = original.index(b"\xff\x90")
    sod = original.index(b"\xff\x93", sot) + 2
    tile = bytearray(original[sod:-2])
    kind, at = rng.randrange(4), rng.randrange(len(tile) - 16)
    if kind == 0:
        for _ in range(rng.randint(1, 8)):
            tile[rng.randrange(len(tile))] = rng.randrange(256)
    elif kind == 1:
        del tile[at:]
    elif kind == 2:
        tile[at : at + rng.randint(1, 16)] = bytes(
            [rng.choice(b"\xff\x00\x7f\x80")]
        ) * rng.randint(1, 16)
    else:
        tile[at:at] = bytes(rng.randrange(256) for _ in range(rng.randint(1, 32)))
    try:
        once = transcode_codestream(with_tile(original, tile))
    except ValueError:
        rejected += 1
    else:
        accepted += 1
        matches(transcode_codestream(once), once, "corrupted input is not stable")
if not (accepted and rejected):
    raise AssertionError("corruption test did not exercise both outcomes")
print(
    "pass: {0} rejected and {1} stable corrupted codestreams".format(rejected, accepted)
)
