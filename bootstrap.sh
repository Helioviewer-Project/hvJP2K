#!/bin/sh

dir=~/hvJP2K
python -m venv ${dir}
${dir}/bin/pip install cython
${dir}/bin/pip install --upgrade .
