from setuptools import setup
from Cython.Build import cythonize

kwargs = {'name': 'hvJP2K',
          'description': 'JPEG2000 tools for the Helioviewer project',
          'long_description': open('README.md').read(),
          'author': 'SWHV OMA',
          'author_email': 'swhv@oma.be',
          'url': 'https://github.com/helioviewer/...',
          'ext_modules': cythonize(['hvJP2K/jp2/jp2_common.pyx', 'hvJP2K/jpx/jpx_common.pyx', 'hvJP2K/jpx/jpx_merge.py']),
          'packages': ['hvJP2K', 'hvJP2K.jp2', 'hvJP2K.jp2.data', 'hvJP2K.jpx'],
          'package_data': {'hvJP2K.jp2': ['data/*.sch', 'test/*.jp2', 'test/*.ppm'], 'hvJP2K.jpx': ['test/*/*.jp2', 'test/*/*.jpx']},
          'scripts': ['bin/hv_jp2_decode', 'bin/hv_jp2_encode', 'bin/hv_jp2_verify', 'bin/hv_jpx_merge', 'bin/hv_jpx_merged', 'bin/hv_jpx_split'],
          'license': 'MIT'}

instllrqrs = ['cython', 'numpy', 'lxml>=2.3', 'pillow', 'glymur>=0.5.10']
# jpylyzer>=1.11.2 - doesn't work
kwargs['install_requires'] = instllrqrs

clssfrs = ["Programming Language :: Python",
           "Programming Language :: Python :: 2.7",
           "Programming Language :: Python :: 3.3",
           "Programming Language :: Python :: Implementation :: CPython",
           "License :: OSI Approved :: MIT License",
           "Development Status :: 5 - Production/Stable",
           "Operating System :: MacOS",
           "Operating System :: POSIX :: Linux",
           "Operating System :: Microsoft :: Windows :: Windows XP",
           "Intended Audience :: Science/Research",
           "Intended Audience :: Information Technology",
           "Topic :: Software Development :: Libraries :: Python Modules"]
kwargs['classifiers'] = clssfrs

kwargs['version'] = '0.3'

setup(**kwargs)
