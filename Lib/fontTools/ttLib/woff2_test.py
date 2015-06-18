from __future__ import print_function, division, absolute_import, unicode_literals
from fontTools.misc.py23 import *
from fontTools.ttLib import TTFont, TTLibError
from .woff2 import (WOFF2Reader, woff2DirectorySize, woff2DirectoryFormat,
	woff2FlagsSize, woff2UnknownTagSize, woff2Base128MaxSize, WOFF2DirectoryEntry,
	getKnownTagIndex, packBase128, base128Size, woff2UnknownTagIndex,
	WOFF2FlavorData, woff2TransformedTableTags, WOFF2GlyfTable, WOFF2LocaTable)
if sys.version_info < (2, 7):
	import unittest2 as unittest
else:
	import unittest
import struct
import sstruct
import os

haveBrotli = False
try:
	import brotli
	haveBrotli = True
except ImportError:
	pass


DIR = os.path.abspath(os.path.dirname(os.path.realpath(__file__)))
TTX = os.path.join(DIR, 'test_data', 'TestTTF-Regular.ttx')
OTX = os.path.join(DIR, 'test_data', 'TestOTF-Regular.otx')
METADATA = os.path.join(DIR, 'test_data', 'test_woff2_metadata.xml')
TT_WOFF2 = StringIO()
CFF_WOFF2 = StringIO()


def setUpModule():
	if not haveBrotli:
		raise unittest.SkipTest("No module named brotli")
	assert os.path.exists(TTX)
	assert os.path.exists(OTX)
	# import TT-flavoured test font and save it to woff2
	ttf = TTFont(None, recalcBBoxes=False, recalcTimestamp=False)
	ttf.importXML(TTX, quiet=True)
	ttf.flavor = "woff2"
	ttf.save(TT_WOFF2, reorderTables=False)
	# import CFF-flavoured test font and save it to woff2
	otf = TTFont(None, recalcBBoxes=False, recalcTimestamp=False)
	otf.importXML(OTX, quiet=True)
	otf.flavor = "woff2"
	otf.save(CFF_WOFF2, reorderTables=False)


class WOFF2ReaderTest(unittest.TestCase):

	@classmethod
	def setUpClass(cls):
		cls.file = StringIO(CFF_WOFF2.getvalue())
		cls.font = TTFont(None, recalcBBoxes=False, recalcTimestamp=False)
		cls.font.importXML(OTX, quiet=True)

	def setUp(self):
		self.file.seek(0)

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

	def test_get_normal_tables(self):
		woff2Reader = WOFF2Reader(self.file)
		for tag in [t for t in self.font.keys() if t not in
				woff2TransformedTableTags + ('head', 'GlyphOrder')]:
			# transformed tables need specific tests
			origData = self.font.getTableData(tag)
			self.assertEqual(origData, woff2Reader[tag])

	def test_reconstruct_unknown(self):
		reader = WOFF2Reader(self.file)
		with self.assertRaises(TTLibError):
			reader.reconstructTable('ZZZZ', '')


class WOFF2ReaderTTFTest(unittest.TestCase):
	""" Tests specific to TT-flavored fonts. """

	@classmethod
	def setUpClass(cls):
		cls.file = StringIO(TT_WOFF2.getvalue())
		cls.font = TTFont(None, recalcBBoxes=False, recalcTimestamp=False)
		cls.font.importXML(TTX, quiet=True)

	def setUp(self):
		self.file.seek(0)

	def reconstruct_table(self, tag):
		reader = WOFF2Reader(self.file)
		entry = reader.tables[tag]
		transformedData = entry.loadData(reader.transformBuffer)
		reconstructedData = reader.reconstructTable(tag, transformedData)
		return reconstructedData

	def test_reconstruct_glyf(self):
		origData = self.font.getTableData('glyf')
		reconstructedData = self.reconstruct_table('glyf')
		self.assertEqual(origData, reconstructedData)

	def test_reconstruct_loca(self):
		origData = self.font.getTableData('loca')
		reconstructedData = self.reconstruct_table('loca')
		self.assertEqual(origData, reconstructedData)

	def test_transformed_loca_is_null(self):
		reader = WOFF2Reader(self.file)
		with self.assertRaises(TTLibError):
			reader.reconstructTable('loca', b'\x00')

	def test_head_transform_flag(self):
		origData = self.font.getTableData('head')
		origData = origData[:8] + b'\0\0\0\0' + origData[12:]
		origFlags = byteord(origData[16])
		reader = WOFF2Reader(self.file)
		modifiedData = reader['head']
		modifiedData = modifiedData[:8] + b'\0\0\0\0' + modifiedData[12:]
		modifiedFlags = byteord(modifiedData[16])
		self.assertNotEqual(origFlags, modifiedFlags)
		restoredData = bytearray(modifiedData)
		restoredData[16] = restoredData[16] & ~0x08
		self.assertEqual(origData, bytes(restoredData))


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
		assert os.path.exists(METADATA)
		with open(METADATA, 'rb') as f:
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
		cls.font = TTFont(None, recalcBBoxes=False, recalcTimestamp=False)
		cls.font.importXML(TTX, quiet=True)
		cls.origGlyfData = cls.font.getTableData('glyf')
		cls.origLocaData = cls.font.getTableData('loca')
		cls.origIndexFormat = cls.font['head'].indexToLocFormat
		infile = StringIO(TT_WOFF2.getvalue())
		reader = WOFF2Reader(infile)
		glyfEntry = reader.tables['glyf']
		cls.transformedGlyfData = glyfEntry.loadData(reader.transformBuffer)

	def test_reconstruct_transformed_glyf(self):
		glyfTable = WOFF2GlyfTable()
		glyfTable.reconstruct(self.transformedGlyfData)
		self.assertEqual(self.origGlyfData, glyfTable.compile())

	def test_reconstruct_transformed_loca(self):
		glyfTable = WOFF2GlyfTable()
		glyfTable.reconstruct(self.transformedGlyfData)
		locaTable = WOFF2LocaTable()
		locaTable.reconstruct(glyfTable)
		self.assertEqual(self.origLocaData, locaTable.compile())

	def test_decode_glyf_header_not_enough_data(self):
		with self.assertRaises(TTLibError):
			WOFF2GlyfTable().reconstruct("")

	def test_decode_glyf_table_incorrect_size(self):
		with self.assertRaises(TTLibError):
			WOFF2GlyfTable().reconstruct(self.transformedGlyfData + b"\x00")
		with self.assertRaises(TTLibError):
			WOFF2GlyfTable().reconstruct(self.transformedGlyfData[:-1])

	def test_glyf_reconstruct_and_transform(self):
		glyfTable = WOFF2GlyfTable()
		glyfTable.reconstruct(self.transformedGlyfData)
		transformedGlyfData = glyfTable.transform(glyfTable.indexFormat)
		self.assertEqual(self.transformedGlyfData, transformedGlyfData)

	def test_glyf_transform_and_reconstruct(self):
		numGlyphs, = struct.unpack('>H', self.transformedGlyfData[4:6])
		indexFormat = byteord(self.transformedGlyfData[7])
		glyfTable = WOFF2GlyfTable()
		glyfTable.decompile(self.origGlyfData, self.origLocaData, indexFormat, numGlyphs)
		transformedGlyfData = glyfTable.transform(indexFormat)
		newGlyfTable = WOFF2GlyfTable()
		newGlyfTable.reconstruct(transformedGlyfData)
		self.assertEqual(self.origGlyfData, newGlyfTable.compile())

	def test_glyf_decompile_and_transform(self):
		numGlyphs, = struct.unpack('>H', self.transformedGlyfData[4:6])
		indexFormat = byteord(self.transformedGlyfData[7])
		glyfTable = WOFF2GlyfTable()
		glyfTable.decompile(self.origGlyfData, self.origLocaData, indexFormat, numGlyphs)
		transformedGlyfData = glyfTable.transform(indexFormat)
		self.assertEqual(self.transformedGlyfData, transformedGlyfData)


if __name__ == "__main__":
	unittest.main()
