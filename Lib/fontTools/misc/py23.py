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



import os
try:
	from msvcrt import setmode as _setmode
except ImportError:
	_setmode = None
import io as _io


def open(file, mode='r', buffering=-1, encoding=None, errors=None,
		newline=None, closefd=True, opener=None):
	""" Alias of py3 built-in 'open' function, backported to py2 as 'io.open'.
	The 'opener' keyword argument is disabled for backward compatibility.
	"""
	if opener is not None:
		raise TypeError("'opener' keyword argument is not supported in py2")
	return _io.open(file, mode, buffering, encoding, errors, newline, closefd)


from contextlib import contextmanager as _contextmanager

@_contextmanager
def _open_stdio(name, binary=False, buffering=-1, encoding=None, errors=None,
		newline=None):
	if name not in ('stdin', 'stdout', 'stderr'):
		raise ValueError('invalid standard I/O stream: %s' % name)
	if name == 'stdin':
		mode = 'rb' if binary else 'r'
	else:
		mode = 'wb' if binary else 'w'
	newline_flag = None
	stream = getattr(sys, name)
	fd = stream.fileno()
	stream.flush()
	if _setmode:
		# disable newlines translation ('\r\n' <=> '\n') on win32
		newline_flag = _setmode(fd, os.O_BINARY)
	try:
		with open(fd, mode, buffering, encoding, errors, newline,
				closefd=False) as new_stream:
			yield new_stream
	finally:
		if newline_flag:
			# restore original newline translation mode
			_setmode(fd, newline_flag)


def open_stdin(mode='r', buffering=-1, encoding=None, errors=None, newline=None):
	"""Context manager yielding a file-like object that wraps around the
	standard input stream 'sys.stdin'. When the caller returns, the object is
	closed and standard stream is restored to its original state.

	Keyword Arguments:
 		- mode -- A string indicating how the stream is to be opened, similar
 			to the builtin open() function. Accepts either 'r'/'rt' or 'rb'.
 		- buffering -- The file's desired buffer size. Accepts the same values as
			the builtin open() function.
		- encoding -- The file's encoding. Accepts the same values as the
			builtin open() function. It only applies to text mode.
		- errors -- A string indicating how encoding and decoding errors are to
			be handled. Accepts the same value as the builtin open() function.
			It only applies to text mode.
		- newline -- A string controlling how universal newline mode works.
			Accepts the same value as the builtin open() function. It only
			applies to text mode.
	"""
	valid_modes = ({'r'}, {'r', 'b'}, {'r', 't'})
	if not (1 <= len(mode) <= 2 and any(v == set(mode) for v in valid_modes)):
		raise ValueError("invalid mode %r for stdin" % mode)
	binary = 'b' in mode
	return _open_stdio('stdin', binary, buffering, encoding, errors, newline)


def open_stdout(mode='w', buffering=-1, encoding=None, errors=None, newline=None):
	"""Context manager yielding a file-like object that wraps around the
	standard output stream 'sys.stdout'. When the caller returns, the object is
	closed and standard stream is restored to its original state.

	Keyword Arguments:
 		- mode -- A string indicating how the stream is to be opened, similar
 			to the builtin open() function. Accepts either 'w'/'wt' or 'wb'.
 		- buffering -- The file's desired buffer size. Accepts the same values as
			the builtin open() function.
		- encoding -- The file's encoding. Accepts the same values as the
			builtin open() function. It only applies to text mode.
		- errors -- A string indicating how encoding and decoding errors are to
			be handled. Accepts the same value as the builtin open() function.
			It only applies to text mode.
		- newline -- A string controlling how universal newline mode works.
			Accepts the same value as the builtin open() function. It only
			applies to text mode.
	"""
	valid_modes = ({'w'}, {'w', 'b'}, {'w', 't'})
	if not (1 <= len(mode) <= 2 and any(v == set(mode) for v in valid_modes)):
		raise ValueError("invalid mode %r for stdout" % mode)
	binary = 'b' in mode
	return _open_stdio('stdout', binary, buffering, encoding, errors, newline)


def open_stderr(mode='w', buffering=-1, encoding=None, errors=None, newline=None):
	"""Context manager yielding a file-like object that wraps around the
	standard error stream 'sys.stderr'. When the caller returns, the object is
	closed and standard stream is restored to its original state.

	Keyword Arguments:
 		- mode -- A string indicating how the stream is to be opened, similar
 			to the builtin open() function. Accepts either 'w'/'wt' or 'wb'.
 		- buffering -- The file's desired buffer size. Accepts the same values as
			the builtin open() function.
		- encoding -- The file's encoding. Accepts the same values as the
			builtin open() function. It only applies to text mode.
		- errors -- A string indicating how encoding and decoding errors are to
			be handled. Accepts the same value as the builtin open() function.
			It only applies to text mode.
		- newline -- A string controlling how universal newline mode works.
			Accepts the same value as the builtin open() function. It only
			applies to text mode.
	"""
	valid_modes = ({'w'}, {'w', 'b'}, {'w', 't'})
	if not (1 <= len(mode) <= 2 and any(v == set(mode) for v in valid_modes)):
		raise ValueError("invalid mode %r for stderr" % mode)
	binary = 'b' in mode
	return _open_stdio('stderr', binary, buffering, encoding, errors, newline)


if __name__ == "__main__":
	import doctest, sys
	sys.exit(doctest.testmod().failed)
