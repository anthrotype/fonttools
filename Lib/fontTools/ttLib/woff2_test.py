from __future__ import print_function, division, absolute_import, unicode_literals
from fontTools.misc.py23 import *
from fontTools import ttLib
from .woff2 import (WOFF2Reader, woff2DirectorySize, woff2DirectoryFormat,
	woff2FlagsSize, woff2UnknownTagSize, woff2Base128MaxSize, WOFF2DirectoryEntry,
	getKnownTagIndex, packBase128, base128Size, woff2UnknownTagIndex,
	WOFF2FlavorData, woff2TransformedTableTags, WOFF2GlyfTable, WOFF2LocaTable,
	WOFF2Writer, padData)
import unittest
import sstruct
import os
import random
import copy

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


def normalise_table(font, tag, padding=4):
	""" Return normalised table data. Keep 'font' instance unmodified. """
	assert tag in ('glyf', 'loca', 'head')
	assert tag in font
	if tag == 'head':
		origHeadFlags = font['head'].flags
		font['head'].flags |= (1 << 11)
		tableData = font['head'].compile(font)
	if font.sfntVersion in ("\x00\x01\x00\x00", "true"):
		assert {'glyf', 'loca', 'head'}.issubset(font.keys())
		origIndexFormat = font['head'].indexToLocFormat
		if hasattr(font['loca'], 'locations'):
			origLocations = font['loca'].locations[:]
		else:
			origLocations = []
		glyfTable = WOFF2GlyfTable()
		glyfTable.decompile(font.getTableData('glyf'), font)
		if tag == 'glyf':
			tableData = glyfTable.compile(font, padding=padding)
		elif tag == 'loca':
			glyfTable.compile(font, padding=padding)
			tableData = font['loca'].compile(font)
		if tag == 'head':
			glyfTable.compile(font, padding=padding)
			font['loca'].compile(font)
			tableData = font['head'].compile(font)
		font['head'].indexToLocFormat = origIndexFormat
		font['loca'].set(origLocations)
	if tag == 'head':
		font['head'].flags = origHeadFlags
	return tableData


def normalise_font(font):
	""" Return normalised font data. Keep 'font' instance unmodified. """
	# drop DSIG but keep a copy
	DSIG_copy = copy.deepcopy(font['DSIG'])
	del font['DSIG']
	# ovverride TTFont attributes
	origFlavor = font.flavor
	origRecalcBBoxes = font.recalcBBoxes
	origRecalcTimestamp = font.recalcTimestamp
	origLazy = font.lazy
	font.flavor = None
	font.recalcBBoxes = False
	font.recalcTimestamp = False
	font.lazy = True
	# save font to temporary stream
	infile = StringIO()
	font.save(infile)
	infile.seek(0)
	# reorder tables alphabetically
	outfile = StringIO()
	reader = ttLib.sfnt.SFNTReader(infile)
	writer = ttLib.sfnt.SFNTWriter(
		outfile, len(reader.tables), reader.sfntVersion, reader.flavor, reader.flavorData)
	for tag in sorted(reader.keys()):
		if tag in woff2TransformedTableTags + ('head',):
			writer[tag] = normalise_table(font, tag)
		else:
			writer[tag] = reader[tag]
	writer.close()
	# restore font attributes
	font['DSIG'] = DSIG_copy
	font.flavor = origFlavor
	font.recalcBBoxes = origRecalcBBoxes
	font.recalcTimestamp = origRecalcTimestamp
	font.lazy = origLazy
	return outfile.getvalue()


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
		normGlyfData = normalise_table(self.font, 'glyf')
		self.assertEqual(normGlyfData, reconstructedData)

	def test_reconstruct_loca(self):
		woff2Reader = WOFF2Reader(self.file)
		reconstructedData = woff2Reader['loca']
		normLocaData = normalise_table(self.font, 'loca')
		self.assertEqual(normLocaData, reconstructedData)

	def test_reconstruct_loca_match_orig_size(self):
		reader = WOFF2Reader(self.file)
		reader.tables['loca'].origLength -= 1
		with self.assertRaisesRegexp(
				ttLib.TTLibError, "'loca' table doesn't match original size"):
			reader.reconstructTable('loca')


class WOFF2DirectoryEntryTest(unittest.TestCase):

	def setUp(self):
		self.entry = WOFF2DirectoryEntry()

	def test_not_enough_data_table_flags(self):
		with self.assertRaisesRegexp(ttLib.TTLibError, "can't read table 'flags'"):
			self.entry.fromString(b"")

	def test_not_enough_data_table_tag(self):
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
				ttLib.TTLibError, "transformLength of the 'loca' table must be 0"):
			self.entry.fromString(data)

	def test_fromFile(self):
		unknownTag = Tag('ZZZZ')
		data = bytechr(getKnownTagIndex(unknownTag))
		data += unknownTag.tobytes()
		data += packBase128(random.randint(1, 100))
		expectedPos = len(data)
		f = StringIO(data + b'\0'*100)
		self.entry.fromFile(f)
		self.assertEqual(f.tell(), expectedPos)

	def test_transformed_toString(self):
		self.entry.tag = Tag('glyf')
		self.entry.flags = getKnownTagIndex(self.entry.tag)
		self.entry.origLength = random.randint(101, 200)
		self.entry.length = random.randint(1, 100)
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
		self.entry.origLength = random.randint(1, 100)
		expectedSize = (woff2FlagsSize + woff2UnknownTagSize +
			base128Size(self.entry.origLength))
		data = self.entry.toString()
		self.assertEqual(len(data), expectedSize)


class DummyReader(WOFF2Reader):

	def __init__(self, file, checkChecksums=1, fontNumber=-1):
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
		# make random byte strings; font data must be 4-byte aligned
		cls.fontdata = bytes(bytearray(random.sample(range(0, 256), 80)))
		cls.privData = bytes(bytearray(random.sample(range(0, 256), 20)))

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
		cls.font = ttLib.TTFont(recalcBBoxes=False, recalcTimestamp=False, flavor="woff2")
		cls.font.importXML(OTX, quiet=True)
		cls.tags = [t for t in cls.font.keys() if t != 'GlyphOrder']
		cls.numTables = len(cls.tags)
		cls.file = StringIO(CFF_WOFF2.getvalue())
		cls.file.seek(0, 2)
		cls.length = (cls.file.tell() + 3) & ~3
		cls.setUpFlavorData()

	@classmethod
	def setUpFlavorData(cls):
		assert os.path.exists(METADATA)
		with open(METADATA, 'rb') as f:
			cls.xml_metadata = f.read()
		cls.compressed_metadata = brotli.compress(cls.xml_metadata, mode=brotli.MODE_TEXT)
		cls.privData = bytes(bytearray(random.sample(range(0, 256), 20)))

	def setUp(self):
		self.file.seek(0)
		self.writer = WOFF2Writer(StringIO(), self.numTables, self.font.sfntVersion)

	def test_DSIG_dropped(self):
		self.writer['DSIG'] = b"\0"
		self.assertEqual(len(self.writer.tables), 0)
		self.assertEqual(self.writer.numTables, self.numTables-1)

	def test_no_rewrite_table(self):
		self.writer['ZZZZ'] = b"\0"
		with self.assertRaisesRegexp(ttLib.TTLibError, "cannot rewrite"):
			self.writer['ZZZZ'] = b"\0"

	def test_num_tables(self):
		self.writer['ABCD'] = b"\0"
		with self.assertRaisesRegexp(ttLib.TTLibError, "wrong number of tables"):
			self.writer.close()

	def test_required_tables(self):
		font = ttLib.TTFont(flavor="woff2")
		with self.assertRaisesRegexp(ttLib.TTLibError, "missing required table"):
			font.save(StringIO())

	def test_head_transform_flag(self):
		headData = self.font.getTableData('head')
		origFlags = byteord(headData[16])
		woff2font = ttLib.TTFont(self.file)
		newHeadData = woff2font.getTableData('head')
		modifiedFlags = byteord(newHeadData[16])
		self.assertNotEqual(origFlags, modifiedFlags)
		restoredFlags = modifiedFlags & ~0x08  # turn off bit 11
		self.assertEqual(origFlags, restoredFlags)

	def test_tables_sorted_alphabetically(self):
		expected = sorted([t for t in self.tags if t != 'DSIG'])
		woff2font = ttLib.TTFont(self.file)
		self.assertEqual(expected, woff2font.reader.tableOrder)

	def test_checksums(self):
		normFile = StringIO(normalise_font(self.font))
		normFile.seek(0)
		normFont = ttLib.TTFont(normFile, checkChecksums=2)
		w2font = ttLib.TTFont(self.file)
		for tag in [t for t in self.tags if t != 'DSIG']:
			if tag == "head":
				data = w2font.reader[tag]
				data = data[:8] + b'\0\0\0\0' + data[12:]
				w2CheckSum = ttLib.sfnt.calcChecksum(data)
				normCheckSum = ttLib.sfnt.calcChecksum(data)
			else:
				w2CheckSum = ttLib.sfnt.calcChecksum(w2font.reader[tag])
				normCheckSum = ttLib.sfnt.calcChecksum(normFont.reader[tag])
			self.assertEqual(w2CheckSum, normCheckSum)
		normCheckSumAdjustment = normFont['head'].checkSumAdjustment
		self.assertEqual(normCheckSumAdjustment, w2font['head'].checkSumAdjustment)

	def test_calcSFNTChecksumsLengthsAndOffsets(self):
		normFont = ttLib.TTFont(StringIO(normalise_font(self.font)))
		for tag in self.tags:
			self.writer[tag] = self.font.getTableData(tag)
		self.writer._normaliseGlyfAndLoca()
		self.writer._setHeadTransformFlag()
		self.writer.tableOrder.sort()
		self.writer._calcSFNTChecksumsLengthsAndOffsets()
		for tag, entry in normFont.reader.tables.items():
			self.assertEqual(entry.offset, self.writer.tables[tag].origOffset)
			self.assertEqual(entry.length, self.writer.tables[tag].origLength)
			self.assertEqual(entry.checkSum, self.writer.tables[tag].checkSum)

	def test_bad_sfntVersion(self):
		for i in range(self.numTables):
			self.writer[bytechr(65 + i)*4] = b"\0"
		self.writer.sfntVersion = 'ZZZZ'
		with self.assertRaisesRegexp(ttLib.TTLibError, "bad sfntVersion"):
			self.writer.close()

	def test_calcTotalSize_no_flavorData(self):
		expected = self.length
		self.writer.file = StringIO()
		for tag in self.tags:
			self.writer[tag] = self.font.getTableData(tag)
		self.writer.close()
		self.assertEqual(expected, self.writer.length)
		self.assertEqual(expected, self.writer.file.tell())

	def test_calcTotalSize_metaData(self):
		expected = self.length + len(self.compressed_metadata)
		flavorData = self.writer.flavorData = WOFF2FlavorData()
		flavorData.metaData = self.xml_metadata
		self.writer.file = StringIO()
		for tag in self.tags:
			self.writer[tag] = self.font.getTableData(tag)
		self.writer.close()
		self.assertEqual(expected, self.writer.length)
		self.assertEqual(expected, self.writer.file.tell())

	def test_calcTotalSize_privData(self):
		expected = self.length + len(self.privData)
		flavorData = self.writer.flavorData = WOFF2FlavorData()
		flavorData.privData = self.privData
		self.writer.file = StringIO()
		for tag in self.tags:
			self.writer[tag] = self.font.getTableData(tag)
		self.writer.close()
		self.assertEqual(expected, self.writer.length)
		self.assertEqual(expected, self.writer.file.tell())

	def test_calcTotalSize_metaData_and_privData(self):
		metaDataLength = (len(self.compressed_metadata) + 3) & ~3
		expected = self.length + metaDataLength + len(self.privData)
		flavorData = self.writer.flavorData = WOFF2FlavorData()
		flavorData.metaData = self.xml_metadata
		flavorData.privData = self.privData
		self.writer.file = StringIO()
		for tag in self.tags:
			self.writer[tag] = self.font.getTableData(tag)
		self.writer.close()
		self.assertEqual(expected, self.writer.length)
		self.assertEqual(expected, self.writer.file.tell())

	def test_getVersion(self):
		self.assertEqual((0, 0), self.writer._getVersion())

		fontRevision = self.font['head'].fontRevision
		versionTuple = tuple(int(i) for i in str(fontRevision).split("."))
		entry = self.writer.tables['head'] = ttLib.getTableClass('head')()
		entry.data = self.font.getTableData('head')
		self.assertEqual(versionTuple, self.writer._getVersion())

		flavorData = self.writer.flavorData = WOFF2FlavorData()
		flavorData.majorVersion, flavorData.minorVersion = (10, 11)
		self.assertEqual((10, 11), self.writer._getVersion())


class WOFF2WriterTTFTest(WOFF2WriterTest):

	@classmethod
	def setUpClass(cls):
		cls.font = ttLib.TTFont(recalcBBoxes=False, recalcTimestamp=False, flavor="woff2")
		cls.font.importXML(TTX, quiet=True)
		cls.tags = [t for t in cls.font.keys() if t != 'GlyphOrder']
		cls.numTables = len(cls.tags)
		cls.file = StringIO(TT_WOFF2.getvalue())
		cls.file.seek(0, 2)
		cls.length = (cls.file.tell() + 3) & ~3
		cls.setUpFlavorData()

	def test_normaliseGlyfAndLoca(self):
		normTables = {}
		for tag in ('head', 'loca', 'glyf'):
			normTables[tag] = normalise_table(self.font, tag)
		for tag in self.tags:
			tableData = self.font.getTableData(tag)
			self.writer[tag] = tableData
			if tag in normTables:
				self.assertNotEqual(tableData, normTables[tag])
		self.writer._normaliseGlyfAndLoca()
		self.writer._setHeadTransformFlag()
		for tag in normTables:
			self.assertEqual(self.writer.tables[tag].data, normTables[tag])


class WOFF2GlyfTableTest(unittest.TestCase):

	@classmethod
	def setUpClass(cls):
		font = ttLib.TTFont(recalcBBoxes=False, recalcTimestamp=False)
		font.importXML(TTX, quiet=True)
		cls.tables = {}
		cls.transformedTags = ('maxp', 'head', 'loca', 'glyf')
		for tag in reversed(cls.transformedTags):
			cls.tables[tag] = font.getTableData(tag)
		cls.glyphOrder = ["glyph%d" % i for i in range(font['maxp'].numGlyphs)]
		infile = StringIO(TT_WOFF2.getvalue())
		reader = WOFF2Reader(infile)
		cls.transformedGlyfData = reader.tables['glyf'].loadData(
			reader.transformBuffer)

	def setUp(self):
		self.font = font = ttLib.TTFont(
			recalcBBoxes=False, recalcTimestamp=False)
		font['head'] = ttLib.getTableClass('head')()
		font['maxp'] = ttLib.getTableClass('maxp')()
		font['loca'] = WOFF2LocaTable()
		font['glyf'] = WOFF2GlyfTable()
		font.setGlyphOrder(self.glyphOrder)
		for tag in self.transformedTags:
			font[tag].decompile(self.tables[tag], font)

	def tearDown(self):
		del self.font

	def test_reconstruct_glyf_padded(self):
		glyfTable = WOFF2GlyfTable()
		glyfTable.reconstruct(self.transformedGlyfData, self.font)
		data = glyfTable.compile(self.font, padding=4)
		normGlyfData = normalise_table(self.font, 'glyf')
		self.assertEqual(normGlyfData, data)

	def test_reconstruct_glyf_unpadded(self):
		glyfTable = WOFF2GlyfTable()
		glyfTable.reconstruct(self.transformedGlyfData, self.font)
		data = glyfTable.compile(self.font, padding=None)
		self.assertEqual(self.tables['glyf'], data)

	def test_reconstruct_glyf_incorrect_glyphOrder(self):
		glyfTable = WOFF2GlyfTable()
		badGlyphOrder = self.font.getGlyphOrder()[:-1]
		self.font.setGlyphOrder(badGlyphOrder)
		with self.assertRaisesRegexp(ttLib.TTLibError, "incorrect glyphOrder"):
			glyfTable.reconstruct(self.transformedGlyfData, self.font)

	def test_reconstruct_glyf_missing_glyphOrder(self):
		glyfTable = WOFF2GlyfTable()
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
		normLocaData = normalise_table(self.font, 'loca')
		self.assertEqual(normLocaData, data)

	def test_reconstruct_loca_unpadded(self):
		locaTable = self.font['loca'] = WOFF2LocaTable()
		glyfTable = self.font['glyf'] = WOFF2GlyfTable()
		glyfTable.reconstruct(self.transformedGlyfData, self.font)
		glyfTable.compile(self.font, padding=None)
		data = locaTable.compile(self.font)
		self.assertEqual(self.tables['loca'], data)

	def test_reconstruct_glyf_header_not_enough_data(self):
		with self.assertRaisesRegexp(ttLib.TTLibError, "not enough 'glyf' data"):
			WOFF2GlyfTable().reconstruct(b"", self.font)

	def test_reconstruct_glyf_table_incorrect_size(self):
		msg = "incorrect size of transformed 'glyf'"
		with self.assertRaisesRegexp(ttLib.TTLibError, msg):
			WOFF2GlyfTable().reconstruct(self.transformedGlyfData + b"\x00", self.font)
		with self.assertRaisesRegexp(ttLib.TTLibError, msg):
			WOFF2GlyfTable().reconstruct(self.transformedGlyfData[:-1], self.font)

	def test_transform_glyf(self):
		glyfTable = self.font['glyf']
		data = glyfTable.transform(self.font)
		self.assertEqual(self.transformedGlyfData, data)

	def test_transform_glyf_incorrect_glyphOrder(self):
		glyfTable = self.font['glyf']
		badGlyphOrder = self.font.getGlyphOrder()[:-1]
		del glyfTable.glyphOrder
		self.font.setGlyphOrder(badGlyphOrder)
		with self.assertRaisesRegexp(ttLib.TTLibError, "incorrect glyphOrder"):
			glyfTable.transform(self.font)
		glyfTable.glyphOrder = badGlyphOrder
		with self.assertRaisesRegexp(ttLib.TTLibError, "incorrect glyphOrder"):
			glyfTable.transform(self.font)

	def test_transform_glyf_missing_glyphOrder(self):
		glyfTable = self.font['glyf']
		del glyfTable.glyphOrder
		del self.font.glyphOrder
		numGlyphs = self.font['maxp'].numGlyphs
		del self.font['maxp']
		glyfTable.transform(self.font)
		expected = ["glyph%d" % i for i in range(numGlyphs)]
		self.assertEqual(expected, glyfTable.glyphOrder)

	def test_roundtrip_glyf_1(self):
		glyfTable = WOFF2GlyfTable()
		glyfTable.reconstruct(self.transformedGlyfData, self.font)
		data = glyfTable.transform(self.font)
		self.assertEqual(self.transformedGlyfData, data)

	def test_roundtrip_glyf_2(self):
		glyfTable = self.font['glyf']
		transformedData = glyfTable.transform(self.font)
		newGlyfTable = WOFF2GlyfTable()
		newGlyfTable.reconstruct(transformedData, self.font)
		reconstructedData = newGlyfTable.compile(self.font, padding=4)
		normGlyfData = normalise_table(self.font, 'glyf')
		self.assertEqual(normGlyfData, reconstructedData)


if __name__ == "__main__":
	unittest.main()
