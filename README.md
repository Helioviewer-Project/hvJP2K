# hvJP2K

hvJP2K provides the JPEG 2000 tools used by the Helioviewer data pipeline and
`esajpip`. It can encode Helioviewer JP2 images, validate their structure and
metadata, and build JPX movies in the format served to JHelioviewer.

The package installs these commands:

- `hv_jp2_encode` converts FITS images to Helioviewer JP2.
- `hv_jp2_verify` validates JP2 structure and the Helioviewer profile.
- `hv_jp2_decode` decodes all or part of a JP2 image.
- `hv_jp2_transcode` adds the codestream properties required by `esajpip`.
- `hv_jpx_merge` builds embedded or linked JPX movies.
- `hv_jpx_split` extracts the JP2 frames from a JPX movie.
- `hv_jpx_merged` and `hv_jpx_mergec` provide a persistent merge service for
  applications such as `esajpip`.

## Requirements

- Python 3.11 or newer
- A C compiler
- OpenJPEG 2.4 or newer, available to Glymur at runtime
- Kakadu's `kdu_transcode` executable for `hv_jp2_transcode` only

Python package dependencies are installed automatically. Kakadu is not needed
for encoding, decoding, verification, JPX merging, or JPX splitting.

## Installation

Install into any Python environment:

```sh
python3 -m pip install .
```

For example, to use a separate virtual environment:

```sh
python3 -m venv /path/to/hvjp2k-venv
/path/to/hvjp2k-venv/bin/python -m pip install .
```

This compiles the Cython extensions and the native `hv_jpx_mergec` client.
Building in the checkout creates only `build/` and `hvJP2K.egg-info/`, both of
which are ignored by Git.

## JP2 tools

### Encode FITS

```sh
hv_jp2_encode -i image.fits
```

The output is written as `image.jp2` beside the input. The encoder selects the
first image HDU by default, scales its pixels, and writes an `esajpip`-ready
codestream with RPCL progression, explicit precincts, and PLT packet-length
markers. Use `-hdu` or `-plane` to select a particular image, and use `-layers`,
`-cratio`, `-bpp`, or `-f` to control the encoding.

### Verify a JP2 file

```sh
hv_jp2_verify -i image.jp2
```

Success is silent and returns exit status zero. A validation failure is written
to standard error and returns a nonzero status. `--verbose` prints jpylyzer's
XML report. Use `--nullxml` only for legacy JP2 files with NUL-terminated XML.

The verifier targets jpylyzer 2.2.1's single-file XML structure. In addition to
the Helioviewer metadata schema, it requires the properties used by `esajpip`:
one tile, RPCL progression, explicit precincts of at least 128 by 128, and PLT
markers.

### Decode a JP2 file

```sh
hv_jp2_decode -i image.jp2 -o image.png
```

The output format is selected from the output filename. `-reduce N` discards
resolution levels. `-region {top,left},{height,width}` decodes a normalized
region of the image, with every value expressed from 0 to 1. `-xml` prints the
embedded XML metadata.

### Transcode existing JP2 files

```sh
hv_jp2_transcode -d /data/images
```

This recursively finds `.jp2` files and uses `kdu_transcode` to add RPCL
progression, 128 by 128 precincts, and PLT markers without recompressing image
samples. Each source file is replaced after its transcoded copy has been
written successfully. Use `--xml-rewrite` when the XML box must also be
rewritten.

## JPX movies

Input order is frame order. To create a self-contained JPX movie:

```sh
hv_jpx_merge -i frame0001.jp2 frame0002.jp2 frame0003.jp2 -o movie.jpx
```

To create a linked JPX movie:

```sh
hv_jpx_merge -i frame0001.jp2 frame0002.jp2 frame0003.jp2 \
    -links -o movie-linked.jpx
```

An embedded movie copies every codestream into the JPX file. A linked movie is
much smaller because it contains fragment tables and absolute `file:` URIs for
the source JP2 files. Those files must remain readable at the recorded paths
for `esajpip`, JHelioviewer, or another JPX reader to retrieve the frames.

For a sequence too large for the command line, use the request-file layout
shown in the daemon section below and run the merger directly:

```sh
hv_jpx_merge -s merge.args
```

To extract a movie, run the splitter from the directory that should receive the
numbered files:

```sh
mkdir extracted
cd extracted
hv_jpx_split -i ../movie.jpx
```

The output files are named `000.jp2`, `001.jp2`, and so on. Use an empty output
directory to avoid replacing files with those names.

## Persistent JPX merge service

Starting Python and importing the JPEG 2000 libraries adds overhead to every
merge. `hv_jpx_merged` keeps the merger loaded, while the small native
`hv_jpx_mergec` program submits requests and waits for their result.

### Start and stop the daemon

Start it in the foreground with the default socket:

```sh
hv_jpx_merged
```

The default socket is `/tmp/hv_jpx_merged_socket`. Press Ctrl-C to stop the
daemon and remove the socket. Starting another daemon on an active socket
fails. A socket left behind by a terminated daemon is detected and replaced at
the next start. The command does not fork or create a PID file. Restart it after
upgrading hvJP2K so the process loads the newly installed code.

For production, run the foreground process under the local service manager and
place its socket in a directory accessible only to the service and its client:

```sh
runtime_dir="${XDG_RUNTIME_DIR:-/tmp}/hvjp2k-$(id -u)"
mkdir -p "$runtime_dir"
chmod 700 "$runtime_dir"
hv_jpx_merged --socket "$runtime_dir/merge.socket"
```

The daemon processes filesystem paths with the permissions of its own user.
Restricting access to the socket prevents unrelated local users from submitting
merge requests.

### Submit a merge

Write the normal `hv_jpx_merge` arguments to a request file. Arguments can be
separated by spaces or newlines, and input paths can be comma-separated:

```text
-i /data/frame0001.jp2,/data/frame0002.jp2,/data/frame0003.jp2
-links
-o /data/movie.jpx
```

Submit it to the default socket:

```sh
hv_jpx_mergec -s merge.args
```

For a custom socket, pass the same path to both processes:

```sh
hv_jpx_mergec -s merge.args --socket "$runtime_dir/merge.socket"
```

The client can also read a request from standard input:

```sh
hv_jpx_mergec --socket "$runtime_dir/merge.socket" < merge.args
```

Omit `-links` from the request to create an embedded movie. Shell-style quoting
and backslash escaping are accepted when a path contains whitespace or other
special characters.

`hv_jpx_mergec` blocks until the output is complete. It returns zero after a
successful merge. Parse, input, and output errors return a nonzero status and
are written to standard error; the full traceback remains in the daemon log.
The daemon continues serving subsequent requests after a failed merge.

The daemon accepts multiple clients concurrently, and each client waits for its
own response. Overlapping requests can increase aggregate memory and I/O use.

## Tests

With the installed commands on `PATH`, run:

```sh
./hvJP2K/jp2/test/test
./hvJP2K/jpx/test/test
```

To test an installation whose commands are not on `PATH`:

```sh
HVJP2K_BIN="/path/to/hvjp2k-venv/bin" \
HVJP2K_PYTHON="/path/to/hvjp2k-venv/bin/python" \
./hvJP2K/jpx/test/test
```

The project is distributed under the MIT license.
