from __future__ import print_function, division, absolute_import
from fontTools.misc.py23 import *
from fontTools.misc import sstruct
import struct
import sys
import array
import brotli
from fontTools.ttLib import TTFont, TTLibError, getTableModule, getTableClass, getSearchRange
from fontTools.ttLib.sfnt import SFNTReader, SFNTWriter, DirectoryEntry, WOFFFlavorData, sfntDirectoryFormat, sfntDirectorySize, SFNTDirectoryEntry, sfntDirectoryEntrySize, calcChecksum
from fontTools.ttLib.tables import ttProgram


class WOFF2Reader(SFNTReader):

	flavor = "woff2"

	def __init__(self, file):
		self.file = file

		sfntVersion = self.file.read(4)
		if sfntVersion != b"wOF2":
			raise TTLibError("Not a WOFF2 font (bad signature)")

		self.file.seek(0)
		self.DirectoryEntry = WOFF2DirectoryEntry
		sstruct.unpack(woff2DirectoryFormat, self.file.read(woff2DirectorySize), self)

		self.tables = {}
		# WOFF2 doesn't store offsets to individual tables. These can be calculated
		# by summing up the tables' lengths in the order in which the tables have
		# been encoded, and without further padding between tables.
		offset = 0
		for i in range(self.numTables):
			entry = self.DirectoryEntry()
			entry.fromFile(self.file)
			tag = Tag(entry.tag)
			self.tables[tag] = entry
			entry.offset = offset
			offset += entry.length

		# WOFF2 font data is compressed in a single stream comprising all tables
		# so it must be decompressed once as a whole
		totalUncompressedSize = offset
		compressedData = self.file.read(self.totalCompressedSize)
		decompressedData = brotli.decompress(compressedData)
		if len(decompressedData) != totalUncompressedSize:
			raise TTLibError(
				'unexpected size for decompressed font data: expected %d, found %d'
				% (totalUncompressedSize, len(decompressedData)))
		self.transformBuffer = StringIO(decompressedData)
		self.glyfDecoder = WOFF2Glyf()

		# Load flavor data if any
		self.flavorData = WOFFFlavorData(self)

	def __getitem__(self, tag):
		entry = self.tables[Tag(tag)]
		rawData = entry.loadData(self.transformBuffer)
		if tag not in woff2TransformedTableTags:
			return rawData

		if hasattr(entry, 'data'):
			# table already reconstructed, return compiled data
			return entry.data

		if tag == 'glyf':
			# reconstruct both glyf and loca tables
			data = self.glyfDecoder.decodeData(rawData)
		elif tag == 'loca':
			# transformed loca is reconstructed as part of the glyf decoding process
			# and its length must always be 0
			assert len(rawData) == 0, "expected 0, received %d bytes" % len(rawData)
			if not self.glyfDecoder.locaData:
				# make sure glyf is loaded first
				self['glyf']
			# get loca data from reconstructed glyf
			data = self.glyfDecoder.locaData

		if len(data) != entry.origLength:
			raise TTLibError(
				"reconstructed '%s' table doesn't match original size: expected %d, found %d"
				% (tag, entry.origLength, len(data)))
		entry.data = data
		return data


class WOFF2Writer(SFNTWriter):

	flavor = "woff2"

	def __init__(self, file, numTables, sfntVersion="\000\001\000\000",
			     flavorData=None):
		self.file = file
		self.numTables = numTables
		self.sfntVersion = Tag(sfntVersion)
		self.flavorData = flavorData

		self.directoryFormat = woff2DirectoryFormat
		self.directorySize = woff2DirectorySize
		self.DirectoryEntry = WOFF2DirectoryEntry

		self.signature = "wOF2"

		# calculate SFNT offsets for checksum calculation purposes
		self.origNextTableOffset = sfntDirectorySize + numTables * sfntDirectoryEntrySize

		# make temporary buffer for storing raw or transformed table data before compression
		self.transformBuffer = StringIO()
		self.nextTableOffset = 0
		self.glyfEncoder = WOFF2Glyf()

		self.tables = {}
		self.tableOrder = []

	def __setitem__(self, tag, data):
		""" WOFF2 raw table data are written to disk only at the end, after all tags
		have been defined.
		"""
		if tag in self.tables:
			raise TTLibError("cannot rewrite '%s' table: length does not match directory entry" % tag)

		entry = self.DirectoryEntry()
		entry.tag = Tag(tag)

		if tag == 'head':
			entry.checkSum = calcChecksum(data[:8] + b'\0\0\0\0' + data[12:])
			self.headTable = data
		else:
			entry.checkSum = calcChecksum(data)

		entry.origOffset = self.origNextTableOffset

		entry.flags = 0x3F
		for i in range(len(woff2KnownTags)):
			if entry.tag == woff2KnownTags[i]:
				entry.flags = i
		entry.origLength = len(data)
		entry.data = data

		# get head's indexToLocFormat and maxp's numGlyphs for glyf transform
		if tag == 'head':
			self.glyfEncoder.indexFormat, = struct.unpack(">H", data[50:52])
		elif tag == 'maxp':
			self.glyfEncoder.numGlyphs, = struct.unpack(">H", data[4:6])
		elif tag == 'loca':
			self.glyfEncoder.locaData = data

		self.origNextTableOffset += (entry.origLength + 3) & ~3

		self.tables[tag] = entry
		self.tableOrder.append(tag)

	def close(self):
		""" All tags must have been defined. Now write the table data and directory.
		"""
		if 0:
			# According to WOFF2 specs, the directory must reflect the 'physical order'
			# in which the tables have been encoded.
			tables = sorted(self.tables.items(), key=lambda x: self.tableOrder.index(x[0]))
		else:
			# However, for compatibility with current woff2 implementations (e.g. OTS),
			# we must sort both the directory and table data in ascending order by tag.
			# See https://github.com/google/woff2/pull/3
			tables = sorted(self.tables.items())
			# we also need to 'normalise' the original table offsets used for checksum
			# calculation
			offset = sfntDirectorySize + sfntDirectoryEntrySize * len(tables)
			for tag, entry in tables:
				entry.origOffset = offset
				offset = offset + ((entry.origLength + 3) & ~3)

		if len(tables) != self.numTables:
			raise TTLibError("wrong number of tables; expected %d, found %d" % (self.numTables, len(tables)))

		self.reserved = 0

		# size of uncompressed font
		self.totalSfntSize = sfntDirectorySize
		self.totalSfntSize += sfntDirectoryEntrySize * len(tables)
		for tag, entry in tables:
			self.totalSfntSize += (entry.origLength + 3) & ~3

		self.signature = b"wOF2"

		for tag, entry in tables:
			data = entry.data
			if tag == "loca":
				data = b""
			elif tag == "glyf":
				data = self.glyfEncoder.encodeData(data)
			entry.offset = self.nextTableOffset
			entry.saveData(self.transformBuffer, data)
			self.nextTableOffset += entry.length

		# start calculating total size of WOFF2 font
		offset = woff2DirectorySize
		for tag, entry in tables:
			offset += len(entry.toString())

		# update head's checkSumAdjustment
		self.writeMasterChecksum(b"")

		# compress font data
		self.transformBuffer.seek(0)
		uncompressedData = self.transformBuffer.read()
		import brotli
		compressedData = brotli.compress(uncompressedData, brotli.MODE_FONT)
		self.totalCompressedSize = len(compressedData)

		offset += self.totalCompressedSize
		offset = (offset + 3) & ~3

		# calculate offsets and lengths for any metadata and/or private data
		compressedMetaData = privData = b""
		data = self.flavorData if self.flavorData else WOFFFlavorData()
		if data.majorVersion is not None and data.minorVersion is not None:
			self.majorVersion = data.majorVersion
			self.minorVersion = data.minorVersion
		else:
			if hasattr(self, 'headTable'):
				self.majorVersion, self.minorVersion = struct.unpack(">HH", self.headTable[4:8])
			else:
				self.majorVersion = self.minorVersion = 0
		if data.metaData:
			self.metaOrigLength = len(data.metaData)
			self.metaOffset = offset
			# compress metadata using brotli
			compressedMetaData = brotli.compress(data.metaData)
			self.metaLength = len(compressedMetaData)
			offset += self.metaLength
		else:
			self.metaOffset = self.metaLength = self.metaOrigLength = 0
		if data.privData:
			privData = data.privData
			# make sure private data is padded to 4-byte boundary
			offset = (offset + 3) & ~3
			self.privOffset = offset
			self.privLength = len(privData)
			offset += self.privLength
		else:
			self.privOffset = self.privLength = 0

		# total size of WOFF/WOFF2 font, including any metadata or private data
		self.length = offset

		directory = sstruct.pack(self.directoryFormat, self)

		self.file.seek(self.directorySize)
		for tag, entry in tables:
			directory = directory + entry.toString()
		self.file.seek(0)
		self.file.write(directory)

		# finally write WOFF2 compressed font data to disk
		self.file.write(compressedData)
		write4BytePadding(self.file)

		# write any WOFF/WOFF2 metadata and/or private data
		if compressedMetaData:
			self.file.seek(self.metaOffset)
			assert self.file.tell() == self.metaOffset
			self.file.write(compressedMetaData)
			if privData:
				write4BytePadding(self.file)
		if privData:
			self.file.seek(self.privOffset)
			assert self.file.tell() == self.privOffset
			self.file.write(privData)

	def _calcMasterChecksum(self, directory):
		# calculate checkSumAdjustment
		tags = list(self.tables.keys())
		checksums = []
		for i in range(len(tags)):
			checksums.append(self.tables[tags[i]].checkSum)

		# Create a SFNT directory for checksum calculation purposes
		self.searchRange, self.entrySelector, self.rangeShift = getSearchRange(self.numTables, 16)
		directory = sstruct.pack(sfntDirectoryFormat, self)
		tables = sorted(self.tables.items())
		for tag, entry in tables:
			sfntEntry = SFNTDirectoryEntry()
			sfntEntry.tag = entry.tag
			sfntEntry.checkSum = entry.checkSum
			sfntEntry.offset = entry.origOffset
			sfntEntry.length = entry.origLength
			directory = directory + sfntEntry.toString()

		directory_end = sfntDirectorySize + len(self.tables) * sfntDirectoryEntrySize
		assert directory_end == len(directory)

		checksums.append(calcChecksum(directory))
		checksum = sum(checksums) & 0xffffffff
		# BiboAfba!
		checksumadjustment = (0xB1B0AFBA - checksum) & 0xffffffff
		return checksumadjustment

	def writeMasterChecksum(self, directory):
		checksumadjustment = self._calcMasterChecksum(directory)
		# write the checksum to the file
		self.transformBuffer.seek(self.tables['head'].offset + 8)
		self.transformBuffer.write(struct.pack(">L", checksumadjustment))

# -- woff2 directory helpers and cruft

woff2DirectoryFormat = """
		> # big endian
		signature:           4s   # "wOF2"
		sfntVersion:         4s
		length:              L    # total woff2 file size
		numTables:           H    # number of tables
		reserved:            H    # set to 0
		totalSfntSize:       L    # uncompressed size
		totalCompressedSize: L    # compressed size
		majorVersion:        H    # major version of WOFF file
		minorVersion:        H    # minor version of WOFF file
		metaOffset:          L    # offset to metadata block
		metaLength:          L    # length of compressed metadata
		metaOrigLength:      L    # length of uncompressed metadata
		privOffset:          L    # offset to private data block
		privLength:          L    # length of private data block
"""

woff2DirectorySize = sstruct.calcsize(woff2DirectoryFormat)

woff2KnownTags = (
	"cmap", "head", "hhea", "hmtx", "maxp", "name", "OS/2", "post", "cvt ",
	"fpgm", "glyf", "loca", "prep", "CFF ", "VORG", "EBDT", "EBLC", "gasp",
	"hdmx", "kern", "LTSH", "PCLT", "VDMX", "vhea", "vmtx", "BASE", "GDEF",
	"GPOS", "GSUB", "EBSC", "JSTF", "MATH", "CBDT", "CBLC", "COLR", "CPAL",
	"SVG ", "sbix", "acnt", "avar", "bdat", "bloc", "bsln", "cvar", "fdsc",
	"feat", "fmtx", "fvar", "gvar", "hsty", "just", "lcar", "mort", "morx",
	"opbd", "prop", "trak", "Zapf", "Silf", "Glat", "Gloc", "Feat", "Sill")

woff2FlagsFormat = """
		> # big endian
		flags: B  # table type and flags
"""

woff2FlagsSize = sstruct.calcsize(woff2FlagsFormat)

woff2UnknownTagFormat = """
		> # big endian
		tag: 4s  # 4-byte tag (optional)
"""

woff2UnknownTagSize = sstruct.calcsize(woff2UnknownTagFormat)

woff2Base128MaxSize = 5
woff2DirectoryEntryMaxSize = woff2FlagsSize + woff2UnknownTagSize + 2 * woff2Base128MaxSize

woff2TransformedTableTags = ('glyf', 'loca')

woff2GlyfTableFormat = """
		> # big endian
		version:                  L  # = 0x00000000
		numGlyphs:                H  # Number of glyphs
		indexFormat:              H  # Offset format for loca table
		nContourStreamSize:       L  # Size of nContour stream
		nPointsStreamSize:        L  # Size of nPoints stream
		flagStreamSize:           L  # Size of flag stream
		glyphStreamSize:          L  # Size of glyph stream
		compositeStreamSize:      L  # Size of composite stream
		bboxStreamSize:           L  # Comnined size of bboxBitmap and bboxStream
		instructionStreamSize:    L  # Size of instruction stream
"""

woff2GlyfTableFormatSize = sstruct.calcsize(woff2GlyfTableFormat)

bboxFormat = """
		>	# big endian
		xMin:				h
		yMin:				h
		xMax:				h
		yMax:				h
"""


class WOFF2DirectoryEntry(DirectoryEntry):

	def fromFile(self, file):
		pos = file.tell()
		data = file.read(woff2DirectoryEntryMaxSize)
		left = self.fromString(data)
		consumed = len(data) - len(left)
		file.seek(pos + consumed)

	def fromString(self, data):
		dummy, data = sstruct.unpack2(woff2FlagsFormat, data, self)
		if self.flags & 0x3F == 0x3F:
			# if bits [0..5] of the flags byte == 63, read a 4-byte arbitrary tag value
			dummy, data = sstruct.unpack2(woff2UnknownTagFormat, data, self)
		else:
			# otherwise, tag is derived from a fixed 'Known Tags' table
			self.tag = woff2KnownTags[self.flags & 0x3F]
		self.tag = Tag(self.tag)
		if self.flags & 0xC0 != 0:
			raise TTLibError('bits 6-7 are reserved and must be 0')
		# UIntBase128 value specifying the table's length in an uncompressed font
		self.origLength, data = unpackBase128(data)
		self.length = self.origLength
		if self.tag in woff2TransformedTableTags:
			# Optional UIntBase128 specifying the length of the 'transformed' table.
			# For simplicity, the 'transformLength' is called 'length' here.
			self.length, data = unpackBase128(data)
		# return left over data
		return data

	def toString(self):
		data = struct.pack('B', self.flags)
		if (self.flags & 0x3f) == 0x3f:
			data += struct.pack('>L', self.tag)
		data += packBase128(self.origLength)
		if self.tag in woff2TransformedTableTags:
			data += packBase128(self.length)
		return data


class WOFF2Glyf(object):

	def __init__(self, ttFont=None, indexFormat=None, numGlyphs=None, locaData=None):
		self.tempFont = ttFont
		if not self.tempFont:
			self.tempFont = TTFont(flavor="woff2", recalcBBoxes=False)
			self.tempFont['head'] = getTableClass('head')()
			self.tempFont['maxp'] = getTableClass('maxp')()
			self.tempFont['loca'] = getTableClass('loca')()
		self.indexFormat = indexFormat
		self.numGlyphs = numGlyphs
		self.locaData = locaData

	def decodeData(self, data):
		inputDataSize = len(data)

		# unpack transformed glyf table header
		dummy, data = sstruct.unpack2(woff2GlyfTableFormat, data, self)
		numGlyphs = self.numGlyphs
		substreamOffset = woff2GlyfTableFormatSize

		# slice stream data into seven individual sub-streams
		self.nContourStream = data[:self.nContourStreamSize]
		data = data[self.nContourStreamSize:]
		substreamOffset += self.nContourStreamSize

		self.nPointsStream = data[:self.nPointsStreamSize]
		data = data[self.nPointsStreamSize:]
		substreamOffset += self.nPointsStreamSize

		self.flagStream = data[:self.flagStreamSize]
		data = data[self.flagStreamSize:]
		substreamOffset += self.flagStreamSize

		self.glyphStream = data[:self.glyphStreamSize]
		data = data[self.glyphStreamSize:]
		substreamOffset += self.glyphStreamSize

		self.compositeStream = data[:self.compositeStreamSize]
		data = data[self.compositeStreamSize:]
		substreamOffset += self.compositeStreamSize

		combinedBboxStream = data[:self.bboxStreamSize]
		data = data[self.bboxStreamSize:]
		substreamOffset += self.bboxStreamSize

		self.instructionStream = data[:self.instructionStreamSize]
		data = data[self.instructionStreamSize:]
		substreamOffset += self.instructionStreamSize

		# check all input data was read and no more is left
		if substreamOffset != inputDataSize:
			raise TTLibError(
				"incorrect size of transformed 'glyf' table: expected %d, received %d bytes"
				% (substreamOffset, inputDataSize))

		# extract bboxBitmap from bboxStream
		bboxBitmapSize = ((numGlyphs + 31) >> 5) << 2
		bboxBitmap = combinedBboxStream[:bboxBitmapSize]
		self.bboxBitmap = array.array('B', bboxBitmap)
		self.bboxStream = combinedBboxStream[bboxBitmapSize:]

		# convert nContourStream to a numGlyphs-long Int16 array
		self.nContourStream = array.array("h", self.nContourStream)
		if sys.byteorder != "big":
			self.nContourStream.byteswap()
		assert len(self.nContourStream) == numGlyphs

		# create empty glyf table
		self.tempFont['glyf'] = glyfTable = getTableClass('glyf')()

		# build dummy glyphOrder
		glyfTable.glyphOrder = glyphOrder = []
		for glyphID in range(numGlyphs):
			glyphName = "glyph%d" % glyphID
			glyphOrder.append(glyphName)
		self.tempFont.setGlyphOrder(glyphOrder)

		# decode each glyph and populate glyf table
		glyfTable.glyphs = {}
		for glyphID, glyphName in enumerate(glyphOrder):
			glyph = getTableModule('glyf').Glyph()
			glyfTable.glyphs[glyphName] = glyph
			glyph.numberOfContours = self.getNumberOfContours(glyphID)
			if glyph.numberOfContours == 0:
				continue
			if glyph.isComposite():
				self.decodeComponents(glyph)
			elif glyph.numberOfContours > 0:
				self.decodeCoordinates(glyph)
			haveBBox = self.haveBBox(glyphID)
			if glyph.isComposite() and not haveBBox:
				raise TTLibError('no bbox values for composite glyph %d' % glyphID)
			if haveBBox:
				self.decodeBBox(glyph)
			else:
				self.recalcBBox(glyph)

		# compile glyf table
		data = glyfTable.compile(self.tempFont)

		# compile loca table
		locaTable = self.tempFont['loca']
		locaData = locaTable.compile(self.tempFont)
		origIndexFormat = self.indexFormat
		currIndexFormat = self.tempFont['head'].indexToLocFormat
		if currIndexFormat != origIndexFormat:
			raise TTLibError(
				"reconstructed 'loca' table has wrong index format: expected %d, found %d"
				% (origIndexFormat, currIndexFormat))
		self.locaData = locaData

		# return compiled glyf data
		return data

	def getNumberOfContours(self, glyphID):
		return self.nContourStream[glyphID]

	def decodeComponents(self, glyph):
		data = self.compositeStream
		glyph.components = []
		more = 1
		haveInstructions = 0
		while more:
			component = getTableModule('glyf').GlyphComponent()
			more, haveInstr, data = component.decompile(data, self.tempFont['glyf'])
			haveInstructions = haveInstructions | haveInstr
			glyph.components.append(component)
		self.compositeStream = data
		if haveInstructions:
			self.decodeInstructions(glyph)

	def decodeCoordinates(self, glyph):
		nPointsStream = self.nPointsStream
		endPtsOfContours = []
		endPoint = -1
		for i in range(glyph.numberOfContours):
			ptsOfContour, nPointsStream = unpack255UShort(nPointsStream)
			endPoint += ptsOfContour
			endPtsOfContours.append(endPoint)
		glyph.endPtsOfContours = endPtsOfContours
		nPoints = endPoint + 1
		self.nPointsStream = nPointsStream
		glyph.flags, glyph.coordinates = self.decodeTriplets(nPoints)
		self.decodeInstructions(glyph)

	def decodeInstructions(self, glyph):
		glyphStream = self.glyphStream
		instructionStream = self.instructionStream
		instructionLength, glyphStream = unpack255UShort(glyphStream)
		glyph.program = ttProgram.Program()
		glyph.program.fromBytecode(instructionStream[:instructionLength])
		self.glyphStream = glyphStream
		self.instructionStream = instructionStream[instructionLength:]

	def haveBBox(self, index):
		return bool(self.bboxBitmap[index >> 3] & (0x80 >> (index & 7)))

	def decodeBBox(self, glyph):
		dummy, self.bboxStream = sstruct.unpack2(bboxFormat, self.bboxStream, glyph)

	def recalcBBox(self, glyph):
		glyph.recalcBounds(self.tempFont['glyf'])

	def decodeTriplets(self, nPoints):

		def withSign(flag, baseval):
			assert 0 <= baseval and baseval < 65536, 'integer overflow'
			return baseval if flag & 1 else -baseval

		flagStream = self.flagStream
		flagSize = nPoints
		if flagSize > len(flagStream):
			raise TTLibError("not enough 'flagStream' data")
		flagsData = flagStream[:flagSize]
		self.flagStream = flagStream[flagSize:]
		flags = array.array('B', flagsData)

		glyphStream = self.glyphStream
		triplets = array.array('B', glyphStream)
		nTriplets = len(triplets)
		assert nPoints <= nTriplets

		x = 0
		y = 0
		coordinates = getTableModule('glyf').GlyphCoordinates.zeros(nPoints)
		onCurves = []
		tripletIndex = 0
		for i in range(nPoints):
			flag = flags[i]
			onCurve = not bool(flag >> 7)
			flag &= 0x7f
			if flag < 84:
				nBytes = 1
			elif flag < 120:
				nBytes = 2
			elif flag < 124:
				nBytes = 3
			else:
				nBytes = 4
			assert ((tripletIndex + nBytes) <= nTriplets)
			if flag < 10:
				dx = 0
				dy = withSign(flag, ((flag & 14) << 7) + triplets[tripletIndex])
			elif flag < 20:
				dx = withSign(flag, (((flag - 10) & 14) << 7) + triplets[tripletIndex])
				dy = 0
			elif flag < 84:
				b0 = flag - 20
				b1 = triplets[tripletIndex]
				dx = withSign(flag, 1 + (b0 & 0x30) + (b1 >> 4))
				dy = withSign(flag >> 1, 1 + ((b0 & 0x0c) << 2) + (b1 & 0x0f))
			elif flag < 120:
				b0 = flag - 84
				dx = withSign(flag, 1 + ((b0 // 12) << 8) + triplets[tripletIndex])
				dy = withSign(flag >> 1,
					1 + (((b0 % 12) >> 2) << 8) + triplets[tripletIndex + 1])
			elif flag < 124:
				b2 = triplets[tripletIndex + 1]
				dx = withSign(flag, (triplets[tripletIndex] << 4) + (b2 >> 4))
				dy = withSign(flag >> 1,
					((b2 & 0x0f) << 8) + triplets[tripletIndex + 2])
			else:
				dx = withSign(flag,
					(triplets[tripletIndex] << 8) + triplets[tripletIndex + 1])
				dy = withSign(flag >> 1,
					(triplets[tripletIndex + 2] << 8) + triplets[tripletIndex + 3])
			tripletIndex += nBytes
			x += dx
			y += dy
			coordinates[i] = (x, y)
			onCurves.append(int(onCurve))
		bytesConsumed = tripletIndex
		self.glyphStream = glyphStream[bytesConsumed:]

		flags = array.array("B", onCurves)
		return flags, coordinates

	def encodeData(self, data):

		# decompile loca table using indexFormat and numGlyphs
		self.tempFont['head'].indexToLocFormat = self.indexFormat
		self.tempFont['maxp'].numGlyphs = self.numGlyphs
		self.tempFont['loca'].decompile(self.locaData, self.tempFont)

		# build dummy glyph order
		glyphOrder = ["glyph%d" % i for i in range(self.numGlyphs)]
		self.tempFont.setGlyphOrder(glyphOrder)
		self.tempFont.lazy = False

		# decompile glyf table
		self.tempFont['glyf'] = glyfTable = getTableClass('glyf')()
		glyfTable.decompile(data, self.tempFont)

		# initialise sub-streams
		self.nContourStream = array.array("h", [0]*self.numGlyphs)
		self.nPointsStream = ""
		self.flagStream = ""
		self.glyphStream = ""
		self.compositeStream = ""
		self.bboxStream = ""
		self.instructionStream = ""
		bboxBitmapSize = ((self.numGlyphs + 31) >> 5) << 2
		self.bboxBitmap = array.array('B', [0]*bboxBitmapSize)

		raise NotImplementedError

		# encode each glyph in glyf table
		for glyphID, glyphName in enumerate(glyfTable.glyphOrder):
			glyph = glyfTable.glyphs[glyphName]
			storeBBox = False
			if glyph.numberOfContours == 0:
				continue
			elif glyph.isComposite():
				self.encodeComponents(glyph)
				storeBBox = True
			else:
				self.encodeCoordinates(glyph)
			self.nContourStream[glyphID] = glyph.numberOfContours
			if storeBBox:
				self.encodeBBox(glyph)

		# pack nContourStream bytes
		if sys.byteorder != "big":
			self.nContourStream.byteswap()
		self.nContourStream = self.nContourStream.tostring()

		# combine bboxBitmap with bboxStream
		self.bboxBitmap = self.bboxBitmap.tostring()
		self.bboxStream = self.bboxBitmap + self.bboxStream

		# pack transformed glyf header
		self.nContourStreamSize = len(self.nContourStream)
		self.nPointsStreamSize = len(self.nPointsStream)
		self.flagStreamSize = len(self.flagStream)
		self.glyphStreamSize = len(self.glyphStream)
		self.compositeStreamSize = len(self.compositeStream)
		self.bboxStreamSize = len(self.bboxStream)
		self.instructionStreamSize = len(self.instructionStream)
		data = sstruct.pack(woffTransformedGlyfHeaderFormat, self)

		# append sub-streams
		data += self.nContourStream + self.nPointsStream + self.flagStream + \
			self.glyphStream + self.compositeStream + self.bboxStream + \
			self.instructionStream

		return data

	def __contains__(self, tag):
		return tag in self.tempFont

	def __getitem__(self, tag):
		return self.tempFont[tag]


def unpackBase128(data):
	""" A UIntBase128 encoded number is a sequence of bytes for which the most
	significant bit is set for all but the last byte, and clear for the last byte.
	The number itself is base 128 encoded in the lower 7 bits of each byte.
	"""
	result = 0
	for i in range(5):
		if len(data) == 0:
			raise TTLibError('not enough data to unpack UIntBase128')
		code, = struct.unpack(">B", data[0])
		data = data[1:]
		# if any of the top seven bits are set then we're about to overflow
		if result & 0xFE000000:
			raise TTLibError('UIntBase128 value exceeds 2**32-1')
		# set current value = old value times 128 bitwise-or (byte bitwise-and 127)
		result = (result << 7) | (code & 0x7f)
		# repeat until the most significant bit of byte is false
		if (code & 0x80) == 0:
			# return result plus left over data
			return result, data
	# make sure not to exceed the size bound
	raise TTLibError('UIntBase128-encoded sequence is longer than 5 bytes')

def base128Size(n):
	size = 1
	while n >= 128:
		size += 1
		n >>= 7
	return size

def packBase128(n):
	data = b''
	size = base128Size(n)
	for i in range(size):
		b = (n >> (7 * (size - i - 1))) & 0x7f
		if i < size - 1:
			b |= 0x80
		data += struct.pack('B', b)
	return data

def unpack255UShort(data):
	"""Based on MicroType Express specification, section 6.1.1."""
	code, = struct.unpack(">B", data[:1])
	data = data[1:]
	if code == 253:
		# read two more bytes as an unsigned short
		result, = struct.unpack(">H", data[:2])
		data = data[2:]
	elif code == 254:
		# read another byte, plus 253 * 2
		result, = struct.unpack(">B", data[:1])
		result += 506
		data = data[1:]
	elif code == 255:
		# read another byte, plus 253
		result, = struct.unpack(">B", data[:1])
		result += 253
		data = data[1:]
	else:
		# leave as is if lower than 253
		result = code
	# return result plus left over data
	return result, data

def write4BytePadding(file):
	"""Write NUL bytes at the end of file to pad data to a 4-byte boundary."""
	file.seek(0, 2)
	offset = file.tell()
	paddedOffset = (offset + 3) & ~3
	file.write(b'\0' * (paddedOffset - offset))
