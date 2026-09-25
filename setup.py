import os

from Cython.Build import cythonize
from setuptools import setup

from distutils.ccompiler import new_compiler
from distutils.command.build_scripts import build_scripts
from distutils.sysconfig import customize_compiler


class BuildScripts(build_scripts):
    def run(self):
        super().run()

        compiler = new_compiler(force=self.force)
        customize_compiler(compiler)
        build_ext = self.get_finalized_command("build_ext")
        source = "bin/hv_jpx_mergec.c"
        objects = compiler.compile([source], output_dir=build_ext.build_temp)
        compiler.link_executable(objects, os.path.join(self.build_dir, "hv_jpx_mergec"))

    def get_source_files(self):
        return super().get_source_files() + ["bin/hv_jpx_mergec.c"]


setup(
    ext_modules=cythonize(
        [
            "hvJP2K/jp2/jp2_packets.pyx",
            "hvJP2K/jp2/jp2_precincts.py",
            "hvJP2K/jpx/jpx_common.pyx",
            "hvJP2K/jpx/jpx_merge.pyx",
        ],
        build_dir="build/cython",
        language_level=3,
    ),
    cmdclass={"build_scripts": BuildScripts},
    scripts=[
        "bin/hv_jp2_decode",
        "bin/hv_jp2_encode",
        "bin/hv_jp2_verify",
        "bin/hv_jpx_merge",
        "bin/hv_jpx_merged",
        "bin/hv_jpx_split",
        "bin/hv_jp2_transcode",
    ],
)
