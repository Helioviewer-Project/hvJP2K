# hvJP2K

A collection of JPEG2000 tools useful for the Helioviewer Project:

- `hv_jp2_decode` -- replacement for `kdu_expand`, sufficient for the web client image tile decoding;
- `hv_jp2_encode` -- proto-replacement for `fits2img`, not yet capable of emitting conforming JP2 files;
- `hv_jp2_transcode` -- wrapper for `kdu_transcode`, it can output JP2 format and can reparse the XML metadata to ensure conformity;
- `hv_jp2_verify` -- verify the conformity of JP2 file format to ensure end-to-end compatibility;
- `hv_jpx_merge` -- standalone replacement for `kdu_merge`, it can create JPX movies out of JP2 files;
- `hv_jpx_mergec` -- client for `hv_jpx_merged`, written in C;
- `hv_jpx_merged` -- Unix domain sockets threaded server for JPX merging functionality, it avoids the startup overhead of `hv_jpx_merge`;
- `hv_jpx_split` -- split JPX movies into standalone JP2 files.

This software is mainly written in Python and is based on the [glymur](https://github.com/quintusdias/glymur/) and [jpylyzer](https://github.com/openpreserve/jpylyzer/) libraries.

## Installation

A bootstrap script that assumes Python 3 is provided.
