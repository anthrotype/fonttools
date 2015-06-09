from __future__ import print_function, division, absolute_import, unicode_literals
from fontTools.misc.py23 import *
from fontTools.ttLib import TTFont, TTLibError
from .woff2 import (WOFF2Reader, woff2DirectorySize, woff2DirectoryFormat,
	woff2FlagsSize, woff2UnknownTagSize, woff2Base128MaxSize, WOFF2DirectoryEntry,
	getKnownTagIndex, packBase128, base128Size, woff2UnknownTagIndex,
	WOFF2FlavorData, woff2TransformedTableTags)
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


dirName = os.path.abspath(os.path.dirname(os.path.realpath(__file__)))
ttxName = os.path.join(dirName, 'test_data', 'TestTTF-Regular.ttx')
otxName = os.path.join(dirName, 'test_data', 'TestOTF-Regular.otx')
metaDataName = os.path.join(dirName, 'test_data', 'test_woff2_metadata.xml')
ttWoff2File = StringIO()
cffWoff2File = StringIO()


def setUpModule():
	if not haveBrotli:
		raise unittest.SkipTest("No module named brotli")
	assert os.path.exists(ttxName)
	assert os.path.exists(otxName)
	# import TT-flavoured test font and save it to woff2
	ttf = TTFont(None, recalcBBoxes=False, recalcTimestamp=False)
	ttf.importXML(ttxName, quiet=True)
	ttf.flavor = "woff2"
	ttf.save(ttWoff2File, reorderTables=False)
	# import CFF-flavoured test font and save it to woff2
	otf = TTFont(None, recalcBBoxes=False, recalcTimestamp=False)
	otf.importXML(otxName, quiet=True)
	otf.flavor = "woff2"
	otf.save(cffWoff2File, reorderTables=False)


class BaseReaderTest(unittest.TestCase):

	@classmethod
	def setUpClass(cls):
		# called once, before any tests
		cls.file = StringIO(cffWoff2File.getvalue())
		cls.font = TTFont(cls.file, recalcBBoxes=False, recalcTimestamp=False)

	def setUp(self):
		# called multiple times, before every test method
		self.file.seek(0)


class WOFF2ReaderTest(BaseReaderTest):
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

	def test_num_tables(self):
		tags = [t for t in self.font.keys() if t != "GlyphOrder"]
		data = self.file.read(woff2DirectorySize)
		header = sstruct.unpack(woff2DirectoryFormat, data)
		self.assertEqual(header['numTables'], len(tags))

	def test_table_tags(self):
		tags = set([t for t in self.font.keys() if t != "GlyphOrder"])
		reader = WOFF2Reader(self.file)
		self.assertEqual(set(reader.keys()), tags)

	def test_get_normal_tables_data(self):
		woff2Reader = WOFF2Reader(self.file)
		for tag in self.font.reader.keys():
			if tag in woff2TransformedTableTags:
				# these need specific tests
				continue
			self.assertEqual(self.font.reader[tag], woff2Reader[tag])


class WOFF2ReaderTTFTest(BaseReaderTest):
	""" Tests specific to TT-flavored fonts. """

	@classmethod
	def setUpClass(cls):
		# called once, before any tests
		cls.file = StringIO(ttWoff2File.getvalue())
		cls.font = TTFont(cls.file, recalcBBoxes=False, recalcTimestamp=False)

	def test_get_reconstructed_glyf_data(self):
		origGlyfData = self.font.reader['glyf']
		reader = WOFF2Reader(self.file)
		reconstructedGlyfData = reader['glyf']
		self.assertEqual(origGlyfData, reconstructedGlyfData)


class WOFF2DirectoryEntryTest(unittest.TestCase):

	def setUp(self):
		""" called multiple times, before every test method """
		self.entry = WOFF2DirectoryEntry()

	def test_not_enough_data_table_flags(self):
		with self.assertRaises(TTLibError):
			self.entry.fromString(b"")

	def test_not_enough_data_table_unknown_tag(self):
		incompleteBuf = bytearray([0x3F, 0, 0, 0])
		with self.assertRaises(TTLibError):
			self.entry.fromString(bytes(incompleteBuf))

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
		unknownTag = b'ZZZZ'
		data = bytechr(getKnownTagIndex(unknownTag))
		data += unknownTag
		data += packBase128(12345)
		expectedPos = len(data)
		f = StringIO(data + b'\0'*100)
		self.entry.fromFile(f)
		self.assertEqual(f.tell(), expectedPos)

	def test_transformed_toString(self):
		self.entry.tag = Tag('glyf')
		self.entry.flags = getKnownTagIndex(self.entry.tag)
		self.entry.origLength = 123456
		self.entry.length = 12345
		expectedSize = (woff2FlagsSize + base128Size(self.entry.origLength) +
			base128Size(self.entry.length))
		data = self.entry.toString()
		self.assertEqual(len(data), expectedSize)

	def test_known_toString(self):
		self.entry.tag = Tag('head')
		self.entry.flags = getKnownTagIndex(self.entry.tag)
		self.entry.origLength = 54
		expectedSize = (woff2FlagsSize + base128Size(self.entry.origLength))
		data = self.entry.toString()
		self.assertEqual(len(data), expectedSize)

	def test_unknown_toString(self):
		self.entry.tag = Tag('ZZZZ')
		self.entry.flags = woff2UnknownTagIndex
		self.entry.origLength = 123456
		expectedSize = (woff2FlagsSize + woff2UnknownTagSize +
			base128Size(self.entry.origLength))
		data = self.entry.toString()
		self.assertEqual(len(data), expectedSize)


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
		assert os.path.exists(metaDataName)
		with open(metaDataName, 'rb') as f:
			cls.xml_metadata = f.read()
		cls.compressed_metadata = brotli.compress(cls.xml_metadata, mode=brotli.MODE_TEXT)
		cls.fontdata = b'\0'*96  # 4-byte aligned
		cls.privData = bytes(bytearray([i for i in range(32, 127)]))

	def setUp(self):
		""" called multiple times, before every test method """
		self.file = StringIO(self.fontdata)
		self.file.seek(0, 2)

	def test_get_metaData_no_privData(self):
		self.file.write(self.compressed_metadata)
		reader = DummyReader(self.file)
		reader.metaOffset = len(self.fontdata)
		reader.metaLength = len(self.compressed_metadata)
		reader.metaOrigLength = len(self.xml_metadata)
		flavorData = WOFF2FlavorData(reader)
		self.assertEqual(self.xml_metadata, flavorData.metaData)

	def test_get_privData_no_metaData(self):
		self.file.write(self.privData)
		reader = DummyReader(self.file)
		reader.privOffset = len(self.fontdata)
		reader.privLength = len(self.privData)
		flavorData = WOFF2FlavorData(reader)
		self.assertEqual(self.privData, flavorData.privData)

	def test_get_metaData_and_privData(self):
		self.file.write(self.compressed_metadata + self.privData)
		reader = DummyReader(self.file)
		reader.metaOffset = len(self.fontdata)
		reader.metaLength = len(self.compressed_metadata)
		reader.metaOrigLength = len(self.xml_metadata)
		reader.privOffset = reader.metaOffset + reader.metaLength
		reader.privLength = len(self.privData)
		flavorData = WOFF2FlavorData(reader)
		self.assertEqual(self.xml_metadata, flavorData.metaData)
		self.assertEqual(self.privData, flavorData.privData)

	def test_get_major_minorVersion(self):
		reader = DummyReader(self.file)
		reader.majorVersion = 1
		reader.minorVersion = 1
		flavorData = WOFF2FlavorData(reader)
		self.assertEqual(flavorData.majorVersion, 1)
		self.assertEqual(flavorData.minorVersion, 1)


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
