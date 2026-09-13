#!/bin/sh

set -eu

dir=~/hvJP2K

python3 -m venv "$dir"
"$dir/bin/pip" install --upgrade pip
"$dir/bin/pip" install --upgrade .
