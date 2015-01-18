"""ttLib/sfnt.py -- low-level module to deal with the sfnt file format.

Defines two public classes:
	SFNTReader
	SFNTWriter

(Normally you don't have to use these classes explicitly; they are 
used automatically by ttLib.TTFont.)

The reading and writing of sfnt files is separated in two distinct 
classes, since whenever to number of tables changes or whenever
a table's length chages you need to rewrite the whole file anyway.
"""

from __future__ import print_function, division, absolute_import
from fontTools.misc.py23 import *
from fontTools.misc import sstruct
from fontTools.ttLib import getSearchRange, TTLibError, getTableClass, getTableModule
import struct


class SFNTReader(object):
	
	def __init__(self, file, checkChecksums=1, fontNumber=-1):
		self.file = file
		self.checkChecksums = checkChecksums

		self.flavor = None
		self.flavorData = None
		self.DirectoryEntry = SFNTDirectoryEntry
		self.sfntVersion = self.file.read(4)
		self.file.seek(0)
		if self.sfntVersion == b"ttcf":
			sstruct.unpack(ttcHeaderFormat, self.file.read(ttcHeaderSize), self)
			assert self.Version == 0x00010000 or self.Version == 0x00020000, "unrecognized TTC version 0x%08x" % self.Version
			if not 0 <= fontNumber < self.numFonts:
				raise TTLibError("specify a font number between 0 and %d (inclusive)" % (self.numFonts - 1))
			offsetTable = struct.unpack(">%dL" % self.numFonts, self.file.read(self.numFonts * 4))
			if self.Version == 0x00020000:
				pass # ignoring version 2.0 signatures
			self.file.seek(offsetTable[fontNumber])
			sstruct.unpack(sfntDirectoryFormat, self.file.read(sfntDirectorySize), self)
		elif self.sfntVersion == b"wOFF":
			self.flavor = "woff"
			self.DirectoryEntry = WOFFDirectoryEntry
			sstruct.unpack(woffDirectoryFormat, self.file.read(woffDirectorySize), self)
		elif self.sfntVersion == b"wOF2":
			self.flavor = "woff2"
			self.DirectoryEntry = WOFF2DirectoryEntry
			sstruct.unpack(woff2DirectoryFormat, self.file.read(woff2DirectorySize), self)
		else:
			sstruct.unpack(sfntDirectoryFormat, self.file.read(sfntDirectorySize), self)
		self.sfntVersion = Tag(self.sfntVersion)

		if self.sfntVersion not in ("\x00\x01\x00\x00", "OTTO", "true"):
			raise TTLibError("Not a TrueType or OpenType font (bad sfntVersion)")
		self.tables = {}
		offset = 0
		for i in range(self.numTables):
			entry = self.DirectoryEntry()
			entry.fromFile(self.file)
			self.tables[Tag(entry.tag)] = entry
			if self.flavor == "woff2":
				# WOFF2 doesn't store offsets to individual tables. These can be 
				# calculated by summing up the tables' lengths (there's no padding)
				entry.offset = offset
				offset += entry.length

		if self.flavor == "woff2":
			# WOFF2 font data is compressed in a single stream comprising all tables
			# so it must be decompressed once as a whole
			totalUncompressedSize = offset
			compressedData = self.file.read(self.totalCompressedSize)
			import brotli
			decompressedData = brotli.decompress(compressedData)
			if len(decompressedData) != totalUncompressedSize:
				raise TTLibError(
					'unexpected size for decompressed font data: expected %d, found %d'
					% (totalUncompressedSize, len(decompressedData)))
			self.transformBuffer = StringIO(decompressedData)
			self.tempFont = None

		# Load flavor data if any
		if self.flavor == "woff":
			self.flavorData = WOFFFlavorData(self)

	def has_key(self, tag):
		return tag in self.tables

	__contains__ = has_key
	
	def keys(self):
		return self.tables.keys()
	
	def __getitem__(self, tag):
		"""Fetch the raw table data. Reconstruct data if table is transformed."""
		entry = self.tables[Tag(tag)]

		if self.flavor != "woff2":
			data = entry.loadData(self.file)
			if self.checkChecksums:
				if tag == 'head':
					# Beh: we have to special-case the 'head' table.
					checksum = calcChecksum(data[:8] + b'\0\0\0\0' + data[12:])
				else:
					checksum = calcChecksum(data)
				if self.checkChecksums > 1:
					# Be obnoxious, and barf when it's wrong
					assert checksum == entry.checksum, "bad checksum for '%s' table" % tag
				elif checksum != entry.checkSum:
					# Be friendly, and just print a warning.
					print("bad checksum for '%s' table" % tag)
			return data

		rawData = entry.loadData(self.transformBuffer)
		if not entry.transformed:
			return rawData

		if tag not in woff2TransformedTableTags:
			raise TTLibError('transform for the tag "%s" is not known')

		if hasattr(entry, 'data'):
			# table already reconstructed, return compiled data
			return entry.data

		if self.tempFont is None:
			from fontTools.ttLib import TTFont
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

		if len(data) != entry.origLength:
			raise TTLibError(
				"reconstructed '%s' table doesn't match original size: expected %d, found %d"
				% (tag, entry.origLength, len(data)))

		if tag == 'loca':
			origIndexFormat = self.tempFont['glyf'].indexFormat
			currIndexFormat = self.tempFont['head'].indexToLocFormat
			if currIndexFormat != origIndexFormat:
				raise TTLibError(
					"reconstructed 'loca' table has wrong index format: expected %d, found %d"
					% (origIndexFormat, currIndexFormat))
		return data
	
	def __delitem__(self, tag):
		del self.tables[Tag(tag)]
	
	def close(self):
		self.file.close()


class SFNTWriter(object):
	
	def __init__(self, file, numTables, sfntVersion="\000\001\000\000",
		     flavor=None, flavorData=None):
		self.file = file
		self.numTables = numTables
		self.sfntVersion = Tag(sfntVersion)
		self.flavor = flavor
		self.flavorData = flavorData

		if self.flavor == "woff":
			self.directoryFormat = woffDirectoryFormat
			self.directorySize = woffDirectorySize
			self.DirectoryEntry = WOFFDirectoryEntry

			self.signature = "wOFF"
		else:
			assert not self.flavor,  "Unknown flavor '%s'" % self.flavor
			self.directoryFormat = sfntDirectoryFormat
			self.directorySize = sfntDirectorySize
			self.DirectoryEntry = SFNTDirectoryEntry

			self.searchRange, self.entrySelector, self.rangeShift = getSearchRange(numTables, 16)

		self.nextTableOffset = self.directorySize + numTables * self.DirectoryEntry.formatSize
		# clear out directory area
		self.file.seek(self.nextTableOffset)
		# make sure we're actually where we want to be. (old cStringIO bug)
		self.file.write(b'\0' * (self.nextTableOffset - self.file.tell()))
		self.tables = {}
	
	def __setitem__(self, tag, data):
		"""Write raw table data to disk."""
		if tag in self.tables:
			raise TTLibError("cannot rewrite '%s' table: length does not match directory entry" % tag)

		entry = self.DirectoryEntry()
		entry.tag = tag
		entry.offset = self.nextTableOffset
		if tag == 'head':
			entry.checkSum = calcChecksum(data[:8] + b'\0\0\0\0' + data[12:])
			self.headTable = data
			entry.uncompressed = True
		else:
			entry.checkSum = calcChecksum(data)
		entry.saveData (self.file, data)

		self.nextTableOffset = self.nextTableOffset + ((entry.length + 3) & ~3)
		# Add NUL bytes to pad the table data to a 4-byte boundary.
		# Don't depend on f.seek() as we need to add the padding even if no
		# subsequent write follows (seek is lazy), ie. after the final table
		# in the font.
		self.file.write(b'\0' * (self.nextTableOffset - self.file.tell()))
		assert self.nextTableOffset == self.file.tell()
		
		self.tables[tag] = entry
	
	def close(self):
		"""All tables must have been written to disk. Now write the
		directory.
		"""
		tables = sorted(self.tables.items())
		if len(tables) != self.numTables:
			raise TTLibError("wrong number of tables; expected %d, found %d" % (self.numTables, len(tables)))

		if self.flavor == "woff":
			self.signature = b"wOFF"
			self.reserved = 0

			self.totalSfntSize = 12
			self.totalSfntSize += 16 * len(tables)
			for tag, entry in tables:
				self.totalSfntSize += (entry.origLength + 3) & ~3

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
				self.file.seek(0,2)
				self.metaOffset = self.file.tell()
				import zlib
				compressedMetaData = zlib.compress(data.metaData)
				self.metaLength = len(compressedMetaData)
				self.file.write(compressedMetaData)
			else:
				self.metaOffset = self.metaLength = self.metaOrigLength = 0
			if data.privData:
				self.file.seek(0,2)
				off = self.file.tell()
				paddedOff = (off + 3) & ~3
				self.file.write('\0' * (paddedOff - off))
				self.privOffset = self.file.tell()
				self.privLength = len(data.privData)
				self.file.write(data.privData)
			else:
				self.privOffset = self.privLength = 0

			self.file.seek(0,2)
			self.length = self.file.tell()

		else:
			assert not self.flavor,  "Unknown flavor '%s'" % self.flavor
			pass
		
		directory = sstruct.pack(self.directoryFormat, self)
		
		self.file.seek(self.directorySize)
		seenHead = 0
		for tag, entry in tables:
			if tag == "head":
				seenHead = 1
			directory = directory + entry.toString()
		if seenHead:
			self.writeMasterChecksum(directory)
		self.file.seek(0)
		self.file.write(directory)

	def _calcMasterChecksum(self, directory):
		# calculate checkSumAdjustment
		tags = list(self.tables.keys())
		checksums = []
		for i in range(len(tags)):
			checksums.append(self.tables[tags[i]].checkSum)

		# TODO(behdad) I'm fairly sure the checksum for woff is not working correctly.
		# Haven't debugged.
		if self.DirectoryEntry != SFNTDirectoryEntry:
			# Create a SFNT directory for checksum calculation purposes
			self.searchRange, self.entrySelector, self.rangeShift = getSearchRange(self.numTables, 16)
			directory = sstruct.pack(sfntDirectoryFormat, self)
			tables = sorted(self.tables.items())
			for tag, entry in tables:
				sfntEntry = SFNTDirectoryEntry()
				for item in ['tag', 'checkSum', 'offset', 'length']:
					setattr(sfntEntry, item, getattr(entry, item))
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
		self.file.seek(self.tables['head'].offset + 8)
		self.file.write(struct.pack(">L", checksumadjustment))


# -- sfnt directory helpers and cruft

ttcHeaderFormat = """
		> # big endian
		TTCTag:                  4s # "ttcf"
		Version:                 L  # 0x00010000 or 0x00020000
		numFonts:                L  # number of fonts
		# OffsetTable[numFonts]: L  # array with offsets from beginning of file
		# ulDsigTag:             L  # version 2.0 only
		# ulDsigLength:          L  # version 2.0 only
		# ulDsigOffset:          L  # version 2.0 only
"""

ttcHeaderSize = sstruct.calcsize(ttcHeaderFormat)

sfntDirectoryFormat = """
		> # big endian
		sfntVersion:    4s
		numTables:      H    # number of tables
		searchRange:    H    # (max2 <= numTables)*16
		entrySelector:  H    # log2(max2 <= numTables)
		rangeShift:     H    # numTables*16-searchRange
"""

sfntDirectorySize = sstruct.calcsize(sfntDirectoryFormat)

sfntDirectoryEntryFormat = """
		> # big endian
		tag:            4s
		checkSum:       L
		offset:         L
		length:         L
"""

sfntDirectoryEntrySize = sstruct.calcsize(sfntDirectoryEntryFormat)

woffDirectoryFormat = """
		> # big endian
		signature:      4s   # "wOFF"
		sfntVersion:    4s
		length:         L    # total woff file size
		numTables:      H    # number of tables
		reserved:       H    # set to 0
		totalSfntSize:  L    # uncompressed size
		majorVersion:   H    # major version of WOFF file
		minorVersion:   H    # minor version of WOFF file
		metaOffset:     L    # offset to metadata block
		metaLength:     L    # length of compressed metadata
		metaOrigLength: L    # length of uncompressed metadata
		privOffset:     L    # offset to private data block
		privLength:     L    # length of private data block
"""

woffDirectorySize = sstruct.calcsize(woffDirectoryFormat)

woffDirectoryEntryFormat = """
		> # big endian
		tag:            4s
		offset:         L
		length:         L    # compressed length
		origLength:     L    # original length
		checkSum:       L    # original checksum
"""

woffDirectoryEntrySize = sstruct.calcsize(woffDirectoryEntryFormat)

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


class DirectoryEntry(object):
	
	def __init__(self):
		self.uncompressed = False # if True, always embed entry raw

	def fromFile(self, file):
		sstruct.unpack(self.format, file.read(self.formatSize), self)
	
	def fromString(self, str):
		sstruct.unpack(self.format, str, self)
	
	def toString(self):
		return sstruct.pack(self.format, self)
	
	def __repr__(self):
		if hasattr(self, "tag"):
			return "<%s '%s' at %x>" % (self.__class__.__name__, self.tag, id(self))
		else:
			return "<%s at %x>" % (self.__class__.__name__, id(self))

	def loadData(self, file):
		file.seek(self.offset)
		data = file.read(self.length)
		assert len(data) == self.length
		if hasattr(self.__class__, 'decodeData'):
			data = self.decodeData(data)
		return data

	def saveData(self, file, data):
		if hasattr(self.__class__, 'encodeData'):
			data = self.encodeData(data)
		self.length = len(data)
		file.seek(self.offset)
		file.write(data)

	def decodeData(self, rawData):
		return rawData

	def encodeData(self, data):
		return data

class SFNTDirectoryEntry(DirectoryEntry):

	format = sfntDirectoryEntryFormat
	formatSize = sfntDirectoryEntrySize

class WOFFDirectoryEntry(DirectoryEntry):

	format = woffDirectoryEntryFormat
	formatSize = woffDirectoryEntrySize
	zlibCompressionLevel = 6

	def decodeData(self, rawData):
		import zlib
		if self.length == self.origLength:
			data = rawData
		else:
			assert self.length < self.origLength
			data = zlib.decompress(rawData)
			assert len (data) == self.origLength
		return data

	def encodeData(self, data):
		import zlib
		self.origLength = len(data)
		if not self.uncompressed:
			compressedData = zlib.compress(data, self.zlibCompressionLevel)
		if self.uncompressed or len(compressedData) >= self.origLength:
			# Encode uncompressed
			rawData = data
			self.length = self.origLength
		else:
			rawData = compressedData
			self.length = len(rawData)
		return rawData

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
		self.transformed = False
		self.length = self.origLength
		if self.tag in woff2TransformedTableTags:
			# only glyf and loca are subject to transformation
			self.transformed = True
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
		if self.transformed:
			data += packBase128(self.length)
		return data

class WOFFFlavorData():

	Flavor = 'woff'

	def __init__(self, reader=None):
		self.majorVersion = None
		self.minorVersion = None
		self.metaData = None
		self.privData = None
		if reader:
			self.majorVersion = reader.majorVersion
			self.minorVersion = reader.minorVersion
			if reader.metaLength:
				reader.file.seek(reader.metaOffset)
				rawData = reader.file.read(reader.metaLength)
				assert len(rawData) == reader.metaLength
				import zlib
				data = zlib.decompress(rawData)
				assert len(data) == reader.metaOrigLength
				self.metaData = data
			if reader.privLength:
				reader.file.seek(reader.privOffset)
				data = reader.file.read(reader.privLength)
				assert len(data) == reader.privLength
				self.privData = data

class WOFF2Glyf(getTableClass('glyf')):

	def __init__(self):
		self.tableTag = Tag('glyf')

	def reconstruct(self, data, ttFont):
		import sys, array

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
		from fontTools.ttLib.tables import ttProgram
		self.program = ttProgram.Program()
		self.program.fromBytecode(instructionStream[:instructionLength])
		glyfTable.glyphStream = glyphStream
		glyfTable.instructionStream = instructionStream[instructionLength:]

	def decodeTriplets(self, nPoints, glyfTable):
		import array

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

def calcChecksum(data):
	"""Calculate the checksum for an arbitrary block of data.
	Optionally takes a 'start' argument, which allows you to
	calculate a checksum in chunks by feeding it a previous
	result.
	
	If the data length is not a multiple of four, it assumes
	it is to be padded with null byte. 

		>>> print calcChecksum(b"abcd")
		1633837924
		>>> print calcChecksum(b"abcdxyz")
		3655064932
	"""
	remainder = len(data) % 4
	if remainder:
		data += b"\0" * (4 - remainder)
	value = 0
	blockSize = 4096
	assert blockSize % 4 == 0
	for i in range(0, len(data), blockSize):
		block = data[i:i+blockSize]
		longs = struct.unpack(">%dL" % (len(block) // 4), block)
		value = (value + sum(longs)) & 0xffffffff
	return value


if __name__ == "__main__":
    import doctest
    doctest.testmod()
