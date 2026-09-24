# hvJP2K

JPEG 2000 tools for the [Helioviewer Project](https://github.com/Helioviewer-Project/hvJP2K).

hvJP2K turns FITS images into Helioviewer JP2 files, checks that JP2 files
meet the Helioviewer profile, and assembles them into the JPX movies that
`esajpip` serves to JHelioviewer.

- [What's included](#whats-included)
- [Quick start](#quick-start)
- [Installation](#installation)
- [JP2 tools](#jp2-tools)
- [JPX movies](#jpx-movies)
- [Persistent JPX merge service](#persistent-jpx-merge-service)
- [Running the tests](#running-the-tests)

## What's included

| Command | What it does |
| --- | --- |
| `hv_jp2_encode` | Convert a FITS image to a Helioviewer JP2 file. |
| `hv_jp2_decode` | Decode all or part of a JP2 file to an ordinary image. |
| `hv_jp2_verify` | Check a JP2 file's structure and Helioviewer metadata. |
| `hv_jp2_transcode` | Add the codestream properties `esajpip` needs to existing JP2 files (requires Kakadu). |
| `hv_jpx_merge` | Combine JP2 files into an embedded or linked JPX movie. |
| `hv_jpx_merged` | Keep the merger loaded as a background service. |
| `hv_jpx_mergec` | Small native client that sends merge requests to `hv_jpx_merged`. |
| `hv_jpx_split` | Extract the JP2 frames from an embedded JPX movie. |

## Quick start

```sh
python3 -m pip install .              # build and install the commands

hv_jp2_encode -i image.fits -p        # writes the JP2 and prints its path
hv_jp2_verify -i image.jp2            # silent on success

hv_jpx_merge -i frame0001.jp2 frame0002.jp2 -o movie.jpx
```

## Installation

### Requirements

- Python 3.11 or newer
- A C compiler
- OpenJPEG 2.4 or newer, available to Glymur at runtime
- Kakadu's `kdu_transcode`, **only** for `hv_jp2_transcode`

The Python dependencies (Astropy, Glymur, jpylyzer, lxml, NumPy, Pillow) are
installed automatically. Encoding, decoding, verification, merging and
splitting all work without Kakadu.

### Install with pip

From the repository checkout, install into any Python environment:

```sh
python3 -m pip install .
```

or into a dedicated virtual environment:

```sh
python3 -m venv /path/to/hvjp2k-venv
/path/to/hvjp2k-venv/bin/python -m pip install .
```

Installing compiles the Cython extensions and the native `hv_jpx_mergec`
client. The build leaves only `build/` and `hvJP2K.egg-info/` in the checkout,
and Git ignores both.

### Install with `bootstrap.sh`

`./bootstrap.sh` does the same in one step: it creates a virtual environment
in `~/hvJP2K`, installs hvJP2K into it, and confirms that Glymur finds
OpenJPEG 2.4 or newer, printing the library it loaded.

## JP2 tools

### `hv_jp2_encode`: FITS to JP2

```sh
hv_jp2_encode -i image.fits
hv_jp2_encode -i image.fits -o /data/jp2 -O -p     # /data/jp2/YYYY/MM/DD/…
```

**Input and output**

| Option | Default | Purpose |
| --- | --- | --- |
| `-i`, `--input FITS` | required | Input FITS file. |
| `--hdu INDEX` | first suitable HDU | Use this HDU instead. |
| `-o`, `--out-dir DIRECTORY` | current directory | Base output directory. |
| `-O`, `--out-dateobs-dir` | off | Add a `YYYY/MM/DD` subdirectory taken from `DATE-OBS`. |
| `-p`, `--print-filename` | off | Print the path of the finished file. |
| `-N`, `--no-verify` | off | Skip FITS checksum verification. |
| `--threads N` | `1` | Use 1–64 OpenJPEG threads per image. |
| `-v`, `--verbose` | off | Show OpenJPEG diagnostics. |

**Metadata**

| Option | Default | Purpose |
| --- | --- | --- |
| `-c`, `--contact CONTACT` | `swhv@oma.be` | Contact recorded in the Helioviewer metadata. |
| `-C`, `--colormap NAME` | none (grayscale) | Embed a packaged RGB palette; `--help` lists the names. |
| `--date-obs`, `--telescop`, `--instrume`, `--detector`, `--wavelnth` | none | Override that keyword in the embedded metadata. |

**Encoding**

| Option | Default | Purpose |
| --- | --- | --- |
| `--cratio RATIO` | `3.3` | Compression ratio. |
| `--nlayers COUNT` | `4` | Quality layers. |
| `--nresolutions COUNT` | `6` | Resolution levels. |
| `--precinctw PIXELS` | `128` | Precinct width. |
| `--precincth PIXELS` | `128` | Precinct height. |

> [!IMPORTANT]
> The defaults define the **Helioviewer JPEG 2000 profile** that `esajpip` and
> JHelioviewer rely on:
>
> - RPCL progression
> - PLT packet-length markers
> - 4 quality layers
> - 6 resolution levels
> - 128×128 precincts
>
> Only `--cratio` is meant to be tuned. Changing any other encoding option
> produces files outside the profile.

How the encoder works:

- **Output name.** The input filename with a `.jp2` extension, so
  `image.fits` becomes `image.jp2`. A compression suffix (`.gz`, `.bz2`,
  `.fz`, `.xz`, `.Z`) is dropped first. `--out-dateobs-dir` requires
  `DATE-OBS` in the header.
- **Which HDU.** It uses the first HDU whose image is a two-dimensional
  `uint8` array. This covers both ordinary image HDUs and tile-compressed
  images stored in binary tables.
- **Pixels.** Values are copied as-is, with no clipping, scaling or transfer
  function, and flipped vertically from FITS order to raster order.
- **Color.** Output is grayscale by default. `--colormap` adds a 256-entry
  palette while keeping a single 8-bit component.
- **Metadata.** The JP2 embeds the full logical FITS header as XML, including
  joined long strings, repeated commentary cards, HIERARCH keywords and
  comments, with their text unchanged by escaping. Characters that XML 1.0
  forbids become the Unicode replacement character. The keyword overrides
  apply only to this embedded copy.
- **Checksums.** FITS checksums are verified when present, unless `--no-verify`
  is given.

#### From Python

Producers that already hold the image in memory can skip the intermediate FITS
file:

```python
from hvJP2K.jp2.jp2_encode import encode

encode(
    image,
    header,
    "image.jp2",
    colormap=None,
    contact="swhv@oma.be",
    compression_ratio=3.3,
    threads=1,
)
```

- `image`: a two-dimensional NumPy `uint8` array in FITS row order.
- `header`: an Astropy FITS header.
- The output filename is the caller's choice.

### `hv_jp2_decode`: JP2 to image

```sh
hv_jp2_decode -i image.jp2 -o image.png
```

The output format follows the extension of the output filename.

| Option | Purpose |
| --- | --- |
| `-i JP2`, `-o FILE` | Input JP2 and output image. `-o` is omitted with `-no_decode`. |
| `-reduce N` | Discard `N` resolution levels. |
| `-region {top,left},{height,width}` | Decode only part of the image. All four values are fractions from 0 to 1. |
| `-no_decode -record FILE` | Parse the main header without decoding and write `Clevels=N` for the Helioviewer API. |
| `-codestream_components` | Suppress multi-component and color transforms. |
| `-xml` | Print the embedded XML metadata. |
| `--threads N` | Use 1–64 OpenJPEG threads per image (default 1). |
| `-v`, `--verbose` | Verbose output. |

### `hv_jp2_verify`: check a JP2 file

```sh
hv_jp2_verify -i image.jp2
```

It prints nothing and exits with status 0 when the file is valid. Otherwise it
writes the problem to standard error and exits with a nonzero status.

| Option | Purpose |
| --- | --- |
| `-i JP2` | File to check (required). |
| `-schema FILE` | Use an alternate Schematron file. |
| `-n`, `--nullxml` | Accept a NUL-terminated XML box (legacy files only). |
| `-v`, `--verbose` | Print jpylyzer's full XML report. |

Besides the Helioviewer metadata schema, the verifier requires what `esajpip`
relies on: a single tile, RPCL progression, explicit precincts of at least
128 by 128, and PLT markers. It targets the XML report format of jpylyzer 2.2.1.

### `hv_jp2_transcode`: upgrade existing JP2 files

```sh
hv_jp2_transcode -d /data/images
```

Recursively finds `.jp2` files under the directory and uses Kakadu's
`kdu_transcode` to add RPCL progression, 128 by 128 precincts and PLT markers
without recompressing the image. Each file is replaced only after its
transcoded copy has been written successfully. Add `-x`/`--xml-rewrite` to
rewrite the XML box as well.

## JPX movies

A JPX movie is a sequence of JP2 frames, in the order given on the command
line. There are two kinds:

- **Embedded** movies copy every frame into the JPX file. They are
  self-contained.
- **Linked** movies store only fragment tables and absolute `file:` URIs that
  point to the original JP2 files. They are much smaller, but those files must
  stay readable at the same paths for `esajpip`, JHelioviewer or any other
  reader.

```sh
# Embedded
hv_jpx_merge -i frame0001.jp2 frame0002.jp2 frame0003.jp2 -o movie.jpx

# Linked
hv_jpx_merge -i frame0001.jp2 frame0002.jp2 frame0003.jp2 \
    -links -o movie-linked.jpx
```

When the frame list is too long for the command line, put the arguments in a
request file (see [Submit a merge](#submit-a-merge) for the format) and run:

```sh
hv_jpx_merge -s merge.args
```

To pull the frames back out of an embedded movie, run the splitter in the
directory that should receive them:

```sh
mkdir extracted && cd extracted
hv_jpx_split -i ../movie.jpx
```

Frames are written as `000.jp2`, `001.jp2` and so on. Existing files with
those names are overwritten, so start from an empty directory.

## Persistent JPX merge service

Each `hv_jpx_merge` run pays the cost of starting Python and loading the
JPEG 2000 libraries. For frequent merges, such as those made by `esajpip`,
`hv_jpx_merged` keeps the merger loaded, and the lightweight native
`hv_jpx_mergec` client sends it requests.

### Start and stop the daemon

```sh
hv_jpx_merged                        # listens on /tmp/hv_jpx_merged_socket
```

- It runs in the foreground; it does not fork or write a PID file.
- Ctrl-C stops it and removes the socket.
- A second daemon on a socket that is in use refuses to start. A stale socket
  left by a crashed daemon is replaced automatically.
- Restart it after upgrading hvJP2K so that it loads the new code.

**In production**, run it under your service manager and put the socket in a
directory that only the service and its clients can reach:

```sh
runtime_dir="${XDG_RUNTIME_DIR:-/tmp}/hvjp2k-$(id -u)"
mkdir -p "$runtime_dir"
chmod 700 "$runtime_dir"
hv_jpx_merged --socket "$runtime_dir/merge.socket"
```

The daemon reads and writes files with its own user's permissions, so
restricting the socket keeps other local users from submitting merges.

### Submit a merge

A request file holds the usual `hv_jpx_merge` arguments, separated by spaces
or newlines. Input paths may also be comma-separated:

```text
-i /data/frame0001.jp2,/data/frame0002.jp2,/data/frame0003.jp2
-links
-o /data/movie.jpx
```

Leave out `-links` for an embedded movie. Paths containing spaces or other
special characters can use shell-style quoting or backslash escapes.

```sh
hv_jpx_mergec -s merge.args                                   # default socket
hv_jpx_mergec -s merge.args --socket "$runtime_dir/merge.socket"
hv_jpx_mergec --socket "$runtime_dir/merge.socket" < merge.args   # from stdin
```

The client and the daemon must use the same socket path.

`hv_jpx_mergec` waits until the movie is written:

- **Success:** exit status 0.
- **Failure** (bad arguments, unreadable input, unwritable output): nonzero
  exit status and a message on standard error. The full traceback is in the
  daemon's log, and the daemon keeps serving later requests.

Several clients can be served at once, each waiting for its own result.
Overlapping requests add up in memory and I/O use.

## Running the tests

With the installed commands on your `PATH`:

```sh
./hvJP2K/jp2/test/test
./hvJP2K/jpx/test/test
```

To test an installation that is not on your `PATH`, point the tests at it:

```sh
HVJP2K_BIN="/path/to/hvjp2k-venv/bin" \
HVJP2K_PYTHON="/path/to/hvjp2k-venv/bin/python" \
./hvJP2K/jpx/test/test
```

## License

MIT; see [LICENSE](LICENSE).
