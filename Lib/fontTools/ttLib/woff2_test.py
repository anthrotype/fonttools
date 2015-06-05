from __future__ import print_function, division, absolute_import, unicode_literals
from fontTools.misc.py23 import *
from fontTools.ttLib import TTFont, TTLibError
from .woff2 import (WOFF2Reader, woff2DirectorySize, woff2DirectoryFormat,
	woff2FlagsSize, woff2UnknownTagSize, woff2Base128MaxSize, WOFF2DirectoryEntry,
	getKnownTagIndex, packBase128, base128Size, woff2UnknownTagIndex,
	WOFF2FlavorData)
import unittest
import sstruct
import sys
import os

haveBrotli = False
try:
	import brotli
	haveBrotli = True
except ImportError:
	pass


dirname = os.path.abspath(os.path.dirname(os.path.realpath(__file__)))
ttxname = os.path.join(dirname, 'test_data', 'TestTTF-Regular.ttx')
otxname = os.path.join(dirname, 'test_data', 'TestOTF-Regular.otx')
ttf = TTFont(None, recalcBBoxes=False, recalcTimestamp=False)
otf = TTFont(None, recalcBBoxes=False, recalcTimestamp=False)
tt_woff2_file = StringIO()
ot_woff2_file = StringIO()


def setUpModule():
	if not haveBrotli:
		raise unittest.SkipTest("No module named brotli")
	assert os.path.exists(ttxname)
	assert os.path.exists(otxname)
	# import TT-flavoured test font and save it to woff2
	ttf.importXML(ttxname, quiet=True)
	ttf.flavor = "woff2"
	ttf.save(tt_woff2_file, reorderTables=False)
	# import CFF-flavoured test font and save it to woff2
	otf.importXML(otxname, quiet=True)
	otf.flavor = "woff2"
	otf.save(ot_woff2_file, reorderTables=False)


class BasicTestCase(unittest.TestCase):

	def setUp(self):
		# called multiple times, before every test method
		self.file.seek(0)


class TT_TestCase(BasicTestCase):

	@classmethod
	def setUpClass(cls):
		# called once, before any tests
		cls.file = StringIO(tt_woff2_file.getvalue())
		cls.font = ttf


class CFF_TestCase(BasicTestCase):

	@classmethod
	def setUpClass(cls):
		# called once, before any tests
		cls.file = StringIO(ot_woff2_file.getvalue())
		cls.font = otf


class WOFF2ReaderTest_TTF(TT_TestCase):
	""" Tests specific to TT-flavored fonts. """

	def test_num_tables(self):
		tags = [t for t in self.font.keys() if t != "GlyphOrder"]
		data = self.file.read(woff2DirectorySize)
		header = sstruct.unpack(woff2DirectoryFormat, data)
		self.assertEqual(header['numTables'], len(tags))

	def test_table_tags(self):
		tags = set([t for t in self.font.keys() if t != "GlyphOrder"])
		reader = WOFF2Reader(self.file)
		self.assertEqual(set(reader.keys()), tags)


class WOFF2ReaderTest_OTF(CFF_TestCase, WOFF2ReaderTest_TTF):
	""" Tests specific to CFF-flavored fonts. """
	pass


class WOFF2ReaderTest_Any(TT_TestCase):
	""" Generic tests not specific to TT- or CFF-flavored fonts. """

	def test_bad_signature(self):
		with self.assertRaises(TTLibError):
			WOFF2Reader(StringIO(b"wOFF"))

	def test_not_enough_data_header(self):
		incomplete_header = self.file.read(woff2DirectorySize - 1)
		with self.assertRaises(TTLibError):
			WOFF2Reader(StringIO(incomplete_header))

	def test_bad_total_compressed_size(self):
		data = self.file.read(woff2DirectorySize)
		header = sstruct.unpack(woff2DirectoryFormat, data)
		header['totalCompressedSize'] = 0
		data = sstruct.pack(woff2DirectoryFormat, header)
		with self.assertRaises(brotli.error):
			WOFF2Reader(StringIO(data + self.file.read()))

	def test_no_match_actual_length(self):
		data = self.file.read(woff2DirectorySize)
		header = sstruct.unpack(woff2DirectoryFormat, data)
		header['length'] -= 1
		data = sstruct.pack(woff2DirectoryFormat, header)
		with self.assertRaises(TTLibError):
			WOFF2Reader(StringIO(data + self.file.read()))


class WOFF2DirectoryEntryTest(unittest.TestCase):

	def setUp(self):
		""" called multiple times, before every test method """
		self.entry = WOFF2DirectoryEntry()

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

	def test_fromFile(self):
		unknown_tag = b'ZZZZ'
		data = bytechr(getKnownTagIndex(unknown_tag))
		data += unknown_tag
		data += packBase128(12345)
		expected_pos = len(data)
		f = StringIO(data + b'\0'*100)
		self.entry.fromFile(f)
		self.assertEqual(f.tell(), expected_pos)

	def test_transformed_toString(self):
		self.entry.tag = Tag('glyf')
		self.entry.flags = getKnownTagIndex(self.entry.tag)
		self.entry.origLength = 123456
		self.entry.length = 12345
		expected_size = (woff2FlagsSize + base128Size(self.entry.origLength) +
			base128Size(self.entry.length))
		data = self.entry.toString()
		self.assertEqual(len(data), expected_size)

	def test_known_toString(self):
		self.entry.tag = Tag('head')
		self.entry.flags = getKnownTagIndex(self.entry.tag)
		self.entry.origLength = 54
		expected_size = (woff2FlagsSize + base128Size(self.entry.origLength))
		data = self.entry.toString()
		self.assertEqual(len(data), expected_size)

	def test_unknown_toString(self):
		self.entry.tag = Tag('ZZZZ')
		self.entry.flags = woff2UnknownTagIndex
		self.entry.origLength = 123456
		expected_size = (woff2FlagsSize + woff2UnknownTagSize +
			base128Size(self.entry.origLength))
		data = self.entry.toString()
		self.assertEqual(len(data), expected_size)


class DummyReader(object):

	def __init__(self, file):
		self.file = file
		for attr in ('majorVersion', 'minorVersion', 'metaOffset', 'metaLength',
				'metaOrigLength', 'privLength', 'privOffset'):
			setattr(self, attr, 0)


class WOFF2FlavorDataTest(unittest.TestCase):

	@classmethod
	def setUpClass(cls):
		""" called once, before any tests """
		xml_filename = os.path.join(dirname, 'test_data', 'test_woff2_metadata.xml')
		assert os.path.exists(xml_filename)
		with open(xml_filename, 'rb') as f:
			cls.xml_metadata = f.read()
		cls.compressed_metadata = brotli.compress(cls.xml_metadata, mode=brotli.MODE_TEXT)
		cls.fontdata = b'\0'*96  # 4-byte aligned

	def test_get_metaData_no_privData(self):
		infile = StringIO(self.fontdata + self.compressed_metadata)
		reader = DummyReader(infile)
		reader.metaOffset = len(self.fontdata)
		reader.metaLength = len(self.compressed_metadata)
		reader.metaOrigLength = len(self.xml_metadata)
		flavorData = WOFF2FlavorData(reader)
		self.assertEqual(self.xml_metadata, flavorData.metaData)

	@classmethod
	def tearDownClass(cls):
		""" called once, after all tests, if setUpClass successful """
		pass

	def setUp(self):
		""" called multiple times, before every test method """
		pass

	def tearDown(self):
		""" called multiple times, after every test method """


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


if __name__ == "__main__":
	unittest.main()
