from __future__ import print_function, division, absolute_import, unicode_literals
from fontTools.misc.py23 import *
from fontTools.ttLib import TTFont, TTLibError
from fontTools.ttLib.woff2 import (WOFF2Reader, woff2DirectorySize, woff2DirectoryFormat,
	woff2FlagsSize, woff2UnknownTagSize, woff2Base128MaxSize)
import unittest
import sstruct


test_font = 'data/Lobster.ttx'


def setUpModule():
	""" called once, before anything else in this module """
	pass


def tearDownModule():
	""" called once, before anything else in this module """
	pass


class WOFF2ReaderTest(unittest.TestCase):

	@classmethod
	def setUpClass(cls):
		""" called once, before any tests """
		cls.ttFont = TTFont(None, recalcBBoxes=False, recalcTimestamp=False)
		cls.ttFont.importXML(test_font, quiet=True)
		cls.ttFont.flavor = "woff2"
		cls.file = StringIO()
		cls.ttFont.save(cls.file, reorderTables=False)

	@classmethod
	def tearDownClass(cls):
		""" called once, after all tests, if setUpClass successful """
		pass

	def setUp(self):
		""" called multiple times, before every test method """
		self.file.seek(0)

	def tearDown(self):
		""" called multiple times, after every test method """

	def test_bad_signature(self):
		with self.assertRaises(TTLibError):
			WOFF2Reader(StringIO(b"wOFF"))

	def test_not_enough_data_header(self):
		incomplete_header = self.file.read(woff2DirectorySize - 1)
		with self.assertRaises(TTLibError):
			WOFF2Reader(StringIO(incomplete_header))

	def test_num_tables(self):
		tags = list(self.ttFont.keys())
		if "GlyphOrder" in tags:
			tags.remove("GlyphOrder")
		data = self.file.read(woff2DirectorySize)
		header = sstruct.unpack(woff2DirectoryFormat, data)
		self.assertEqual(header['numTables'], len(tags))

	def test_not_enough_data_table_flags(self):
		incomplete_flags = self.file.read(woff2DirectorySize)
		with self.assertRaises(TTLibError):
			WOFF2Reader(StringIO(incomplete_flags))

	def test_not_enough_data_table_unknown_tag(self):
		flags_offset = woff2DirectorySize
		buf = bytearray(
			self.file.read(
				flags_offset + woff2FlagsSize + woff2UnknownTagSize))
		buf[flags_offset] = 0x3F
		incomplete_buf = buf[:-1]
		with self.assertRaises(TTLibError):
			WOFF2Reader(StringIO(incomplete_buf))

	def test_table_reserved_flags(self):
		buf = bytearray(
			self.file.read(woff2DirectorySize + woff2FlagsSize))
		buf[-1] |= 0xC0
		with self.assertRaises(TTLibError):
			WOFF2Reader(StringIO(buf))

	def test_not_enough_data_origLength(self):
		flags_offset = woff2DirectorySize
		self.file.seek(flags_offset)
		flags = byteord(self.file.read(woff2FlagsSize))
		origLength_offset = flags_offset + woff2FlagsSize
		if flags & 0x3F == 0x3F:
			origLength_offset += woff2UnknownTagSize
		self.file.seek(0)
		buf = bytearray(self.file.read(origLength_offset))
		with self.assertRaises(TTLibError):
			WOFF2Reader(StringIO(buf))



class WOFF2WriterTest(unittest.TestCase):

	@classmethod
	def setUpClass(cls):
		""" called once, before any tests """
		pass

	@classmethod
	def tearDownClass(cls):
		""" called once, after all tests, if setUpClass successful """
		pass

	def setUp(self):
		""" called multiple times, before every test method """
		pass

	def tearDown(self):
		""" called multiple times, after every test method """


class WOFF2DirectoryEntryTest(unittest.TestCase):

	@classmethod
	def setUpClass(cls):
		""" called once, before any tests """
		pass

	@classmethod
	def tearDownClass(cls):
		""" called once, after all tests, if setUpClass successful """
		pass

	def setUp(self):
		""" called multiple times, before every test method """
		pass

	def tearDown(self):
		""" called multiple times, after every test method """


class WOFF2GlyfTableTest(unittest.TestCase):

	@classmethod
	def setUpClass(cls):
		""" called once, before any tests """
		pass

	@classmethod
	def tearDownClass(cls):
		""" called once, after all tests, if setUpClass successful """
		pass

	def setUp(self):
		""" called multiple times, before every test method """
		pass

	def tearDown(self):
		""" called multiple times, after every test method """


class WOFF2FlavorDataTest(unittest.TestCase):

	@classmethod
	def setUpClass(cls):
		""" called once, before any tests """
		pass

	@classmethod
	def tearDownClass(cls):
		""" called once, after all tests, if setUpClass successful """
		pass

	def setUp(self):
		""" called multiple times, before every test method """
		pass

	def tearDown(self):
		""" called multiple times, after every test method """


if __name__ == "__main__":
	unittest.main()
