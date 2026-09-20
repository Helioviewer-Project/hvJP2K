import csv
import math
import os
import re
import socket
from datetime import datetime, timezone
from functools import cache
from importlib.resources import files
from numbers import Integral, Real
from pathlib import Path

import numpy as np
from astropy.io.fits.card import Undefined
from lxml import etree

from .jp2_write import hv_write_openjp2

COLORMAPS = (
    "aia171",
    "aspiicsWBF",
    "aspiicsFE",
    "aspiicsHE",
    "aspiicsPolWBF",
    "eui174",
    "eui304",
    "eui1216",
    "citrus",
    "hot",
    "jet",
)

_XML_NAME_START = re.compile(r"[A-Za-z_]")
_XML_NAME_CHARACTER = re.compile(r"[A-Za-z0-9_.-]")
_XML_INVALID_CHARACTER = re.compile(
    r"[^\x09\x0A\x0D\x20-\uD7FF\uE000-\uFFFD\U00010000-\U0010FFFF]"
)
_COMMENTARY_KEYWORDS = ("", "COMMENT", "HISTORY")


def _xml_text(value):
    return _XML_INVALID_CHARACTER.sub("\ufffd", str(value))


def _xml_keyword(keyword):
    keyword = keyword or "COMMENT"
    name = "".join(
        character if _XML_NAME_CHARACTER.fullmatch(character) else "."
        for character in keyword
    )
    if not _XML_NAME_START.fullmatch(name[0]):
        name = "_" + name
    return keyword, name


def _card_value(card):
    value = card.value
    if isinstance(value, Undefined):
        return ""
    if isinstance(value, str):
        return _xml_text(value)

    # The public card image preserves FITS spelling and formats values created
    # in memory, including logical values as T and F.
    value_field = card.image.partition("=")[2].split("/", 1)[0]
    return _xml_text(value_field.strip())


def header_to_xml(header, contact=None, title=None):
    """Convert the logical FITS header into Helioviewer XML metadata."""

    if not hasattr(header, "cards"):
        raise TypeError("header must be an Astropy FITS header")

    root = etree.Element("meta")
    fits = etree.SubElement(root, "fits")

    # Astropy has already joined each CONTINUE chain into its logical card.
    for card in header.cards:
        keyword, element_name = _xml_keyword(card.keyword)
        element = etree.SubElement(fits, element_name)
        if element_name != keyword:
            element.set("keyword", _xml_text(keyword))
        if card.keyword in _COMMENTARY_KEYWORDS:
            element.set("comment", _xml_text(card.value))
        elif card.comment:
            element.set("comment", _xml_text(card.comment))
        if card.keyword not in _COMMENTARY_KEYWORDS:
            element.text = _card_value(card)

    helioviewer = etree.SubElement(root, "helioviewer")
    if contact:
        comment = etree.SubElement(helioviewer, "HV_COMMENT")
        created = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        comment.text = (
            f"\n Title         : {_xml_text(title or '')}\n"
            f" Contact       : {_xml_text(contact)}\n"
            " Copyright     : Public Domain\n"
            f" Creation Time : {created.replace('+00:00', 'Z')}\n"
            " Software      : hvJP2K\n"
            f" Source        : {_xml_text(socket.gethostname())}\n"
        )

    return root


@cache
def load_colormap(name):
    if name not in COLORMAPS:
        raise ValueError(f"Unknown colormap: {name}")

    resource = files(__package__).joinpath("data", f"{name}.csv")
    try:
        with resource.open("r", encoding="ascii", newline="") as stream:
            values = [[int(value) for value in row] for row in csv.reader(stream)]
    except OSError as error:
        raise RuntimeError(f"Colormap data is unavailable: {name}") from error
    except ValueError as error:
        raise ValueError(f"Invalid colormap: {name}") from error

    if len(values) != 256 or any(len(row) != 3 for row in values):
        raise ValueError(f"Invalid colormap: {name}")
    if any(value < 0 or value > 255 for row in values for value in row):
        raise ValueError(f"Invalid colormap: {name}")
    palette = np.asarray(values, dtype=np.uint8)
    palette.flags.writeable = False
    return palette


def encode(
    image,
    header,
    output,
    *,
    colormap=None,
    contact="swhv@oma.be",
    compression_ratio=3.3,
    layers=4,
    resolutions=6,
    precinct=(128, 128),
    verbose=False,
):
    """Encode a Helioviewer JP2 from a two-dimensional 8-bit FITS image.

    ``precinct`` contains ``(height, width)`` in pixels. Both dimensions must
    be powers of two from 128 through 32768, as required by the served profile.
    """

    if not isinstance(image, np.ndarray) or image.ndim != 2:
        raise ValueError("image must be a two-dimensional NumPy array")
    if image.dtype != np.uint8:
        raise ValueError("image must have dtype uint8")
    if image.size == 0:
        raise ValueError("image must not be empty")
    if (
        isinstance(layers, bool)
        or not isinstance(layers, Integral)
        or not 1 <= layers <= 32
    ):
        raise ValueError("layers must be between 1 and 32")
    if (
        isinstance(resolutions, bool)
        or not isinstance(resolutions, Integral)
        or not 1 <= resolutions <= 32
    ):
        raise ValueError("resolutions must be between 1 and 32")
    if (
        isinstance(compression_ratio, bool)
        or not isinstance(compression_ratio, Real)
        or not math.isfinite(compression_ratio)
        or compression_ratio < 1
    ):
        raise ValueError("compression_ratio must be a finite number of at least 1")
    try:
        precinct = tuple(precinct)
    except TypeError as error:
        raise ValueError("precinct must contain height and width") from error
    if len(precinct) != 2:
        raise ValueError("precinct must contain height and width")
    if any(
        isinstance(value, bool) or not isinstance(value, Integral) for value in precinct
    ):
        raise ValueError("precinct dimensions must be integers")
    precinct = tuple(int(value) for value in precinct)
    if any(value < 128 or value > 32768 or value & (value - 1) for value in precinct):
        raise ValueError(
            "precinct dimensions must be powers of two from 128 through 32768"
        )

    output = os.fspath(output)
    palette = None if colormap is None else load_colormap(colormap)
    metadata = header_to_xml(header, contact, Path(output).name)
    ratios = [compression_ratio * 2**index for index in reversed(range(layers))]

    hv_write_openjp2(
        output,
        np.flipud(image),
        8,
        metadata,
        palette=palette,
        prog="RPCL",
        cratios=ratios,
        numres=resolutions,
        psizes=[precinct] * resolutions,
        plt=True,
        irreversible=True,
        verbose=verbose,
    )
