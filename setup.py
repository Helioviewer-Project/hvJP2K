from setuptools import setup

kwargs = {'name': 'hvJP2K',
          'description': 'JPEG2000 tools for the Helioviewer project',
          'long_description': open('README.md').read(),
          'author': 'SWHV OMA',
          'author_email': 'swhv@oma.be',
          'url': 'https://github.com/helioviewer/...',
          'packages': ['hvJP2K', 'hvJP2K.jp2', 'hvJP2K.jpx', 'hvJP2K.jp2.test', 'hvJP2K.jpx.test'],
          'scripts': ['bin/hv_jp2_decode', 'bin/hv_jp2_encode', 'bin/hv_jpx_merge', 'bin/hv_jpx_split'],
          'license': 'MIT'}

instllrqrs = ['glymur>=0.5.10']
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

kwargs['version'] = '0.1'

setup(**kwargs)
