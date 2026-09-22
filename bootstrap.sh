#!/bin/sh

set -eu

dir=${HOME}/hvJP2K

python3 -m venv --without-scm-ignore-files "$dir"
"$dir/bin/pip" install --upgrade pip
"$dir/bin/pip" install --upgrade .
"$dir/bin/python" - <<'PY'
from glymur import version
from glymur.lib import openjp2

if version.openjpeg_version_tuple < (2, 4):
    raise SystemExit(
        'OpenJPEG 2.4 or newer is required; found {0}'.format(
            version.openjpeg_version))

print('OpenJPEG {0}: {1}'.format(
    version.openjpeg_version, openjp2.OPENJP2._name))
PY
