#!/bin/sh

dir=~/hvJP2K

python -m venv ${dir}
${dir}/bin/pip install cython
${dir}/bin/pip install --upgrade .

cc -O2 bin/hv_jpx_mergec.c -o ${dir}/bin/hv_jpx_mergec
