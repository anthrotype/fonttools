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
from fontTools.ttLib import getSearchRange
import struct
import sys
import array
from fontTools.ttLib import getTableModule, getTableClass
from fontTools.ttLib.tables import ttProgram
from fontTools.ttLib import TTFont


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
				from fontTools import ttLib
				raise ttLib.TTLibError("specify a font number between 0 and %d (inclusive)" % (self.numFonts - 1))
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
			from fontTools import ttLib
			raise ttLib.TTLibError("Not a TrueType or OpenType font (bad sfntVersion)")
		self.tables = {}
		self.tableOrder = []
		offset = 0
		for i in range(self.numTables):
			entry = self.DirectoryEntry()
			entry.fromFile(self.file)
			tag = Tag(entry.tag)
			self.tables[tag] = entry
			self.tableOrder.append(tag)
			# WOFF2 doesn't store offsets to individual tables; to access random table
			# data, one must reconstruct the offsets from the tables' lengths.
			if self.flavor == 'woff2':
				entry.offset = offset
				offset += entry.length

		if self.flavor == 'woff2':
			# the total sum of the 'origLength' for non-transformed tables and
			# 'transformLength' for transformed tables is used to verify that the
			# decompressed data has the same size as the original uncompressed data.
			uncompressedSize = offset
			# there's no explicit offset to the compressed font data: this follows
			# immediately after the last directory entry; however, the length of
			# WOFF2 directory entries varies depending on their content. So, we need
			# to take the sum of all the directory entries...
			compressedDataOffset = woff2DirectorySize
			for entry in self.tables.values():
				compressedDataOffset += entry.size
			# WOFF2 font data is compressed in a single stream comprising all the
			# tables. So it is loaded once and decompressed as a whole, and then
			# stored inside a file-like '_fontBuffer' attribute of reader
			self.file.seek(compressedDataOffset)
			compressedData = self.file.read(self.totalCompressedSize)
			import brotli
			decompressedData = brotli.decompress(compressedData)
			if len(decompressedData) != uncompressedSize:
				from fontTools import ttLib
				raise ttLib.TTLibError(
					'unexpected size for uncompressed font data: expected %d, found %d'
					% (uncompressedSize, len(decompressedData)))
			self._fontBuffer = StringIO(decompressedData)

		# Load flavor data if any
		if self.flavor is not None:
			self.flavorData = FlavorData(self)

	def has_key(self, tag):
		return tag in self.tables

	__contains__ = has_key
	
	def keys(self):
		return self.tables.keys()
	
	def __getitem__(self, tag):
		"""Fetch the raw table data."""
		entry = self.tables[Tag(tag)]
		data = entry.loadData(self if self.flavor == "woff2" else self.file)
		# exclude WOFF2 from checking as it doesn't store original table checkSums
		if self.checkChecksums and self.flavor != 'woff2':
			if tag == 'head':
				# Beh: we have to special-case the 'head' table.
				checksum = calcChecksum(data[:8] + b'\0\0\0\0' + data[12:])
			else:
				checksum = calcChecksum(data)
			if self.checkChecksums > 1:
				# Be obnoxious, and barf when it's wrong
				assert checksum == entry.checkSum, "bad checksum for '%s' table" % tag
			elif checksum != entry.checkSum:
				# Be friendly, and just print a warning.
				print("bad checksum for '%s' table" % tag)
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
		elif self.flavor == "woff2":
			self.directoryFormat = woff2DirectoryFormat
			self.directorySize = woff2DirectorySize
			self.DirectoryEntry = WOFF2DirectoryEntry

			self.signature = "wOF2"
		else:
			assert not self.flavor,  "Unknown flavor '%s'" % self.flavor
			self.directoryFormat = sfntDirectoryFormat
			self.directorySize = sfntDirectorySize
			self.DirectoryEntry = SFNTDirectoryEntry

			self.searchRange, self.entrySelector, self.rangeShift = getSearchRange(numTables, 16)

		if self.flavor in ("woff", "woff2"):
			# calculate sfnt offsets for WOFF/WOFF2 checksum calculation purposes
			self.origNextTableOffset = sfntDirectorySize + numTables * sfntDirectoryEntrySize
		if self.flavor == "woff2":
			# make temporary buffer for storing raw table data before compressing
			self._fontBuffer = StringIO()
			self.nextTableOffset = 0
		else:
			self.nextTableOffset = self.directorySize + numTables * self.DirectoryEntry.formatSize
			# clear out directory area
			self.file.seek(self.nextTableOffset)
			# make sure we're actually where we want to be. (old cStringIO bug)
			self.file.write(b'\0' * (self.nextTableOffset - self.file.tell()))
		self.tables = {}
		self.tableOrder = []
	
	def __setitem__(self, tag, data):
		"""Write raw table data to disk."""
		if tag in self.tables:
			from fontTools import ttLib
			raise ttLib.TTLibError("cannot rewrite '%s' table: length does not match directory entry" % tag)

		entry = self.DirectoryEntry()
		entry.tag = Tag(tag)

		if tag == 'head':
			entry.checkSum = calcChecksum(data[:8] + b'\0\0\0\0' + data[12:])
			self.indexFormat, = struct.unpack(">H", data[50:52])
			self.headTable = data
			entry.uncompressed = True
		else:
			entry.checkSum = calcChecksum(data)

		if self.flavor in ("woff", "woff2"):
			entry.origOffset = self.origNextTableOffset

		if self.flavor == "woff2":
			entry.flags = knownTableIndex(tag)
			entry.transform = False
			# only glyf and loca tables needs to be transformed
			if tag == 'glyf':
				entry.transform = True
			elif tag == 'loca':
				if 'glyf' not in self.tables:
					from fontTools import ttLib
					raise ttLib.TTLibError('loca must follow glyf in WOFF2 table directory')
				entry.transform = True
			elif tag == 'maxp':
				self.maxpNumGlyphs, = struct.unpack(">H", data[4:6])
			entry.origLength = len(data)
			# table data is encoded and written to disk at the end
			entry.data = data
		else:
			entry.offset = self.nextTableOffset
			entry.saveData(self.file, data)

			self.nextTableOffset = self.nextTableOffset + ((entry.length + 3) & ~3)
			# Add NUL bytes to pad the table data to a 4-byte boundary.
			# Don't depend on f.seek() as we need to add the padding even if no
			# subsequent write follows (seek is lazy), ie. after the final table
			# in the font.
			self.file.write(b'\0' * (self.nextTableOffset - self.file.tell()))
			assert self.nextTableOffset == self.file.tell()

		if self.flavor in ("woff", "woff2"):
			self.origNextTableOffset += (entry.origLength + 3) & ~3

		self.tables[tag] = entry
		self.tableOrder.append(tag)

	def close(self):
		"""All tables must have been written to disk. Now write the
		directory.
		"""
		if self.flavor == "woff2":
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
		else:
			# SFNT and WOFF table records must be sorted in ascending order by tag
			tables = sorted(self.tables.items())
		if len(tables) != self.numTables:
			from fontTools import ttLib
			raise ttLib.TTLibError("wrong number of tables; expected %d, found %d" % (self.numTables, len(tables)))

		if self.flavor in ("woff", "woff2"):
			self.reserved = 0

			# size of uncompressed font
			self.totalSfntSize = sfntDirectorySize
			self.totalSfntSize += sfntDirectoryEntrySize * len(tables)
			for tag, entry in tables:
				self.totalSfntSize += (entry.origLength + 3) & ~3

			if self.flavor == "woff":
				self.signature = b"wOFF"

				# start calculating total size of WOFF font
				offset = woffDirectorySize + len(tables) * woffDirectoryEntrySize
				for tag, entry in tables:
					offset = offset + ((entry.length + 3) & ~3)
			else:
				self.signature = b"wOF2"

				# for each table, encode and save the data to _fontBuffer
				for tag, entry in tables:
					data = entry.data
					entry.saveData(self, data)

				# start calculating total size of WOFF2 font
				offset = woff2DirectorySize
				for tag, entry in tables:
					offset += tableEntrySize(entry)

				# update head's checkSumAdjustment
				self.writeMasterChecksum(b"")

				# compress font data
				self._fontBuffer.seek(0)
				uncompressedData = self._fontBuffer.read()
				import brotli
				compressedData = brotli.compress(uncompressedData, brotli.MODE_FONT)
				self.totalCompressedSize = len(compressedData)

				offset += self.totalCompressedSize
				offset = (offset + 3) & ~3

			# calculate offsets and lengths for any metadata and/or private data
			compressedMetaData = privData = b""
			data = self.flavorData if self.flavorData else FlavorData(flavor=self.flavor)
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
				# compress metadata using either zlib or brotli
				compressedMetaData = data.encodeData(data.metaData)
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
		if seenHead and self.flavor != "woff2":
			self.writeMasterChecksum(directory)
		self.file.seek(0)
		self.file.write(directory)

		if self.flavor == "woff2":
			# finally write WOFF2 compressed font data to disk
			self.file.write(compressedData)
			write4BytePadding(self.file)
		if self.flavor in ("woff", "woff2"):
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

		if self.DirectoryEntry != SFNTDirectoryEntry:
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
		dst = self._fontBuffer if self.flavor == "woff2" else self.file
		checksumadjustment = self._calcMasterChecksum(directory)
		# write the checksum to the file
		dst.seek(self.tables['head'].offset + 8)
		dst.write(struct.pack(">L", checksumadjustment))

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

woff2FlagsFormat = """\
		> # big endian
		flags: B  # table type and flags
"""

woff2FlagsSize = sstruct.calcsize(woff2FlagsFormat)

woff2UnknownTagFormat = """\
		> # big endian
		tag: 4s  # 4-byte tag (optional)
"""

woff2UnknownTagSize = sstruct.calcsize(woff2UnknownTagFormat)

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

class FlavorData(object):

	_flavor = None

	@property
	def flavor(self):
		return self._flavor

	@flavor.setter
	def flavor(self, value):
		if value in ('woff', 'woff2'):
			self._flavor = value
		else:
			from fontTools import ttLib
			raise ttLib.TTLibError(
				"Invalid flavor '%s'. Must be either 'woff' or 'woff2" % value)

	def __init__(self, reader=None, flavor=None):
		self.flavor = reader.flavor if reader else flavor
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
				data = self.decodeData(rawData)
				assert len(data) == reader.metaOrigLength
				self.metaData = data
			if reader.privLength:
				reader.file.seek(reader.privOffset)
				data = reader.file.read(reader.privLength)
				assert len(data) == reader.privLength
				self.privData = data

	def decodeData(self, rawData):
		if self.flavor == "woff":
			import zlib
			data = zlib.decompress(rawData)
		elif self.flavor == "woff2":
			import brotli
			data = brotli.decompress(rawData)
		return data

	def encodeData(self, data):
		if self.flavor == "woff":
			import zlib
			rawData = zlib.compress(data)
		elif self.flavor == "woff2":
			import brotli
			rawData = brotli.compress(data)
		return rawData

def write4BytePadding(file):
	"""Write NUL bytes at the end of file to pad data to a 4-byte boundary."""
	file.seek(0, 2)
	offset = file.tell()
	paddedOffset = (offset + 3) & ~3
	file.write(b'\0' * (paddedOffset - offset))

def readUInt128(file):
	""" A UIntBase128 encoded number is a sequence of bytes for which the most
	significant bit is set for all but the last byte, and clear for the last byte.
	The number itself is base 128 encoded in the lower 7 bits of each byte.
	"""
	result = 0
	length = 0
	for i in range(5):
		data = file.read(1)
		length += 1
		code, = struct.unpack(">B", data)
		# if any of the top seven bits are set then we're about to overflow
		if result & 0xFE000000:
			from fontTools import ttLib
			raise ttLib.TTLibError('UIntBase128 value exceeds 2**32-1')
		# set current value = old value times 128 bitwise-or (byte bitwise-and 127)
		result = (result << 7) | (code & 0x7f)
		# repeat until the most significant bit of byte is false
		if (code & 0x80) == 0:
			# return result plus number of bytes consumed
			return result, length
	# make sure not to exceed the size bound
	from fontTools import ttLib
	raise ttLib.TTLibError('UIntBase128-encoded sequence is longer than 5 bytes')

def UInt128Size(n):
	size = 1
	while n >= 128:
		size += 1
		n >>= 7
	return size

def packUInt128(n):
	data = b''
	size = UInt128Size(n)
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

def knownTableIndex(tag):
	for i in range(63):
		if Tag(tag) == woff2KnownTags[i]:
			return i
	return 63

def tableEntrySize(table):
	flagByte = knownTableIndex(table.tag)
	size = 1 if (flagByte & 0x3f) != 0x3f else 5
	size += UInt128Size(table.origLength)
	if table.transform:
		size += UInt128Size(table.length)
	return size

def compileGlyphData(glyfTable, indexToLocFormat=1, longAlign=True, recalcBBoxes=False, compact=True):
	""" Return a list of compiled glyph data for the table 'glyfTable'.
	If 'longAlign' is False, do not pad glyph data to 4-byte boundaries.
	If 'indexToLocFormat' is 0, pad odd-lengthed glyphs to use the 'short' loca
	version.
	"""
	dataList = []
	currentLocation = 0
	for glyphName in glyfTable.glyphOrder:
		glyph = glyfTable.glyphs[glyphName]
		if compact and not hasattr(glyph, 'data'):
			# store glyph data in 'compact' form
			glyph.compact(glyfTable, recalcBBoxes)
		glyphData = glyph.compile(glyfTable, recalcBBoxes)
		if longAlign:
			# pad glyph data to 4-byte boundary
			glyphSize = len(glyphData)
			paddedGlyphSize = (glyphSize + 3) & ~3
			glyphData += b'\0' * (paddedGlyphSize - glyphSize)
		if indexToLocFormat == 0:
			# pad odd-lengthed glyphs
			if not longAlign and len(glyphData) % 2 == 1:
				glyphData += b'\0'
			# make sure the data fits the 'short' version
			if currentLocation + len(glyphData) > 0x1FFFF:
				from fontTools import ttLib
				raise ttLib.TTLibError(
					"glyph offset exceeds the limits of 'short' loca format: 0x%05X"
					% (currentLocation + len(glyphData)))
		dataList.append(glyphData)
		currentLocation += len(glyphData)
	return dataList

def glyphLocations(glyfTable, indexToLocFormat=1):
	""" Calculate 'loca' offsets using data from 'glyfTable' and applying the
	specified 'indexToLocFormat'.
	"""
	locations = []
	currentLocation = 0
	for glyphData in compileGlyphData(glyfTable, indexToLocFormat):
		locations.append(currentLocation)
		currentLocation += len(glyphData)
	locations.append(currentLocation)
	return locations

def compileGlyf(glyfTable, indexToLocFormat=1):
	"""Return compiled 'glyf' table data using the specified 'indexToLocFormat'"""
	dataList = compileGlyphData(glyfTable, indexToLocFormat)
	return bytesjoin(dataList)

def compileLoca(glyfTable, indexToLocFormat=1):
	""" Return compiled 'loca' table using glyph data from 'glyfTable'.
	If 'indexToLocFormat' is 0, use 'short' loca version.
	"""
	locations = glyphLocations(glyfTable, indexToLocFormat)
	# use 'long' or 'short' loca version according to 'indexToLocFormat'
	if indexToLocFormat:
		locations = array.array("I", locations)
	else:
		# for the 'short' loca, divide the actual offsets by 2
		locations = array.array("H", [value >> 1 for value in locations])
	if sys.byteorder != "big":
		locations.byteswap()
	return locations.tostring()

def decompileLoca(data, indexToLocFormat=0):
	longFormat = indexToLocFormat
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
	return locations

def decompileGlyf(data, loca, lazy=True):
	last = int(loca[0])
	table = getTableClass('glyf')()
	table.glyphs = {}
	table.glyphOrder = glyphOrder = []
	for i in range(0, len(loca)-1):
		glyphName = 'glyph%s' % i
		glyphOrder.append(glyphName)
		next = int(loca[i+1])
		glyphdata = data[last:next]
		if len(glyphdata) != (next - last):
			raise ttLib.TTLibError("not enough 'glyf' table data")
		glyph = getTableModule('glyf').Glyph(glyphdata)
		table.glyphs[glyphName] = glyph
		last = next
	if len(data) - next >= 4:
		warnings.warn("too much 'glyf' table data: expected %d, received %d bytes" %
				(next, len(data)))
	if lazy is False:
		for glyph in table.glyphs.values():
			glyph.expand(table)
	return table

class WOFF2DirectoryEntry(DirectoryEntry):
	def fromFile(self, file):
		sstruct.unpack(woff2FlagsFormat, file.read(woff2FlagsSize), self)
		self.size = woff2FlagsSize
		if self.flags & 0x3F == 0x3F:
			# if bits [0..5] of the flags byte == 63, read a 4-byte arbitrary tag value
			sstruct.unpack(woff2UnknownTagFormat, file.read(woff2UnknownTagSize), self)
			self.size += woff2UnknownTagSize
		else:
			# otherwise, tag is derived from a fixed 'Known Tags' table
			self.tag = woff2KnownTags[self.flags & 0x3F]
		self.tag = Tag(self.tag)
		if self.flags & 0xC0 != 0:
			from fontTools import ttLib
			raise ttLib.TTLibError('bits 6-7 are reserved and must be 0')
		# UIntBase128 value specifying the table's length in an uncompressed font
		self.origLength, nBytes = readUInt128(file)
		self.size += nBytes
		self.transform = False
		self.length = self.origLength
		if self.tag not in ('glyf', 'loca'):
			return
		# only glyf and loca are subject to transformation
		self.transform = True
		# Optional UIntBase128 specifying the length of the 'transformed' table.
		# For simplicity, the 'transformLength' is called 'length' here.
		self.length, nBytes = readUInt128(file)
		self.size += nBytes
		# transformed loca is reconstructed as part of the glyf decoding process
		# and its length must always be 0
		if self.tag == 'loca' and self.length != 0:
			from fontTools import ttLib
			raise ttLib.TTLibError(
				"incorrect size of transformed 'loca' table: expected 0, received %d bytes"
				% (len(self.length)))

	def fromString(self, str):
		return self.fromFile(StringIO(str))

	def toString(self):
		data = struct.pack('B', self.flags)
		if (self.flags & 0x3f) == 0x3f:
			data += struct.pack('>L', self.tag)
		data += packUInt128(self.origLength)
		if self.transform:
			data += packUInt128(self.length)
		return data

	def loadData(self, reader):
		reader._fontBuffer.seek(self.offset)
		rawData = reader._fontBuffer.read(self.length)
		assert len(rawData) == self.length
		data = self.decodeData(rawData, reader)
		return data

	def saveData(self, writer, data):
		data = self.encodeData(data, writer)
		self.length = len(data)
		self.offset = writer.nextTableOffset
		writer._fontBuffer.seek(self.offset)
		writer._fontBuffer.write(data)
		writer.nextTableOffset += self.length

	def decodeData(self, rawData, reader):
		""" Return reconstructed 'glyf' and 'loca' tables. Return raw data
		if the table was not transformed.
		"""
		if not self.transform:
			return rawData

		if self.tag == 'loca':
			# there's no loca data in WOFF2, it must be recalculated from glyf
			if not hasattr(reader, 'glyfTable'):
				# make sure glyf is loaded first
				glyfEntry = reader.tables['glyf']
				glyfEntry.loadData(reader)
			# compile loca from reconstructed glyf
			table = WOFF2Loca()
			data = table.reconstruct(reader.glyfTable)
			return data

		if self.tag != 'glyf':
			from fontTools import ttLib
			raise ttLib.TTLibError("can't decode transformed '%s' table" % self.tag)

		if hasattr(reader, 'glyfTable'):
			# glyf already decoded, return compiled data
			return reader.glyfTable.compile()

		# reconstruct transformed glyf table and store it inside reader
		reader.glyfTable = table = WOFF2Glyf()
		data = table.reconstruct(rawData)

		if len(data) != self.origLength:
			from fontTools import ttLib
			raise ttLib.TTLibError(
				"reconstructed 'glyf' doesn't match original size: expected %d, found %d"
				% (self.origLength, len(data)))
		return data

	def encodeData(self, data, writer):
		""" Return transformed 'glyf' and 'loca' tables' data, or return raw data
		if the table was not transformed.
		"""
		if not self.transform:
			return data

		if self.tag == 'loca':
			# transformed loca data is null
			return b""

		if self.tag != 'glyf':
			from fontTools import ttLib
			raise ttLib.TTLibError("can't transform '%s' table" % self.tag)

		if 'loca' not in writer.tables:
			from fontTools import ttLib
			raise ttLib.TTLibError("loca must be encoded before glyf")

		loca = WOFF2Loca(writer.indexFormat)
		loca.decompile(writer.tables['loca'].data)
		writer.glyfTable = table = WOFF2Glyf()
		table.decompile(data, loca)

		print(table.__dict__)
		raise Exception('stop')

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

	def compile(self):
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

	def reconstruct(self, data):
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
			from fontTools import ttLib
			raise ttLib.TTLibError(
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

		# decompile each glyph
		self.glyphs = {}
		for i in range(numGlyphs):
			glyphName = glyphOrder[i]
			glyph = WOFF2Glyph(i, self)
			self.glyphs[glyphName] = glyph

		# return compiled table data
		return self.compile()

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
				from fontTools import ttLib
				raise ttLib.TTLibError("not enough 'glyf' table data")
			glyph = getTableModule('glyf').Glyph(glyphdata)
			self.glyphs[glyphName] = glyph
			last = next
		if len(data) - next >= 4:
			from fontTools import ttLib
			raise ttLib.TTLibError(
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
					from fontTools import ttLib
					raise ttLib.TTLibError(
						"glyph offset exceeds the limits of 'short' loca format: 0x%05X"
						% (currentLocation + len(glyphData)))
			dataList.append(glyphData)
			currentLocation += len(glyphData)
		return dataList

	def compile(self, recalcBBoxes=False, compact=True):
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
			raise ttLib.TTLibError('no bbox values for composite glyph %d' % index)
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
			raise ttLib.TTLibError("not enough 'flagStream' data")
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
