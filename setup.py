#! /usr/bin/env python

from __future__ import print_function
from setuptools import setup, find_packages

# Force distutils to use py_compile.compile() function with 'doraise' argument
# set to True, in order to raise an exception on compilation errors
import py_compile
orig_py_compile = py_compile.compile

def doraise_py_compile(file, cfile=None, dfile=None, doraise=False):
	orig_py_compile(file, cfile=cfile, dfile=dfile, doraise=True)

py_compile.compile = doraise_py_compile


# Trove classifiers for PyPI
classifiers = {"classifiers": [
	"Development Status :: 4 - Beta",
	"Environment :: Console",
	"Environment :: Other Environment",
	"Intended Audience :: Developers",
	"Intended Audience :: End Users/Desktop",
	"License :: OSI Approved :: BSD License",
	"Natural Language :: English",
	"Operating System :: OS Independent",
	"Programming Language :: Python",
	"Topic :: Multimedia :: Graphics",
	"Topic :: Multimedia :: Graphics :: Graphics Conversion",
]}

long_description = """\
FontTools/TTX is a library to manipulate font files from Python.
It supports reading and writing of TrueType/OpenType fonts, reading
and writing of AFM files, reading (and partially writing) of PS Type 1
fonts. The package also contains a tool called "TTX" which converts
TrueType/OpenType fonts to and from an XML-based format.
"""


def guess_next_dev_version(version):
	""" If the distance from the last version tag is N != 0, increase the
	last number by one, and append '.devN' suffix. Else return the version tag
	as is.

	Note: The version tag must be two to three non-negative integer values,
	separated by dots: MAJOR.MINOR[.MICRO].
	When 'MICRO' is omitted, it's assumed to be 0.

	>>> from setuptools_scm.version import meta
	>>> guess_next_dev_version(meta('3.1'))
	3.1
	>>> guess_next_dev_version(meta('3.1', distance=4))
	3.1.1.dev4
	"""
	if version.exact:
		return version.format_with("{tag}")
	else:
		import re

		tag = str(version.tag)
		version_tag_re = re.compile(r"^([0-9]+.[0-9]+)(?:.([0-9]+))?$")
		try:
			major_minor, micro = version_tag_re.match(tag).groups()
		except AttributeError:
			raise ValueError(
				'Invalid version tag: %r. It must match MAJOR.MINOR[.MICRO]' % tag)
		return '%s.%d.dev%s' % (
			major_minor, int(micro or '0') + 1, version.distance)


DESCRIBE_COMMAND = 'git describe --dirty --tags --long'


def my_scm_version():
	from setuptools_scm.git import parse as _parse

	def parse(root, describe_command=DESCRIBE_COMMAND):
		return _parse(root, describe_command)

	return {
		"write_to": "Lib/fontTools/version.py",
		"version_scheme": guess_next_dev_version,
		"parse": parse,
	}


setup(
	name="fonttools",
	use_scm_version=my_scm_version,
	description="Tools to manipulate font files",
	author="Just van Rossum",
	author_email="just@letterror.com",
	maintainer="Behdad Esfahbod",
	maintainer_email="behdad@behdad.org",
	url="http://github.com/behdad/fonttools",
	license="OpenSource, BSD-style",
	platforms=["Any"],
	long_description=long_description,
	package_dir={'': 'Lib'},
	packages=find_packages("Lib"),
	py_modules=['sstruct', 'xmlWriter'],
	extra_path='FontTools',
	data_files=[('share/man/man1', ["Doc/ttx.1"])],
	setup_requires=[
		"setuptools_scm>=1.11.1",
	],
	entry_points={
		'console_scripts': [
			"ttx = fontTools.ttx:main",
			"pyftsubset = fontTools.subset:main",
			"pyftmerge = fontTools.merge:main",
			"pyftinspect = fontTools.inspect:main"
		]
	},
	**classifiers
)
