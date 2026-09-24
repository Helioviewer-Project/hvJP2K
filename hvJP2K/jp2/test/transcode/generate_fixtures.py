"""Regenerate the EUI and synthetic transcode fixtures.

The AIA fixture predates this generator and is not regenerated here.
"""

import argparse
import bz2
import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path

import glymur
import numpy as np
from astropy.io import fits
from glymur import jp2box

from hvJP2K.jp2.jp2_common import first_box
from hvJP2K.jp2.jp2_encode import header_to_xml
from hvJP2K.jp2.jp2_write import hv_write_openjp2

SOURCE = (
    Path(__file__).parent
    / "source"
    / ("solo_L2_eui-fsi174-image_20260919T000055144_V00_8bit.fits.bz2")
)
SOURCE_SHA256 = "473dd9a636a09b76675ce0d4a0b7ac0c3cb8bf32c59d1fe2095831502c92b049"
EUI_CROPS = (
    ("solo_fsi174_510x514_LRCP.jp2", 510, 514, "LRCP", False),
    ("solo_fsi174_511x513_LRCP_PLT.jp2", 511, 513, "LRCP", True),
    ("solo_fsi174_509x513_PCRL.jp2", 509, 513, "PCRL", False),
    ("solo_fsi174_127x129_RLCP_PLT.jp2", 127, 129, "RLCP", True),
)
RGB_NAME = "synthetic_rgb_129x129_origin129_CPRL.jp2"
SOP_EPH_NAME = "synthetic_rgb_129x129_CPRL_SOP_EPH.jp2"


def read_eui():
    digest = hashlib.sha256()
    with bz2.open(SOURCE, "rb") as stream:
        data = stream.read()
    digest.update(data)
    if digest.hexdigest() != SOURCE_SHA256:
        raise ValueError(f"source FITS checksum differs: {SOURCE}")
    with fits.open(SOURCE, memmap=False) as hdul:
        return hdul[0].data, hdul[0].header


def write_eui(directory):
    image, header = read_eui()
    for name, width, height, order, plt in EUI_CROPS:
        left = top = 1200
        pixels = np.ascontiguousarray(image[top : top + height, left : left + width])
        crop_header = header.copy()
        crop_header["NAXIS1"] = width
        crop_header["NAXIS2"] = height
        crop_header["CRPIX1"] = header["CRPIX1"] - left
        crop_header["CRPIX2"] = header["CRPIX2"] - top
        hv_write_openjp2(
            str(directory / name),
            pixels,
            8,
            header_to_xml(crop_header),
            cbsize=(64, 64),
            numres=6,
            psizes=[(256, 256)] * 6,
            prog=order,
            plt=plt,
            irreversible=False,
            cratios=(16, 8, 4, 1),
        )


def rgb_header(filename):
    header = fits.Header()
    header["TELESCOP"] = "SYNTHETIC"
    header["INSTRUME"] = "RGB"
    header["WAVELNTH"] = 0
    header["DATE-OBS"] = "2026-09-19T00:00:00"
    header["DSUN_OBS"] = 149597870700.0
    header["CDELT1"] = 1.0
    header["CDELT2"] = 1.0
    header["CRPIX1"] = 65.0
    header["CRPIX2"] = 65.0
    header["FILENAME"] = filename
    return header


def write_rgb(destination, filename, origin=0, sop_eph=False):
    y, x = np.indices((129, 129))
    pixels = np.stack(((x + 3 * y) % 256, (5 * x + y) % 256, x ^ y), axis=2)
    pixels = pixels.astype(np.uint8)
    with tempfile.TemporaryDirectory() as temporary:
        plain = Path(temporary) / "plain.jp2"
        glymur.Jp2k(
            str(plain),
            data=pixels,
            grid_offset=(origin, origin),
            numres=3,
            psizes=[(256, 256)] * 3,
            cbsize=(64, 64),
            prog="CPRL",
            mct=False,
            plt=sop_eph,
            sop=sop_eph,
            eph=sop_eph,
            irreversible=False,
            cratios=(4, 2, 1),
        )
        jp2 = glymur.Jp2k(str(plain))
        boxes = jp2.box.copy()
        codestream_box = first_box(boxes, "jp2c")
        boxes.insert(
            boxes.index(codestream_box),
            jp2box.XMLBox(header_to_xml(rgb_header(filename)).getroottree()),
        )
        jp2.wrap(str(destination), boxes=boxes)


def write_reference(source, destination, kdu_transcode, remove_sop_eph=False):
    with tempfile.TemporaryDirectory() as temporary:
        codestream_path = Path(temporary) / "transcoded.j2c"
        command = [
            kdu_transcode,
            "-i",
            str(source),
            "-o",
            str(codestream_path),
            "Corder=RPCL",
            "ORGgen_plt=yes",
            "Cprecincts={128,128}",
        ]
        if remove_sop_eph:
            command += ["Cuse_sop=no", "Cuse_eph=no"]
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL)

        original = glymur.Jp2k(str(source))
        codestream = glymur.Jp2k(str(codestream_path))
        boxes = original.box.copy()
        source_codestream = first_box(boxes, "jp2c")
        boxes[boxes.index(source_codestream)] = jp2box.ContiguousCodestreamBox(
            codestream.get_codestream()
        )
        xml = first_box(boxes, "xml ")
        if xml is not None:
            boxes[boxes.index(xml)] = jp2box.XMLBox(xml.xml)
        codestream.wrap(str(destination), boxes=boxes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path, help="new, empty fixture directory")
    parser.add_argument(
        "--inputs-only",
        action="store_true",
        help="generate only the JP2 inputs, without Kakadu references",
    )
    parser.add_argument(
        "--kdu-transcode",
        default=shutil.which("kdu_transcode"),
        help="Kakadu 7.10.3 kdu_transcode executable (default: search PATH)",
    )
    args = parser.parse_args()
    if not args.inputs_only and not args.kdu_transcode:
        parser.error("kdu_transcode is required to generate reference fixtures")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error("output directory must be empty")

    original_dir = args.output_dir / "orig"
    reference_dir = args.output_dir / "trans"
    sop_dir = args.output_dir / "sop_eph"
    sop_reference_dir = sop_dir / "trans"
    for directory in (original_dir, sop_dir):
        directory.mkdir(parents=True, exist_ok=True)

    write_eui(original_dir)
    write_rgb(original_dir / RGB_NAME, "synthetic-grid-origin", origin=129)
    write_rgb(sop_dir / SOP_EPH_NAME, "synthetic-sop-eph", sop_eph=True)

    if args.inputs_only:
        return

    for directory in (reference_dir, sop_reference_dir):
        directory.mkdir(parents=True, exist_ok=True)
    for source in sorted(original_dir.glob("*.jp2")):
        write_reference(source, reference_dir / source.name, args.kdu_transcode)
    write_reference(
        sop_dir / SOP_EPH_NAME,
        sop_reference_dir / SOP_EPH_NAME,
        args.kdu_transcode,
        remove_sop_eph=True,
    )


if __name__ == "__main__":
    main()
