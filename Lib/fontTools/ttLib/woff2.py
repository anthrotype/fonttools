from __future__ import print_function, division, absolute_import
from fontTools.misc.py23 import *
from fontTools.misc import sstruct
import struct
import sys
import array
import brotli
from fontTools.ttLib import TTFont, TTLibError, getTableModule, getTableClass
from fontTools.ttLib.sfnt import SFNTReader, DirectoryEntry, WOFFFlavorData
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
		# WOFF2 doesn't store offsets to individual tables; to access table data
		# randomly, we must reconstruct the offsets from the tables' lengths
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
		uncompressedDataSize = offset
		compressedData = self.file.read(self.totalCompressedSize)
		decompressedData = brotli.decompress(compressedData)
		if len(decompressedData) != uncompressedDataSize:
			raise TTLibError(
				'unexpected size for decompressed font data: expected %d, found %d'
				% (uncompressedDataSize, len(decompressedData)))
		self.transformBuffer = StringIO(decompressedData)
		self.tempFont = None

		# Load flavor data if any
		self.flavorData = WOFFFlavorData(self)

	def __getitem__(self, tag):
		entry = self.tables[Tag(tag)]
		rawData = entry.loadData(self.transformBuffer)
		if not entry.transform:
			return rawData

		if tag not in woff2TransformedTableTags:
			raise TTLibError('transform for the tag "%s" is not known')
		if hasattr(entry, 'data'):
			# table already reconstructed, return compiled data
			return entry.data

		if self.tempFont is None:
			# initialise temporary font object to store reconstructed tables
			self.tempFont = TTFont(sfntVersion=self.sfntVersion, flavor=self.flavor,
					recalcBBoxes=False)
			self.tempFont['maxp'] = getTableClass('maxp')()
			self.tempFont['head'] = getTableClass('head')()
			self.tempFont['loca'] = getTableClass('loca')()

		if tag == 'glyf':
			table = WOFF2Glyf()
			self.tempFont['glyf'] = table
			# reconstruct both glyf and loca tables
			table.reconstruct(rawData, self.tempFont)
		elif tag == 'loca':
			if 'glyf' not in self.tempFont:
				# make sure glyf is loaded first
				self['glyf']
			table = self.tempFont['loca']

		entry.data = data = table.compile(self.tempFont)

		currLength = len(data)
		if currLength != entry.origLength:
			raise TTLibError(
				"reconstructed '%s' table doesn't match original size: expected %d, found %d"
				% (tag, entry.origLength, currLength))

		if tag == 'loca':
			origIndexFormat = self.tempFont['glyf'].indexFormat
			currIndexFormat = self.tempFont['head'].indexToLocFormat
			if currIndexFormat != origIndexFormat:
				raise TTLibError(
					"reconstructed 'loca' table has wrong index format: expected %d, found %d"
					% (origIndexFormat, currIndexFormat))

		return data


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

def write4BytePadding(file):
	"""Write NUL bytes at the end of file to pad data to a 4-byte boundary."""
	file.seek(0, 2)
	offset = file.tell()
	paddedOffset = (offset + 3) & ~3
	file.write(b'\0' * (paddedOffset - offset))

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
		self.transform = False
		self.length = self.origLength
		if self.tag in woff2TransformedTableTags:
			# only glyf and loca are subject to transformation
			self.transform = True
			# Optional UIntBase128 specifying the length of the 'transformed' table.
			# For simplicity, the 'transformLength' is called 'length' here.
			self.length, data = unpackBase128(data)
		# transformed loca is reconstructed as part of the glyf decoding process
		# and its length must always be 0
		if self.tag == 'loca' and self.length != 0:
			raise TTLibError(
				"incorrect size of transformed 'loca' table: expected 0, received %d bytes"
				% (len(self.length)))
		# return left over data
		return data

	def toString(self):
		data = struct.pack('B', self.flags)
		if (self.flags & 0x3f) == 0x3f:
			data += struct.pack('>L', self.tag)
		data += packBase128(self.origLength)
		if self.transform:
			data += packBase128(self.length)
		return data

class WOFF2Loca(getTableClass('loca')):

	def __init__(self, indexFormat=None):
		self.tableTag = Tag('loca')
		self.indexFormat = indexFormat

	def reconstruct(self, glyfTable):
		self.indexFormat = glyfTable.indexFormat
		self.locations = glyfTable.locations
		return self.compile()

	def transform(self):
		return b""

	def decompile(self, data):
		longFormat = self.indexFormat
		if longFormat:
			format = "I"
		else:
			format = "H"
		locations = array.array(format)
		locations.fromstring(data)
		if sys.byteorder != "big":
			locations.byteswap()
		if not longFormat:
			l = array.array("I")
			for i in range(len(locations)):
				l.append(locations[i] * 2)
			locations = l
		self.locations = locations

	def _compile(self):
		longFormat = self.indexFormat
		locations = self.locations
		if longFormat:
			locations = array.array("I", locations)
		else:
			# for the 'short' loca, divide the actual offsets by 2
			locations = array.array("H", [value >> 1 for value in locations])
		if sys.byteorder != "big":
			locations.byteswap()
		return locations.tostring()

class WOFF2Glyf(getTableClass('glyf')):

	def __init__(self):
		self.tableTag = Tag('glyf')

	def reconstruct(self, data, ttFont):
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

		# get bboxBitmap from bboxStream
		bboxBitmapSize = ((numGlyphs + 31) >> 5) << 2
		bboxBitmap = combinedBboxStream[:bboxBitmapSize]
		self.bboxBitmap = array.array('B', bboxBitmap)
		self.bboxStream = combinedBboxStream[bboxBitmapSize:]

		# cast nContourStream as a numGlyphs-long Int16 array
		self.nContourStream = array.array("h", self.nContourStream)
		if sys.byteorder != "big":
			self.nContourStream.byteswap()
		assert len(self.nContourStream) == numGlyphs

		# build temp glyphOrder with dummy glyph names
		self.glyphOrder = glyphOrder = []
		for i in range(numGlyphs):
			glyphName = "glyph%d" % i
			glyphOrder.append(glyphName)
		ttFont.setGlyphOrder(glyphOrder)

		# decompile each glyph
		self.glyphs = {}
		for i in range(numGlyphs):
			glyphName = glyphOrder[i]
			glyph = WOFF2Glyph(i, self)
			self.glyphs[glyphName] = glyph

	def decompile(self, data, loca, lazy=False):
		last = int(loca[0])
		self.glyphs = {}
		self.glyphOrder = glyphOrder = []
		for i in range(0, len(loca)-1):
			glyphName = 'glyph%s' % i
			glyphOrder.append(glyphName)
			next = int(loca[i+1])
			glyphdata = data[last:next]
			if len(glyphdata) != (next - last):
				raise TTLibError("not enough 'glyf' table data")
			glyph = getTableModule('glyf').Glyph(glyphdata)
			self.glyphs[glyphName] = glyph
			last = next
		if len(data) - next >= 4:
			raise TTLibError(
				"too much 'glyf' table data: expected %d, received %d bytes" %
					(next, len(data)))
		if lazy is False:
			for glyph in self.glyphs.values():
				glyph.expand(self)

	def _compileGlyphData(self, recalcBBoxes=False, compact=True):
		""" Return a list of compiled glyph data, padded to 4-byte boundaries.
		"""
		longFormat = self.indexFormat
		dataList = []
		currentLocation = 0
		for glyphName in self.glyphOrder:
			glyph = self.glyphs[glyphName]
			if compact and not hasattr(glyph, 'data'):
				# store glyph data in 'compact' form
				glyph.compact(self, recalcBBoxes)
			glyphData = glyph.compile(self, recalcBBoxes)
			# pad glyph data to 4-byte boundary
			glyphSize = len(glyphData)
			paddedGlyphSize = (glyphSize + 3) & ~3
			glyphData += b'\0' * (paddedGlyphSize - glyphSize)
			if not longFormat:
				# make sure the data fits the 'short' version
				if currentLocation + len(glyphData) > 0x1FFFF:
					raise TTLibError(
						"glyph offset exceeds the limits of 'short' loca format: 0x%05X"
						% (currentLocation + len(glyphData)))
			dataList.append(glyphData)
			currentLocation += len(glyphData)
		return dataList

	def _compile(self, recalcBBoxes=False, compact=True):
		dataList = self._compileGlyphData(recalcBBoxes, compact)
		return bytesjoin(dataList)

	@property
	def locations(self):
		locations = []
		currentLocation = 0
		for glyphData in self._compileGlyphData():
			locations.append(currentLocation)
			currentLocation += len(glyphData)
		locations.append(currentLocation)
		return locations

class WOFF2Glyph(getTableModule('glyf').Glyph):

	def __init__(self, index, glyfTable):
		self.numberOfContours = glyfTable.nContourStream[index]
		if self.numberOfContours < 0:
			self.decompileComponents(glyfTable)
		elif self.numberOfContours > 0:
			self.decompileCoordinates(glyfTable)
		self.decompileBBox(index, glyfTable)

	def decompileComponents(self, glyfTable):
		data = glyfTable.compositeStream
		self.components = []
		more = 1
		haveInstructions = 0
		while more:
			component = getTableModule('glyf').GlyphComponent()
			more, haveInstr, data = component.decompile(data, glyfTable)
			haveInstructions = haveInstructions | haveInstr
			self.components.append(component)
		glyfTable.compositeStream = data
		if haveInstructions:
			self.decompileInstructions(glyfTable)

	def decompileCoordinates(self, glyfTable):
		nPointsStream = glyfTable.nPointsStream
		endPtsOfContours = []
		endPoint = -1
		for i in range(self.numberOfContours):
			ptsOfContour, nPointsStream = unpack255UShort(nPointsStream)
			endPoint += ptsOfContour
			endPtsOfContours.append(endPoint)
		self.endPtsOfContours = endPtsOfContours
		nPoints = endPoint + 1
		glyfTable.nPointsStream = nPointsStream
		self.decodeTriplets(nPoints, glyfTable)
		self.decompileInstructions(glyfTable)

	def decompileBBox(self, index, glyfTable):
		if self.numberOfContours == 0:
			return
		bitmap = glyfTable.bboxBitmap
		bbox = glyfTable.bboxStream
		haveBBox = bitmap[index >> 3] & (0x80 >> (index & 7))
		if self.numberOfContours < 0 and not haveBBox:
			raise TTLibError('no bbox values for composite glyph %d' % index)
		if haveBBox:
			self.xMin, self.yMin, self.xMax, self.yMax = struct.unpack('>hhhh', bbox[:8])
			glyfTable.bboxStream = bbox[8:]
		else:
			self.recalcBounds(glyfTable)

	def decompileInstructions(self, glyfTable):
		glyphStream = glyfTable.glyphStream
		instructionStream = glyfTable.instructionStream
		instructionLength, glyphStream = unpack255UShort(glyphStream)
		self.program = ttProgram.Program()
		self.program.fromBytecode(instructionStream[:instructionLength])
		glyfTable.glyphStream = glyphStream
		glyfTable.instructionStream = instructionStream[instructionLength:]

	def decodeTriplets(self, nPoints, glyfTable):

		def withSign(flag, baseval):
			assert 0 <= baseval and baseval < 65536, 'integer overflow'
			return baseval if flag & 1 else -baseval

		flagStream = glyfTable.flagStream
		flagSize = nPoints
		if flagSize > len(flagStream):
			raise TTLibError("not enough 'flagStream' data")
		flagsData = flagStream[:flagSize]
		glyfTable.flagStream = flagStream[flagSize:]
		flags = array.array('B', flagsData)

		glyphStream = glyfTable.glyphStream
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
		glyfTable.glyphStream = glyphStream[bytesConsumed:]

		self.flags = array.array("B", onCurves)
		self.coordinates = coordinates
