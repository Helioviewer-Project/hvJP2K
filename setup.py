from Cython.Build import cythonize
from setuptools import setup

with open("README.md", encoding="utf-8") as readme:
    long_description = readme.read()

setup(
    name="hvJP2K",
    version="0.6",
    description="JPEG2000 tools for the Helioviewer Project",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="SWHV ROB",
    author_email="swhv@oma.be",
    url="https://github.com/Helioviewer-Project/hvJP2K",
    license="MIT",
    python_requires=">=3.11",
    ext_modules=cythonize(
        [
            "hvJP2K/jp2/jp2_common.pyx",
            "hvJP2K/jpx/jpx_common.pyx",
            "hvJP2K/jpx/jpx_mmap.pyx",
            "hvJP2K/jpx/jpx_merge.py",
        ],
        build_dir="build/cython",
        language_level=3,
    ),
    packages=["hvJP2K", "hvJP2K.jp2", "hvJP2K.jp2.data", "hvJP2K.jpx"],
    package_data={"hvJP2K.jp2": ["data/*.sch"]},
    scripts=[
        "bin/hv_jp2_decode",
        "bin/hv_jp2_encode",
        "bin/hv_jp2_verify",
        "bin/hv_jpx_merge",
        "bin/hv_jpx_merged",
        "bin/hv_jpx_split",
        "bin/hv_jp2_transcode",
    ],
    install_requires=[
        "astropy>=6.0",
        "glymur>=0.14.2",
        "jpylyzer==2.2.1",
        "lxml>=5.0",
        "numpy>=1.26",
        "pillow>=10.0",
    ],
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Information Technology",
        "Intended Audience :: Science/Research",
        "Operating System :: POSIX",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: Implementation :: CPython",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
