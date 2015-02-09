from __future__ import print_function, division, absolute_import
from fontTools.misc.py23 import *
from fontTools.misc import sstruct
import struct
import sys
import array
import brotli
from fontTools.ttLib import TTFont, TTLibError, getTableModule, getTableClass
from fontTools.ttLib.sfnt import SFNTReader, SFNTWriter, DirectoryEntry, WOFFFlavorData
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
			if 'glyf' not in self.glyfDecoder:
				# make sure glyf is loaded first
				self['glyf']
			# get loca data from reconstructed glyf
			data = self.glyfDecoder.getLocaData()

		if len(data) != entry.origLength:
			raise TTLibError(
				"reconstructed '%s' table doesn't match original size: expected %d, found %d"
				% (tag, entry.origLength, len(data)))
		entry.data = data
		return data


class WOFF2Writer(SFNTWriter):
	pass


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

	def __init__(self, tempFont=None):
		if tempFont is None:
			self.tempFont = TTFont(flavor="woff2", recalcBBoxes=False)
			self.tempFont['maxp'] = getTableClass('maxp')()
			self.tempFont['head'] = getTableClass('head')()
			self.tempFont['loca'] = getTableClass('loca')()

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

		# compile glyf table (and update tempFont's loca)
		data = glyfTable.compile(self.tempFont)
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

	def getLocaData(self):
		table = self.tempFont['loca']
		data = table.compile(self.tempFont)
		origIndexFormat = self.indexFormat
		currIndexFormat = self.tempFont['head'].indexToLocFormat
		if currIndexFormat != origIndexFormat:
			raise TTLibError(
				"reconstructed 'loca' table has wrong index format: expected %d, found %d"
				% (origIndexFormat, currIndexFormat))
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
