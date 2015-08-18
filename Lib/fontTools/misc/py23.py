"""Python 2/3 compat layer."""

from __future__ import print_function, division, absolute_import
import sys

try:
	basestring
except NameError:
	basestring = str

try:
	unicode
except NameError:
	unicode = str

try:
	unichr

	if sys.maxunicode < 0x10FFFF:
		# workarounds for Python 2 "narrow" builds with UCS2-only support.

		_narrow_unichr = unichr

		def unichr(i):
			"""
			Return the unicode character whose Unicode code is the integer 'i'.
			The valid range is 0 to 0x10FFFF inclusive.

			>>> _narrow_unichr(0xFFFF + 1)
			Traceback (most recent call last):
			  File "<stdin>", line 1, in ?
			ValueError: unichr() arg not in range(0x10000) (narrow Python build)
			>>> unichr(0xFFFF + 1) == u'\U00010000'
			True
			>>> unichr(1114111) == u'\U0010FFFF'
			True
			>>> unichr(0x10FFFF + 1)
			Traceback (most recent call last):
			  File "<stdin>", line 1, in ?
			ValueError: unichr() arg not in range(0x110000)
			"""
			try:
				return _narrow_unichr(i)
			except ValueError:
				try:
					padded_hex_str = hex(i)[2:].zfill(8)
					escape_str = "\\U" + padded_hex_str
					return escape_str.decode("unicode-escape")
				except UnicodeDecodeError:
					raise ValueError('unichr() arg not in range(0x110000)')

		import re
		_unicode_escape_RE = re.compile(r'\\U[A-Fa-f0-9]{8}')

		def byteord(c):
			"""
			Given a 8-bit or unicode character, return an integer representing the
			Unicode code point of the character. If a unicode argument is given, the
			character's code point must be in the range 0 to 0x10FFFF inclusive.

			>>> ord(u'\U00010000')
			Traceback (most recent call last):
			  File "<stdin>", line 1, in ?
			TypeError: ord() expected a character, but string of length 2 found
			>>> byteord(u'\U00010000') == 0xFFFF + 1
			True
			>>> byteord(u'\U0010FFFF') == 1114111
			True
			"""
			try:
				return ord(c)
			except TypeError as e:
				try:
					escape_str = c.encode('unicode-escape')
					if not _unicode_escape_RE.match(escape_str):
						raise
					hex_str = escape_str[3:]
					return int(hex_str, 16)
				except:
					raise TypeError(e)

	else:
		byteord = ord
	bytechr = chr

except NameError:
	unichr = chr
	def bytechr(n):
		return bytes([n])
	def byteord(c):
		return c if isinstance(c, int) else ord(c)


# the 'io' module provides the same I/O interface on both 2 and 3.
# here we define an alias of io.StringIO to disambiguate it eternally...
from io import BytesIO
from io import StringIO as UnicodeIO
try:
	# in python 2, by 'StringIO' we still mean a stream of *byte* strings
	from StringIO import StringIO
except ImportError:
	# in Python 3, we mean instead a stream of *unicode* strings
	StringIO = UnicodeIO


def strjoin(iterable, joiner=''):
	return tostr(joiner).join(iterable)

def tobytes(s, encoding='ascii', errors='strict'):
	if not isinstance(s, bytes):
		return s.encode(encoding, errors)
	else:
		return s
def tounicode(s, encoding='ascii', errors='strict'):
	if not isinstance(s, unicode):
		return s.decode(encoding, errors)
	else:
		return s

if str == bytes:
	class Tag(str):
		def tobytes(self):
			if isinstance(self, bytes):
				return self
			else:
				return self.encode('latin1')

	tostr = tobytes

	bytesjoin = strjoin
else:
	class Tag(str):

		@staticmethod
		def transcode(blob):
			if not isinstance(blob, str):
				blob = blob.decode('latin-1')
			return blob

		def __new__(self, content):
			return str.__new__(self, self.transcode(content))
		def __ne__(self, other):
			return not self.__eq__(other)
		def __eq__(self, other):
			return str.__eq__(self, self.transcode(other))

		def __hash__(self):
			return str.__hash__(self)

		def tobytes(self):
			return self.encode('latin-1')

	tostr = tounicode

	def bytesjoin(iterable, joiner=b''):
		return tobytes(joiner).join(tobytes(item) for item in iterable)


import io as _io

def open(file, mode='r', buffering=-1, encoding=None, errors=None,
		newline=None, closefd=True, opener=None):
	""" Alias of py3 built-in 'open' function, backported to py2 as 'io.open'.
	The 'opener' keyword argument is disabled for backward compatibility.
	"""
	if opener is not None:
		raise TypeError("'opener' keyword argument is not supported in py2")
	return _io.open(file, mode, buffering, encoding, errors, newline, closefd)


import os
try:
	from msvcrt import setmode as _setmode
except ImportError:
	_setmode = None  # only available on the Windows platform

def _set_binary_flag(fd):
	""" Copy file descriptor and set 'O_BINARY' mode to disable newlines
	translation ('\r\n' <=> '\n') on Windows.
	Return new file descriptor, and a boolean indicating whether it should
	be closed upon closing the file object (True if fd was copied).
	"""
	closefd = False
	if _setmode:
		fd = os.dup(fd)
		_setmode(fd, os.O_BINARY)
		closefd = True
	return fd, closefd


def open_stdin(mode='r', buffering=-1, encoding=None, errors=None, newline=None):
	""" Return a file object that wraps the standard input stream 'sys.stdin'.
	The arguments are the same as the built-in 'open' function.
	"""
	if not any(set(mode) == m for m in ({'r'}, {'r', 'b'}, {'r', 't'})):
		raise ValueError("invalid mode %r for stdin" % mode)
	sys.stdin.flush()
	fd, closefd = _set_binary_flag(sys.stdin.fileno())
	return open(fd, mode, buffering, encoding, errors, newline, closefd)


def open_stdout(mode='w', buffering=-1, encoding=None, errors=None, newline=None):
	""" Return a file object that wraps the standard output stream 'sys.stdout'.
	The arguments are the same as the built-in 'open' function.
	"""
	if not any(set(mode) == m for m in ({'w'}, {'w', 'b'}, {'w', 't'})):
		raise ValueError("invalid mode %r for stdout" % mode)
	sys.stdout.flush()
	fd, closefd = _set_binary_flag(sys.stdout.fileno())
	return open(fd, mode, buffering, encoding, errors, newline, closefd)


def open_stderr(mode='w', buffering=-1, encoding=None, errors=None, newline=None):
	""" Return a file object that wraps the standard error stream 'sys.stderr'.
	The arguments are the same as the built-in 'open' function.
	"""
	if not any(set(mode) == m for m in ({'w'}, {'w', 'b'}, {'w', 't'})):
		raise ValueError("invalid mode %r for stderr" % mode)
	sys.stderr.flush()
	fd, closefd = _set_binary_flag(sys.stderr.fileno())
	return open(fd, mode, buffering, encoding, errors, newline, closefd)


if __name__ == "__main__":
	import doctest, sys
	sys.exit(doctest.testmod().failed)
