from __future__ import print_function, division, absolute_import, unicode_literals
from fontTools.misc.py23 import *
from fontTools.ttLib import TTFont, TTLibError
from fontTools.ttLib.woff2 import (WOFF2Reader, woff2DirectorySize, woff2DirectoryFormat,
	woff2FlagsSize, woff2UnknownTagSize, woff2Base128MaxSize, WOFF2DirectoryEntry,
	getKnownTagIndex, packBase128, base128Size)
import unittest
import sstruct


ttxfile = 'data/Lobster.ttx'
testfont = TTFont(None, recalcBBoxes=False, recalcTimestamp=False)
woff2file = StringIO()


def setUpModule():
	""" called once, before anything else in this module """
	testfont.importXML(ttxfile, quiet=True)
	testfont.flavor = "woff2"
	testfont.save(woff2file, reorderTables=False)


def tearDownModule():
	""" called once, before anything else in this module """
	pass


class WOFF2ReaderTest(unittest.TestCase):

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
		woff2file.seek(0)

	def tearDown(self):
		""" called multiple times, after every test method """

	def test_bad_signature(self):
		with self.assertRaises(TTLibError):
			WOFF2Reader(StringIO(b"wOFF"))

	def test_not_enough_data_header(self):
		incomplete_header = woff2file.read(woff2DirectorySize - 1)
		with self.assertRaises(TTLibError):
			WOFF2Reader(StringIO(incomplete_header))

	def test_num_tables(self):
		tags = list(testfont.keys())
		if "GlyphOrder" in tags:
			tags.remove("GlyphOrder")
		data = woff2file.read(woff2DirectorySize)
		header = sstruct.unpack(woff2DirectoryFormat, data)
		self.assertEqual(header['numTables'], len(tags))



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
		self.entry = WOFF2DirectoryEntry()

	def tearDown(self):
		""" called multiple times, after every test method """

	def test_not_enough_data_table_flags(self):
		with self.assertRaises(TTLibError):
			self.entry.fromString(b"")

	def test_not_enough_data_table_unknown_tag(self):
		incomplete_buf = bytearray([0x3F, 0, 0, 0])
		with self.assertRaises(TTLibError):
			self.entry.fromString(bytes(incomplete_buf))

	def test_table_reserved_flags(self):
		with self.assertRaises(TTLibError):
			self.entry.fromString(bytechr(0xC0))

	def test_loca_zero_transformLength(self):
		data = bytechr(getKnownTagIndex(b'loca'))
		data += packBase128(127)
		data += packBase128(1)
		with self.assertRaises(TTLibError):
			self.entry.fromString(data)

	def test_read_fromFile(self):
		unknown_tag = b'ABCD'
		data = bytechr(getKnownTagIndex(unknown_tag))
		data += unknown_tag
		data += packBase128(12345)
		expected_pos = len(data)
		f = StringIO(data + b'\0'*100)
		self.entry.fromFile(f)
		self.assertEqual(f.tell(), expected_pos)


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
