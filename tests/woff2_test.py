from __future__ import print_function, division, absolute_import, unicode_literals
from fontTools.misc.py23 import *
from fontTools.ttLib import TTFont, TTLibError
from fontTools.ttLib import woff2
import unittest
import sstruct
from io import BytesIO


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
		cls.file = BytesIO()
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
			woff2.WOFF2Reader(BytesIO(b"wOFF"))

	def test_not_enough_data_header(self):
		incomplete_header = self.file.read(woff2.woff2DirectorySize - 1)
		with self.assertRaises(TTLibError):
			woff2.WOFF2Reader(BytesIO(incomplete_header))

	def test_num_tables(self):
		tags = list(self.ttFont.keys())
		if "GlyphOrder" in tags:
			tags.remove("GlyphOrder")
		data = self.file.read(woff2.woff2DirectorySize)
		header = sstruct.unpack(woff2.woff2DirectoryFormat, data)
		self.assertEqual(header['numTables'], len(tags))

	def test_not_enough_data_table_flags(self):
		incomplete_flags = self.file.read(woff2.woff2DirectorySize)
		with self.assertRaises(TTLibError):
			woff2.WOFF2Reader(BytesIO(incomplete_flags))

	def test_not_enough_data_table_unknown_tag(self):
		flags_offset = woff2.woff2DirectorySize
		buf = bytearray(
			flags_offset + woff2.woff2FlagsSize + woff2.woff2UnknownTagSize)
		self.file.readinto(buf)
		buf[flags_offset] = 0x3F
		incomplete_buf = buf[:-1]
		with self.assertRaises(TTLibError):
			woff2.WOFF2Reader(BytesIO(incomplete_buf))

	def test_table_reserved_flags(self):
		buf = bytearray(woff2.woff2DirectorySize + woff2.woff2FlagsSize)
		self.file.readinto(buf)
		buf[-1] |= 0xC0
		with self.assertRaises(TTLibError):
			woff2.WOFF2Reader(BytesIO(buf))


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
