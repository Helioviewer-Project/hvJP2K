# hvJP2K

JPEG 2000 tools used by the Helioviewer data pipeline and `esajpip`.

The package provides commands to encode and decode JP2 images, verify the
Helioviewer JP2 profile, transcode codestreams with Kakadu, and merge or split
JPX movies. `hv_jpx_merge` emits the codestream, layer, association, and data
reference boxes consumed by `esajpip`.

## Requirements

- Python 3.11 or newer
- OpenJPEG 2.4 or newer
- A C compiler
- Kakadu's `kdu_transcode` for `hv_jp2_transcode` only

## Installation

Install into the current Python environment:

```sh
python3 -m pip install .
```

For the traditional self-contained installation under `~/hvJP2K`:

```sh
./bootstrap.sh
```

## Commands

- `hv_jp2_verify -i image.jp2` validates both JP2 structure and the
  Helioviewer profile. Pass `--nullxml` only for legacy files whose XML box is
  NUL-terminated.
- `hv_jp2_decode -i image.jp2 -o image.png` decodes a JP2 image. `-reduce N`
  selects a lower resolution and `-region {top,left},{height,width}` selects a
  normalized region.
- `hv_jp2_encode -i image.fits` creates an `esajpip`-ready JP2 image beside
  the FITS input, including RPCL progression, explicit precincts, and PLT
  packet-length markers.
- `hv_jp2_transcode -d directory` recursively transcodes JP2 files in place.
- `hv_jpx_merge -i first.jp2 second.jp2 -o movie.jpx` creates an embedded JPX
  movie. Add `-links` to create a JPX that references the source JP2 files.
- `hv_jpx_merged` keeps the Python merger loaded for repeated requests.
  `hv_jpx_mergec -s arguments.txt` sends the same argument-file syntax accepted
  by `hv_jpx_merge` to that daemon, waits for the merge to finish, and reports
  failures through its exit status and standard error.
- `hv_jpx_split -i movie.jpx` extracts numbered JP2 files in the current
  directory.

The verifier targets jpylyzer 2.2.1's current single-file XML structure. It
also checks the properties required by `esajpip`: one tile, RPCL progression,
explicit precincts of at least 128 by 128, and PLT markers.
