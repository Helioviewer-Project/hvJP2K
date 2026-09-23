#!/usr/bin/env python3

import re
import subprocess
import sys
from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from astropy.io import fits
from glymur import Jp2k
from glymur.core import PROGRESSION_ORDER
from lxml import etree

from hvJP2K.jp2.jp2_encode import COLORMAPS, encode, header_to_xml, load_colormap


def check_metadata():
    header = fits.Header()
    header.append(fits.Card.fromstring("EXPTIME =               2.5000 / A & B"))
    header["LONGSTR"] = "long <&> value " * 20
    header["HIERARCH ESO DET CHIP1 ID"] = "detector"
    header["COMMENT"] = "first <comment>"
    header["COMMENT"] = "second & comment"
    header["HISTORY"] = "history"
    header["EMPTY"] = None
    header["LOGIC"] = True

    xml = etree.fromstring(
        etree.tostring(header_to_xml(header, "contact", "output.jp2"))
    )
    fits_xml = xml.find("fits")
    assert fits_xml.findtext("EXPTIME") == "2.5000"
    assert fits_xml.find("EXPTIME").get("comment") == "A & B"
    assert fits_xml.findtext("LONGSTR") == header["LONGSTR"]
    hierarchy = fits_xml.find("ESO.DET.CHIP1.ID")
    assert hierarchy.text == "detector"
    assert hierarchy.get("keyword") == "ESO DET CHIP1 ID"
    assert [item.get("comment") for item in fits_xml.findall("COMMENT")] == [
        "first <comment>",
        "second & comment",
    ]
    assert fits_xml.find("HISTORY").get("comment") == "history"
    assert fits_xml.find("EMPTY").text is None
    assert fits_xml.findtext("LOGIC") == "T"
    assert fits_xml.find("CONTINUE") is None
    assert re.search(
        r"Creation Time : \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z\n",
        xml.findtext("helioviewer/HV_COMMENT"),
    )


def base_header():
    header = fits.Header()
    header["DATE-OBS"] = "2026-09-20T12:34:56"
    header["TELESCOP"] = "ORIGINAL"
    header["INSTRUME"] = "CAMERA"
    header["WAVELNTH"] = 171
    header["DSUN_OBS"] = 149_597_870_700
    header["CDELT1"] = 1.0
    header["CDELT2"] = 1.0
    header["CRPIX1"] = 64.5
    header["CRPIX2"] = 64.5
    header["FILENAME"] = "must-not-control-output.fits"
    return header


def xml_root(path):
    jp2 = Jp2k(path)
    xml_box = next(box for box in jp2.box if box.box_id == "xml ")
    return xml_box.xml.getroot()


def verify(command, path):
    subprocess.run((command, "-i", str(path)), check=True)


def check_library(work, verify_command):
    image = np.repeat(np.arange(128, dtype=np.uint8)[:, None], 128, axis=1)
    output = work / "library.jp2"
    encode(
        image,
        base_header(),
        output,
        compression_ratio=1,
        precinct=np.array([128, 128]),
        threads=2,
    )
    verify(verify_command, output)
    assert "Title         : library.jp2" in xml_root(output).findtext(
        "helioviewer/HV_COMMENT"
    )

    jp2 = Jp2k(output)
    header_boxes = next(box for box in jp2.box if box.box_id == "jp2h").box
    assert all(box.box_id not in ("pclr", "cmap") for box in header_boxes)
    markers = jp2.get_codestream(header_only=False).segment
    assert any(marker.marker_id == "PLT" for marker in markers)
    cod = next(marker for marker in markers if marker.marker_id == "COD")
    assert cod.prog_order == PROGRESSION_ORDER["RPCL"]

    decoded = jp2[:]
    assert decoded[0].mean() > decoded[-1].mean()

    for name in COLORMAPS:
        palette = load_colormap(name)
        assert palette.shape == (256, 3)
        assert palette.dtype == np.uint8
        assert not palette.flags.writeable
        assert load_colormap(name) is palette
    packaged_colormaps = {
        resource.name.removesuffix(".csv")
        for resource in files("hvJP2K.jp2.data").iterdir()
        if resource.name.endswith(".csv")
    }
    assert packaged_colormaps == set(COLORMAPS)

    palette_output = work / "palette.jp2"
    encode(image, base_header(), palette_output, colormap="aia171")
    verify(verify_command, palette_output)
    palette_boxes = next(
        box for box in Jp2k(palette_output).box if box.box_id == "jp2h"
    ).box
    assert any(box.box_id == "pclr" for box in palette_boxes)
    assert any(box.box_id == "cmap" for box in palette_boxes)
    assert Jp2k(palette_output)[:].shape == (128, 128, 3)

    try:
        encode(image.astype(np.uint16), base_header(), work / "invalid.jp2")
    except ValueError:
        pass
    else:
        raise AssertionError("accepted a non-8-bit image")

    for arguments in (
        {"compression_ratio": float("nan")},
        {"precinct": (128.0, 128)},
        {"precinct": (64, 128)},
        {"threads": 0},
        {"threads": 65},
    ):
        try:
            encode(image, base_header(), work / "invalid.jp2", **arguments)
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted invalid arguments: {arguments}")


def check_cli(work, command, verify_command):
    image = np.repeat(np.arange(128, dtype=np.uint8)[:, None], 128, axis=1)
    table = fits.BinTableHDU.from_columns(
        [fits.Column(name="VALUE", format="J", array=np.arange(4))]
    )
    compressed = fits.CompImageHDU(data=image, header=base_header())
    source = work / "compressed-input.fits"
    fits.HDUList([fits.PrimaryHDU(), table, compressed]).writeto(source, checksum=True)

    output_directory = work / "output"
    result = subprocess.run(
        (
            command,
            "-i",
            str(source),
            "-o",
            str(output_directory),
            "--telescop",
            "OVERRIDDEN",
            "--detector",
            "FIXED",
            "-p",
        ),
        check=True,
        capture_output=True,
        text=True,
    )
    output = output_directory / "compressed-input.jp2"
    assert result.stdout.strip() == str(output)
    assert output.is_file()
    assert not (output_directory / "must-not-control-output.jp2").exists()
    verify(verify_command, output)

    xml = xml_root(output)
    assert xml.findtext("fits/TELESCOP") == "OVERRIDDEN"
    assert xml.findtext("fits/DETECTOR") == "FIXED"

    default_output = work / "compressed-input.jp2"
    subprocess.run(
        (command, "-i", str(source)),
        check=True,
        cwd=work,
        capture_output=True,
        text=True,
    )
    assert default_output.is_file()
    default_output.unlink()

    subprocess.run(
        (command, "-i", str(source), "--out-dateobs-dir"),
        check=True,
        cwd=work,
        capture_output=True,
        text=True,
    )
    assert (work / "2026/09/20/compressed-input.jp2").is_file()

    compressed_name = work / "compressed-name.fits.gz"
    fits.PrimaryHDU(data=image, header=base_header()).writeto(
        compressed_name, checksum=True
    )
    subprocess.run(
        (command, "-i", str(compressed_name)),
        check=True,
        cwd=work,
        capture_output=True,
        text=True,
    )
    assert (work / "compressed-name.jp2").is_file()

    damaged = work / "damaged.fits"
    damaged.write_bytes(source.read_bytes())
    contents = bytearray(damaged.read_bytes())
    contents[-1] ^= 1
    damaged.write_bytes(contents)
    result = subprocess.run(
        (command, "-i", str(damaged)), cwd=work, capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "verification failed" in result.stderr
    subprocess.run(
        (command, "-i", str(damaged), "--no-verify"),
        check=True,
        cwd=work,
        capture_output=True,
        text=True,
    )


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: encode.py HV_JP2_ENCODE HV_JP2_VERIFY")

    check_metadata()
    with TemporaryDirectory(prefix="hvjp2k-encode-test.") as directory:
        work = Path(directory)
        check_library(work, sys.argv[2])
        check_cli(work, sys.argv[1], sys.argv[2])
    print("pass: encode")


if __name__ == "__main__":
    main()
