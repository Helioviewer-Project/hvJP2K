# Transcode fixtures

The four `solo_fsi174_*` inputs use pixels from the full EUI FSI 174 image
acquired aboard Solar Orbiter:
`source/solo_L2_eui-fsi174-image_20260919T000055144_V00_8bit.fits.bz2`.
The uncompressed FITS has SHA-256
`473dd9a636a09b76675ce0d4a0b7ac0c3cb8bf32c59d1fe2095831502c92b049`.
Their crop ranges use NumPy's `[row_start:row_end, column_start:column_end]`
indexing:

| Input suffix | Crop | Progression | Input PLT |
| --- | --- | --- | --- |
| `510x514_LRCP` | `[1200:1714, 1200:1710]` | LRCP | No |
| `511x513_LRCP_PLT` | `[1200:1713, 1200:1711]` | LRCP | Yes |
| `509x513_PCRL` | `[1200:1713, 1200:1709]` | PCRL | No |
| `127x129_RLCP_PLT` | `[1200:1329, 1200:1327]` | RLCP | Yes |

The `synthetic_rgb_129x129_origin129_CPRL` input has three components and a
grid origin of (129,129). At pixel coordinates (x,y), its channels are
`(x + 3*y) % 256`, `(5*x + y) % 256`, and `x ^ y`. It uses CPRL progression,
three resolutions, 256×256 precincts, 64×64 code blocks, three layers with
`cratios=(4, 2, 1)`, and a reversible transform. The target 128×128 precincts
include nine packets whose precincts have no code blocks. Kakadu 7.10.3 and
8.4.1 encode all nine as `80`, matching the native transcoder.
Glymur warns about this JP2 because its IHDR check compares the image size to
`Xsiz`/`Ysiz` without subtracting the nonzero origin; jpylyzer validates it.

The `sop_eph/` input uses the same synthetic RGB pixel formulas at origin
(0,0), with CPRL progression and SOP/EPH markers. Its `trans/` reference
comes from Kakadu 7.10.3 with `Cuse_sop=no Cuse_eph=no` in addition to the
usual transcode options. Kakadu's default transcode retains SOP/EPH; the
test checks that behavior separately when Kakadu is available.

The EUI inputs were written with `hv_write_openjp2` using `numres=6`,
`psizes=[(256, 256)] * 6`, `cbsize=(64, 64)`, `cratios=(16, 8, 4, 1)`, and
`irreversible=False`. The last layer is lossless. The source FITS header is
embedded as XML, with image dimensions and reference pixels adjusted for each
crop. The JP2 pixels retain FITS row order, and `CRPIX2` is adjusted for the
crop only. `hv_jp2_encode` flips rows before encoding, so these fixtures have
different pixel orientation from its output. The matching `trans/` files were
made with Kakadu 7.10.3 `kdu_transcode` using
`Corder=RPCL ORGgen_plt=yes Cprecincts={128,128}`, then wrapped as JP2 with
`--xml-rewrite`. The preexisting AIA reference used Kakadu 7.7.

The built-in transcoder's output for all six `orig/` files and the SOP/EPH
input matches the corresponding Kakadu references byte for byte except for
codestream COM markers.

From the repository root, regenerate the EUI and synthetic inputs and their
Kakadu references into a new, empty directory with:

```sh
PYTHONPATH=. python hvJP2K/jp2/test/transcode/generate_fixtures.py \
    /tmp/hvjp2k-fixtures --kdu-transcode /path/to/kdu_transcode
```

Without Kakadu, generate the six JP2 inputs with:

```sh
PYTHONPATH=. python hvJP2K/jp2/test/transcode/generate_fixtures.py \
    /tmp/hvjp2k-inputs --inputs-only
```

The checked-in bytes were reproduced with Glymur 0.14.8, OpenJPEG 2.5.4, and
Kakadu 7.10.3. A regeneration check with OpenJPEG 2.5.0 produced the same EUI
codestreams apart from their COM markers. The script checks the bundled FITS
checksum and writes all 12 JP2 files in its full mode. The AIA pair predates
the script and is not regenerated. The normal `test` command uses only the
checked-in fixtures. Kakadu is needed to regenerate their references or to run
the optional comparison branch.
