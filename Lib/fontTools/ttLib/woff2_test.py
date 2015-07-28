from __future__ import print_function, division, absolute_import, unicode_literals
from fontTools.misc.py23 import *
from fontTools import ttLib
from .woff2 import (WOFF2Reader, woff2DirectorySize, woff2DirectoryFormat,
	woff2FlagsSize, woff2UnknownTagSize, woff2Base128MaxSize, WOFF2DirectoryEntry,
	getKnownTagIndex, packBase128, base128Size, woff2UnknownTagIndex,
	WOFF2FlavorData, woff2TransformedTableTags, WOFF2GlyfTable, WOFF2LocaTable,
	newTTFont)
import unittest
import sstruct
import os
import random

haveBrotli = False
try:
	import brotli
	haveBrotli = True
except ImportError:
	pass


current_dir = os.path.abspath(os.path.dirname(os.path.realpath(__file__)))
data_dir = os.path.join(current_dir, 'test_data')
TTX = os.path.join(data_dir, 'TestTTF-Regular.ttx')
OTX = os.path.join(data_dir, 'TestOTF-Regular.otx')
METADATA = os.path.join(data_dir, 'test_woff2_metadata.xml')

TT_WOFF2 = StringIO()
CFF_WOFF2 = StringIO()


def setUpModule():
	if not haveBrotli:
		raise unittest.SkipTest("No module named brotli")
	assert os.path.exists(TTX)
	assert os.path.exists(OTX)
	# import TT-flavoured test font and save it as WOFF2
	ttf = ttLib.TTFont(recalcBBoxes=False, recalcTimestamp=False)
	ttf.importXML(TTX, quiet=True)
	ttf.flavor = "woff2"
	ttf.save(TT_WOFF2, reorderTables=False)
	# import CFF-flavoured test font and save it as WOFF2
	otf = ttLib.TTFont(recalcBBoxes=False, recalcTimestamp=False)
	otf.importXML(OTX, quiet=True)
	otf.flavor = "woff2"
	otf.save(CFF_WOFF2, reorderTables=False)


class WOFF2ReaderTest(unittest.TestCase):

	@classmethod
	def setUpClass(cls):
		cls.file = StringIO(CFF_WOFF2.getvalue())
		cls.font = ttLib.TTFont(recalcBBoxes=False, recalcTimestamp=False)
		cls.font.importXML(OTX, quiet=True)

	def setUp(self):
		self.file.seek(0)

	def test_bad_signature(self):
		with self.assertRaisesRegexp(ttLib.TTLibError, 'bad signature'):
			WOFF2Reader(StringIO(b"wOFF"))

	def test_not_enough_data_header(self):
		incomplete_header = self.file.read(woff2DirectorySize - 1)
		with self.assertRaisesRegexp(ttLib.TTLibError, 'not enough data'):
			WOFF2Reader(StringIO(incomplete_header))

	def test_incorrect_compressed_size(self):
		data = self.file.read(woff2DirectorySize)
		header = sstruct.unpack(woff2DirectoryFormat, data)
		header['totalCompressedSize'] = 0
		data = sstruct.pack(woff2DirectoryFormat, header)
		with self.assertRaises(brotli.error):
			WOFF2Reader(StringIO(data + self.file.read()))

	def test_incorrect_uncompressed_size(self):
		decompress_backup = brotli.decompress
		brotli.decompress = lambda data: b""  # return empty byte string
		with self.assertRaisesRegexp(ttLib.TTLibError, 'unexpected size for decompressed'):
			WOFF2Reader(self.file)
		brotli.decompress = decompress_backup

	def test_incorrect_file_size(self):
		data = self.file.read(woff2DirectorySize)
		header = sstruct.unpack(woff2DirectoryFormat, data)
		header['length'] -= 1
		data = sstruct.pack(woff2DirectoryFormat, header)
		with self.assertRaisesRegexp(
				ttLib.TTLibError, "doesn't match the actual file size"):
			WOFF2Reader(StringIO(data + self.file.read()))

	def test_num_tables(self):
		tags = [t for t in self.font.keys() if t not in ('GlyphOrder', 'DSIG')]
		data = self.file.read(woff2DirectorySize)
		header = sstruct.unpack(woff2DirectoryFormat, data)
		self.assertEqual(header['numTables'], len(tags))

	def test_table_tags(self):
		tags = set([t for t in self.font.keys() if t not in ('GlyphOrder', 'DSIG')])
		reader = WOFF2Reader(self.file)
		self.assertEqual(set(reader.keys()), tags)

	def test_get_normal_tables(self):
		woff2Reader = WOFF2Reader(self.file)
		specialTags = woff2TransformedTableTags + ('head', 'GlyphOrder', 'DSIG')
		for tag in [t for t in self.font.keys() if t not in specialTags]:
			origData = self.font.getTableData(tag)
			decompressedData = woff2Reader[tag]
			self.assertEqual(origData, decompressedData)

	def test_reconstruct_unknown(self):
		reader = WOFF2Reader(self.file)
		with self.assertRaisesRegexp(ttLib.TTLibError, 'transform for table .* unknown'):
			reader.reconstructTable('ZZZZ')

	def test_head_transform_flag(self):
		headData = self.font.getTableData('head')
		origFlags = byteord(headData[16])
		reader = WOFF2Reader(self.file)
		modifiedFlags = byteord(reader['head'][16])
		self.assertNotEqual(origFlags, modifiedFlags)
		restoredFlags = modifiedFlags & ~0x08  # turn off bit 11
		self.assertEqual(origFlags, restoredFlags)


def get_normalised_data(font, tag, padding=4):
	assert tag in ('glyf', 'loca', 'head')
	assert {'glyf', 'loca', 'head'}.issubset(font.keys())
	glyfData = font.getTableData('glyf')
	origIndexFormat = font['head'].indexToLocFormat
	origLocations = font['loca'].locations[:]
	glyfTable = WOFF2GlyfTable()
	glyfTable.decompile(glyfData, font)
	if tag == 'glyf':
		data = glyfTable.compile(font, padding=padding)
	elif tag == 'loca':
		glyfTable.compile(font, padding=padding)
		data = font['loca'].compile(font)
	elif tag == 'head':
		glyfTable.compile(font, padding=padding)
		font['loca'].compile(font)
		data = font['head'].compile(font)
	font['loca'].set(origLocations)
	font['head'].indexToLocFormat = origIndexFormat
	return data


class WOFF2ReaderTTFTest(unittest.TestCase):
	""" Tests specific to TT-flavored fonts. """

	@classmethod
	def setUpClass(cls):
		cls.file = StringIO(TT_WOFF2.getvalue())
		cls.font = ttLib.TTFont(recalcBBoxes=False, recalcTimestamp=False)
		cls.font.importXML(TTX, quiet=True)

	def setUp(self):
		self.file.seek(0)

	def test_reconstruct_glyf(self):
		woff2Reader = WOFF2Reader(self.file)
		reconstructedData = woff2Reader['glyf']
		normGlyfData = get_normalised_data(self.font, 'glyf')
		self.assertEqual(normGlyfData, reconstructedData)

	def test_reconstruct_loca(self):
		woff2Reader = WOFF2Reader(self.file)
		reconstructedData = woff2Reader['loca']
		normLocaData = get_normalised_data(self.font, 'loca')
		self.assertEqual(normLocaData, reconstructedData)

	def test_transformed_loca_is_null(self):
		reader = WOFF2Reader(self.file)
		reader.tables['loca'].length = 1
		with self.assertRaisesRegexp(ttLib.TTLibError, "expected 0"):
			reader.reconstructTable('loca')

	def test_reconstruct_loca_match_orig_size(self):
		reader = WOFF2Reader(self.file)
		reader.tables['loca'].origLength -= 1
		with self.assertRaisesRegexp(
				ttLib.TTLibError, "'loca' table doesn't match original size"):
			reader.reconstructTable('loca')


class WOFF2DirectoryEntryTest(unittest.TestCase):

	def setUp(self):
		""" called multiple times, before every test method """
		self.entry = WOFF2DirectoryEntry()

	def test_not_enough_data_table_flags(self):
		with self.assertRaisesRegexp(ttLib.TTLibError, "can't read table 'flags'"):
			self.entry.fromString(b"")

	def test_not_enough_data_table_unknown_tag(self):
		incompleteData = bytearray([0x3F, 0, 0, 0])
		with self.assertRaisesRegexp(ttLib.TTLibError, "can't read table 'tag'"):
			self.entry.fromString(bytes(incompleteData))

	def test_table_reserved_flags(self):
		with self.assertRaisesRegexp(ttLib.TTLibError, "bits 6-7 are reserved"):
			self.entry.fromString(bytechr(0xC0))

	def test_loca_zero_transformLength(self):
		data = bytechr(getKnownTagIndex('loca'))  # flags
		data += packBase128(random.randint(1, 100))  # origLength
		data += packBase128(1)  # non-zero transformLength
		with self.assertRaisesRegexp(
				ttLib.TTLibError, 'transformLength .* loca .* must be 0'):
			self.entry.fromString(data)

	def test_fromFile(self):
		unknownTag = Tag('ZZZZ')
		data = bytechr(getKnownTagIndex(unknownTag))
		data += unknownTag.tobytes()
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


class DummyReader(WOFF2Reader):

	def __init__(self, file):
		self.file = file
		for attr in ('majorVersion', 'minorVersion', 'metaOffset', 'metaLength',
				'metaOrigLength', 'privLength', 'privOffset'):
			setattr(self, attr, 0)


class WOFF2FlavorDataTest(unittest.TestCase):

	@classmethod
	def setUpClass(cls):
		assert os.path.exists(METADATA)
		with open(METADATA, 'rb') as f:
			cls.xml_metadata = f.read()
		cls.compressed_metadata = brotli.compress(cls.xml_metadata, mode=brotli.MODE_TEXT)
		cls.fontdata = b'\0'*96  # 4-byte aligned
		cls.privData = bytes(bytearray(random.sample(range(32, 127), 20)))

	def setUp(self):
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
		reader.majorVersion = reader.minorVersion = 1
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
		font = ttLib.TTFont(recalcBBoxes=False, recalcTimestamp=False)
		font.importXML(TTX, quiet=True)
		cls.origGlyfData = font.getTableData('glyf')
		cls.origLocaData = font.getTableData('loca')
		cls.origHeadData = font.getTableData('head')
		cls.origMaxpData = font.getTableData('maxp')
		infile = StringIO(TT_WOFF2.getvalue())
		reader = WOFF2Reader(infile)
		cls.transformedGlyfData = reader.getTableData('glyf')

	def setUp(self):
		self.font = newTTFont(
			self.origHeadData,
			self.origMaxpData,
			self.origLocaData,
			self.origGlyfData)

	def test_reconstruct_glyf_padded(self):
		glyfTable = WOFF2GlyfTable()
		glyfTable.reconstruct(self.transformedGlyfData, self.font)
		data = glyfTable.compile(self.font, padding=4)
		normGlyfData = get_normalised_data(self.font, 'glyf')
		self.assertEqual(normGlyfData, data)

	def test_reconstruct_glyf_unpadded(self):
		glyfTable = WOFF2GlyfTable()
		glyfTable.reconstruct(self.transformedGlyfData, self.font)
		data = glyfTable.compile(self.font)
		self.assertEqual(self.origGlyfData, data)

	def test_reconstruct_glyf_incorrect_glyph_order(self):
		glyfTable = WOFF2GlyfTable()
		badGlyphOrder = self.font.getGlyphOrder()[:-1]
		self.font.setGlyphOrder(badGlyphOrder)
		with self.assertRaisesRegexp(ttLib.TTLibError, "incorrect glyphOrder"):
			glyfTable.reconstruct(self.transformedGlyfData, self.font)

	def test_reconstruct_glyf_no_glyphOrder(self):
		glyfTable = WOFF2GlyfTable()
		if hasattr(self.font, 'glyphOrder'):
			del self.font.glyphOrder
		numGlyphs = self.font['maxp'].numGlyphs
		del self.font['maxp']
		glyfTable.reconstruct(self.transformedGlyfData, self.font)
		expected = ["glyph%d" % i for i in range(numGlyphs)]
		self.assertEqual(expected, glyfTable.glyphOrder)

	def test_reconstruct_loca_padded(self):
		locaTable = self.font['loca'] = WOFF2LocaTable()
		glyfTable = self.font['glyf'] = WOFF2GlyfTable()
		glyfTable.reconstruct(self.transformedGlyfData, self.font)
		glyfTable.compile(self.font, padding=4)
		data = locaTable.compile(self.font)
		normLocaData = get_normalised_data(self.font, 'loca')
		self.assertEqual(normLocaData, data)

	def test_reconstruct_loca_unpadded(self):
		locaTable = self.font['loca'] = WOFF2LocaTable()
		glyfTable = self.font['glyf'] = WOFF2GlyfTable()
		glyfTable.reconstruct(self.transformedGlyfData, self.font)
		glyfTable.compile(self.font)
		data = locaTable.compile(self.font)
		self.assertEqual(self.origLocaData, data)

	def test_transform_glyf(self):
		glyfTable = self.font['glyf']
		data = glyfTable.transform(self.font)
		self.assertEqual(self.transformedGlyfData, data)

	def test_decode_glyf_header_not_enough_data(self):
		with self.assertRaisesRegexp(ttLib.TTLibError, "not enough 'glyf' data"):
			WOFF2GlyfTable().reconstruct(b"", self.font)

	def test_decode_glyf_table_incorrect_size(self):
		msg = "incorrect size of transformed 'glyf'"
		with self.assertRaisesRegexp(ttLib.TTLibError, msg):
			WOFF2GlyfTable().reconstruct(self.transformedGlyfData + b"\x00", self.font)
		with self.assertRaisesRegexp(ttLib.TTLibError, msg):
			WOFF2GlyfTable().reconstruct(self.transformedGlyfData[:-1], self.font)

	def test_reconstruct_and_transform_glyf(self):
		glyfTable = WOFF2GlyfTable()
		glyfTable.reconstruct(self.transformedGlyfData, self.font)
		data = glyfTable.transform(self.font)
		self.assertEqual(self.transformedGlyfData, data)

	def test_transform_and_reconstruct_glyf(self):
		glyfTable = self.font['glyf']
		transformedData = glyfTable.transform(self.font)
		newGlyfTable = WOFF2GlyfTable()
		newGlyfTable.reconstruct(transformedData, self.font)
		reconstructedData = newGlyfTable.compile(self.font, padding=4)
		normGlyfData = get_normalised_data(self.font, 'glyf')
		self.assertEqual(normGlyfData, reconstructedData)


if __name__ == "__main__":
	unittest.main()
