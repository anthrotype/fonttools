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
from fontTools.ttLib import (TTFont, getSearchRange, TTLibError, getTableModule,
	getTableClass)
from fontTools.ttLib.tables import ttProgram
import sys
import array
import struct
from collections import OrderedDict
from fontTools.misc import sstruct
from fontTools.misc.arrayTools import calcIntBounds

haveBrotli = False
try:
	import brotli
	haveBrotli = True
except ImportError:
	pass


class SFNTReader(object):

	flavor = None

	def __new__(cls, file, checkChecksums=1, fontNumber=-1):
		if cls is SFNTReader:
			sfntVersion = Tag(file.read(4))
			file.seek(0)
			if sfntVersion == "wOF2":
				if haveBrotli:
					print('return new WOFF2Reader object')
					return super(SFNTReader, cls).__new__(WOFF2Reader)
				else:
					print('The WOFF2 encoder requires the Brotli Python extension:\n'
						  'https://github.com/google/brotli', file=sys.stderr)
					raise ImportError("No module named brotli")
			elif sfntVersion == "wOFF":
				print('return new WOFFReader object')
				return super(SFNTReader, cls).__new__(WOFFReader)
			elif sfntVersion == "ttcf":
				print('return new SFNTCollectionReader object')
				return super(SFNTReader, cls).__new__(SFNTCollectionReader)
		print('return new %s object' % cls.__name__)
		return super(SFNTReader, cls).__new__(cls)

	def __init__(self, file, checkChecksums=1, fontNumber=-1):
		self.file = file
		self.checkChecksums = checkChecksums
		self.fontNumber = fontNumber
		self.flavorData = None

		self._setDirectoryFormat()
		self.readDirectory()

	def _setDirectoryFormat(self):
		self.directoryFormat = sfntDirectoryFormat
		self.directorySize = sfntDirectorySize
		self.DirectoryEntry = SFNTDirectoryEntry

	def readDirectory(self):
		data = self.file.read(self.directorySize)
		if len(data) != self.directorySize:
			raise TTLibError("Not a TrueType or OpenType font (not enough data)")
		sstruct.unpack(self.directoryFormat, data, self)
		self.sfntVersion = Tag(self.sfntVersion)
		if self.sfntVersion not in ("\x00\x01\x00\x00", "OTTO", "true"):
			raise TTLibError("Not a TrueType or OpenType font (bad sfntVersion)")
		self._readDirectoryEntries()

	def _readDirectoryEntries(self):
		self.tables = {}
		for i in range(self.numTables):
			entry = self.DirectoryEntry()
			entry.fromFile(self.file)
			self.tables[Tag(entry.tag)] = entry

	def has_key(self, tag):
		return tag in self.tables

	__contains__ = has_key

	def keys(self):
		return self.tables.keys()

	def __getitem__(self, tag):
		"""Fetch the raw table data."""
		entry = self.tables[Tag(tag)]
		data = entry.loadData(self.file)
		if self.checkChecksums:
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

	@property
	def tableOrder(self):
		"""Return list of table tags sorted by offset."""
		return sorted(self.tables.keys(), key=lambda t: self.tables[t].offset)


class SFNTCollectionReader(SFNTReader):

	flavor = "ttc"

	def __init__(self, file, checkChecksums=1, fontNumber=-1):
		self.file = file
		self.checkChecksums = checkChecksums
		self.flavorData = None

		self._setDirectoryFormat()
		self._readCollectionHeader()

		if fontNumber != -1:
			self.seekOffsetTable(fontNumber)
		else:
			raise NotImplementedError

		self.readDirectory()

	def seekOffsetTable(self, fontNumber):
		"""Move current position to the offset table of font 'fontNumber'."""
		if not 0 <= fontNumber < self.numFonts:
			raise TTLibError("specify a font number between 0 and %d (inclusive)" % (self.numFonts - 1))
		self.file.seek(self.offsetTables[fontNumber])

	def _readCollectionHeader(self):
		if Tag(self.file.read(4)) != "ttcf":
			raise TTLibError("Not a Font Collection (bad TTCTag)")
		self.file.seek(0)
		ttcHeaderData = self.file.read(ttcHeaderSize)
		if len(ttcHeaderData) != ttcHeaderSize:
			TTLibError("Not a Font Collection font (not enough data)")
		sstruct.unpack(ttcHeaderFormat, ttcHeaderData, self)
		if not (self.Version == 0x00010000 or self.Version == 0x00020000):
			raise TTLibError("unrecognized TTC version 0x%08x" % self.Version)
		offsetTableFormat = ">%dL" % self.numFonts
		offsetTableSize = struct.calcsize(offsetTableFormat)
		offsetTableData = self.file.read(offsetTableSize)
		if len(offsetTableData) != offsetTableSize:
			raise TTLibError("Not a Font Collection (not enough data)")
		self.offsetTables = struct.unpack(offsetTableFormat, offsetTableData)
		if self.Version == 0x00020000:
			pass  # ignoring version 2.0 signatures


class WOFFReader(SFNTReader):

	flavor = "woff"
	signature = b"wOFF"

	def __init__(self, file, checkChecksums=1, fontNumber=-1):
		signature = Tag(file.read(4))
		file.seek(0)
		if signature != self.signature:
			raise TTLibError("Not a %s font (bad signature)" % self.flavor.upper())

		super(WOFFReader, self).__init__(file, checkChecksums, fontNumber)

		self.file.seek(0, 2)
		if self.length != self.file.tell():
			raise TTLibError("reported 'length' doesn't match the actual file size")

		self._readFlavorData()

	def _setDirectoryFormat(self):
		self.directoryFormat = woffDirectoryFormat
		self.directorySize = woffDirectorySize
		self.DirectoryEntry = WOFFDirectoryEntry

	def _readFlavorData(self):
		self.flavorData = WOFFFlavorData(self)


class WOFF2Reader(WOFFReader):

	flavor = "woff2"
	signature = b"wOF2"

	def __init__(self, file, checkChecksums=1, fontNumber=-1):
		super(WOFF2Reader, self).__init__(file, checkChecksums, fontNumber)
		# decompress font data
		self.file.seek(self.compressedDataOffset)
		compressedData = self.file.read(self.totalCompressedSize)
		import brotli
		decompressedData = brotli.decompress(compressedData)
		totalUncompressedSize = sum([entry.length for entry in self.tables.values()])
		if len(decompressedData) != totalUncompressedSize:
			raise TTLibError(
				'unexpected size for decompressed font data: expected %d, found %d'
				% (totalUncompressedSize, len(decompressedData)))
		# write decompressed data to temporary buffer
		self.transformBuffer = StringIO(decompressedData)

	def _setDirectoryFormat(self):
		self.directoryFormat = woff2DirectoryFormat
		self.directorySize = woff2DirectorySize
		self.DirectoryEntry = WOFF2DirectoryEntry

	def _readDirectoryEntries(self):
		self.tables = {}
		# calculate offsets to individual tables inside 'transformBuffer'
		offset = 0
		for i in range(self.numTables):
			entry = self.DirectoryEntry()
			entry.fromFile(self.file)
			entry.offset = offset
			self.tables[Tag(entry.tag)] = entry
			offset += entry.length
		# compressed font data starts at the end of variable-length table directory
		self.compressedDataOffset = self.file.tell()

	def _readFlavorData(self):
		self.flavorData = WOFF2FlavorData(self)

	def __getitem__(self, tag):
		"""Fetch the raw table data. Reconstruct transformed tables."""
		tag = Tag(tag)
		entry = self.tables[tag]
		rawData = entry.loadData(self.transformBuffer)
		if tag not in woff2TransformedTableTags:
			return rawData
		if hasattr(entry, 'data'):
			# already reconstructed
			return entry.data
		data = self.reconstructTable(tag, rawData)
		if tag == 'loca' and len(data) != entry.origLength:
			raise TTLibError(
				"reconstructed 'loca' table doesn't match original size: expected %d, found %d"
				% (entry.origLength, len(data)))
		entry.data = data
		return entry.data

	def reconstructTable(self, tag, rawData):
		"""Reconstruct 'glyf' or 'loca' tables from transformed 'rawData'."""
		if tag not in woff2TransformedTableTags:
			raise TTLibError("Transform for table '%s' is unknown" % tag)
		if tag == 'glyf':
			# reconstruct both glyf and loca
			self.glyfTable = WOFF2GlyfTable()
			data = self.glyfTable.reconstruct(rawData)
		elif tag == 'loca':
			assert len(rawData) == 0, "expected 0, received %d bytes" % len(rawData)
			if not hasattr(self, 'glyfTable'):
				# make sure glyf is loaded first
				self['glyf']
			data = self.glyfTable.getLocaData()
		else:
			raise NotImplementedError
		return data


class SFNTWriter(object):

	flavor = None

	def __new__(cls, file, numTables, sfntVersion="\000\001\000\000",
		        flavor=None, flavorData=None):
		if cls is SFNTWriter:
			if flavor == "woff2":
				if haveBrotli:
					print('return new WOFF2Writer object')
					return super(SFNTWriter, cls).__new__(WOFF2Writer)
				else:
					print('The WOFF2 encoder requires the Brotli Python extension:\n'
						  'https://github.com/google/brotli', file=sys.stderr)
					raise ImportError("No module named brotli")
			elif flavor == "woff":
				print('return new WOFFWriter object')
				return super(SFNTWriter, cls).__new__(WOFFWriter)
			elif flavor == "ttc":
				print('return new SFNTCollectionWriter object')
				raise NotImplementedError
		print('return new %s object' % cls.__name__)
		return super(SFNTWriter, cls).__new__(cls)

	def __init__(self, file, numTables, sfntVersion="\000\001\000\000",
		         flavor=None, flavorData=None):
		self.file = file
		self.numTables = numTables
		self.sfntVersion = Tag(sfntVersion)
		self.flavorData = flavorData

		self.tables = OrderedDict()  # keep track of insertion order

		self._setDirectoryFormat()
		self._seekFirstTable()

	def _setDirectoryFormat(self):
		self.directoryFormat = sfntDirectoryFormat
		self.directorySize = sfntDirectorySize
		self.DirectoryEntry = SFNTDirectoryEntry

		self.searchRange, self.entrySelector, self.rangeShift = getSearchRange(self.numTables, 16)

	def _seekFirstTable(self):
		self.nextTableOffset = self.directorySize + self.numTables * self.DirectoryEntry.formatSize
		# clear out directory area
		self.file.seek(self.nextTableOffset)
		# make sure we're actually where we want to be. (old cStringIO bug)
		self.file.write(b'\0' * (self.nextTableOffset - self.file.tell()))

	def __setitem__(self, tag, data):
		"""Write raw table data to disk."""
		if tag in self.tables:
			raise TTLibError("cannot rewrite '%s' table" % tag)

		entry = self.DirectoryEntry()
		entry.tag = tag
		if tag == 'head':
			entry.checkSum = calcChecksum(data[:8] + b'\0\0\0\0' + data[12:])
			self.headTable = data
			entry.uncompressed = True
		else:
			entry.checkSum = calcChecksum(data)
		self._writeTable(entry, data)

		self.tables[tag] = entry

	def _writeTable(self, entry, data):
		entry.offset = self.nextTableOffset
		entry.saveData(self.file, data)

		self.nextTableOffset = self.nextTableOffset + ((entry.length + 3) & ~3)
		# Add NUL bytes to pad the table data to a 4-byte boundary.
		# Don't depend on f.seek() as we need to add the padding even if no
		# subsequent write follows (seek is lazy), ie. after the final table
		# in the font.
		self.file.write(b'\0' * (self.nextTableOffset - self.file.tell()))
		assert self.nextTableOffset == self.file.tell()

	def close(self):
		"""All tables must have been written to disk. Now write the directory."""
		self._assertNumTables()

		# SFNT table directory must be sorted alphabetically by tag
		tables = sorted(self.tables.items())
		directory = sstruct.pack(self.directoryFormat, self)
		seenHead = 0
		for tag, entry in tables:
			if tag == "head":
				seenHead = 1
			directory = directory + entry.toString()
		if seenHead:
			self._writeMasterChecksum(directory)
		self.file.seek(0)
		self.file.write(directory)

	def _assertNumTables(self):
		if len(self.tables) != self.numTables:
			raise TTLibError("wrong number of tables; expected %d, found %d" % (
				self.numTables, len(self.tables)))

	def _writeMasterChecksum(self, directory):
		checksumadjustment = self._calcMasterChecksum(directory)
		# write the checksum to the file
		self.file.seek(self.tables['head'].offset + 8)
		self.file.write(struct.pack(">L", checksumadjustment))

	def _calcMasterChecksum(self, directory):
		# calculate checkSumAdjustment
		checksums = []
		for entry in self.tables.values():
			checksums.append(entry.checkSum)

		directory_end = sfntDirectorySize + len(self.tables) * sfntDirectoryEntrySize
		assert directory_end == len(directory)

		checksums.append(calcChecksum(directory))
		checksum = sum(checksums) & 0xffffffff
		# BiboAfba!
		checksumadjustment = (0xB1B0AFBA - checksum) & 0xffffffff
		return checksumadjustment


class WOFFWriter(SFNTWriter):

	flavor = 'woff'

	def __init__(self, file, numTables, sfntVersion="\000\001\000\000",
		         flavor=None, flavorData=None):
		super(WOFFWriter, self).__init__(file, numTables, sfntVersion)

		self.flavorData = self._newFlavorData()
		if flavorData is not None:
			if not isinstance(flavorData, WOFFFlavorData):
				raise TypeError("expected WOFFFlavorData, found %s" % type(flavorData))
			# copy instead of replacing flavorData, to exchange between WOFF/WOFF2
			self.flavorData.__dict__.update(flavorData.__dict__)

	def _setDirectoryFormat(self):
		self.directoryFormat = woffDirectoryFormat
		self.directorySize = woffDirectorySize
		self.DirectoryEntry = WOFFDirectoryEntry

	def _newFlavorData(self):
		return WOFFFlavorData()

	def close(self):
		self._assertNumTables()

		self.signature = b"wOFF"
		self.reserved = 0
		self.totalSfntSize = self._calcSftnSize()
		self.majorVersion, self.minorVersion = self._getVersion()
		self.length = self._calcTotalSize()

		# write table directory
		super(WOFFWriter, self).close()

		self._writeFlavorData()

	def _calcSftnSize(self):
		# calculate total size of uncompressed SFNT font
		size = sfntDirectorySize + sfntDirectoryEntrySize * len(self.tables)
		for entry in self.tables.values():
			size += (entry.origLength + 3) & ~3
		return size

	def _getVersion(self):
		# get (majorVersion, minorVersion) for WOFF font
		data = self.flavorData
		if data.majorVersion is not None and data.minorVersion is not None:
			return data.majorVersion, data.minorVersion
		else:
			# if None, return 'fontRevision' from 'head' table
			if hasattr(self, 'headTable'):
				return struct.unpack(">HH", self.headTable[4:8])
			else:
				return 0, 0

	def _calcTotalSize(self):
		# calculate total size of WOFF font, including any meta or private data
		offset = self.directorySize + self.DirectoryEntry.formatSize * len(self.tables)
		for entry in self.tables.values():
			offset += (entry.length + 3) & ~3
		offset = self._calcFlavorDataOffsetsAndSize(offset)
		return offset

	def _calcFlavorDataOffsetsAndSize(self, offset):
		# calculate offsets and lengths for any meta or private data
		data = self.flavorData
		if data.metaData:
			self.metaOrigLength = len(data.metaData)
			self.metaOffset = offset
			# compress metaData using zlib (WOFF) or brotli (WOFF2)
			self.compressedMetaData = data.encodeData(data.metaData)
			self.metaLength = len(self.compressedMetaData)
			offset += self.metaLength
		else:
			self.metaOffset = self.metaLength = self.metaOrigLength = 0
			self.compressedMetaData = b""
		if data.privData:
			# make sure private data is padded to 4-byte boundary
			offset = (offset + 3) & ~3
			self.privOffset = offset
			self.privLength = len(data.privData)
			offset += self.privLength
		else:
			self.privOffset = self.privLength = 0
		return offset

	def _writeFlavorData(self):
		# write any metadata and/or private data to disk using appropriate padding
		compressedMetaData = self.compressedMetaData
		privData = self.flavorData.privData
		if compressedMetaData and privData:
			compressedMetaData = padData(compressedMetaData)
		if compressedMetaData:
			self.file.seek(self.metaOffset)
			assert self.file.tell() == self.metaOffset
			self.file.write(compressedMetaData)
		if privData:
			self.file.seek(self.privOffset)
			assert self.file.tell() == self.privOffset
			self.file.write(privData)

	def _calcMasterChecksum(self, directory):
		# create a dummy SFNT directory before calculating the checkSumAdjustment
		directory = self._makeDummySFNTDirectory()
		return super(WOFFWriter, self)._calcMasterChecksum(directory)

	def _makeDummySFNTDirectory(self):
		# compute 'original' SFNT table offsets
		offset = sfntDirectorySize + sfntDirectoryEntrySize * len(self.tables)
		for entry in self.tables.values():
			entry.origOffset = offset
			offset += (entry.origLength + 3) & ~3
		# make dummy SFNT table directory
		self.searchRange, self.entrySelector, self.rangeShift = getSearchRange(
			len(self.tables), 16)
		directory = sstruct.pack(sfntDirectoryFormat, self)
		for tag, entry in sorted(self.tables.items()):
			assert hasattr(entry, 'origLength')
			sfntEntry = SFNTDirectoryEntry()
			sfntEntry.tag = entry.tag
			sfntEntry.checkSum = entry.checkSum
			sfntEntry.offset = entry.origOffset
			sfntEntry.length = entry.origLength
			directory = directory + sfntEntry.toString()
		return directory


class WOFF2Writer(WOFFWriter):

	flavor = 'woff2'

	def _setDirectoryFormat(self):
		self.directoryFormat = woff2DirectoryFormat
		self.directorySize = woff2DirectorySize
		self.DirectoryEntry = WOFF2DirectoryEntry

	def _newFlavorData(self):
		return WOFF2FlavorData()

	def _seekFirstTable(self):
		# initialise empty 'transformBuffer'
		self.nextTableOffset = 0
		self.transformBuffer = StringIO()

	def __setitem__(self, tag, data):
		"""Associate new entry named 'tag' with raw table data."""
		super(WOFF2Writer, self).__setitem__(tag, data)
		entry = self.tables[tag]
		entry.flags = getKnownTagIndex(entry.tag)
		entry.origLength = len(data)

	def _writeTable(self, entry, data):
		# WOFF2 table data are written to disk only on close(), after all tags
		# have been specified, and glyf and loca can be transformed
		entry.data = data

	def close(self):
		""" All tags must have been specified. Now transform the 'glyf' and 'loca'
		tables, compress the table data, and write directory and table data to disk.
		Optionally write any metadata and/or private data.
		"""
		self._assertNumTables()

		# to pass the legacy OpenType Sanitiser currently included in browsers,
		# we must sort the table directory and data alphabetically by tag.
		# See:
		# https://github.com/google/woff2/pull/3
		# https://lists.w3.org/Archives/Public/public-webfonts-wg/2015Mar/0000.html
		# TODO(user): change to match spec once browsers are on newer OTS
		self.tables = OrderedDict(sorted(self.tables.items(), key=lambda i: i[0]))

		# write table data to transformBuffer
		for tag, entry in self.tables.items():
			data = entry.data
			if tag in woff2TransformedTableTags:
				# transform glyf and loca tables
				data = self.transformTable(tag, data)
			entry.offset = self.nextTableOffset
			entry.saveData(self.transformBuffer, data)
			self.nextTableOffset += entry.length

		self._writeMasterChecksum()

		# compress font data with Brotli
		self.transformBuffer.seek(0)
		uncompressedData = self.transformBuffer.read()
		import brotli
		compressedData = brotli.compress(uncompressedData, brotli.MODE_FONT)

		self.signature = b"wOF2"
		self.reserved = 0
		self.totalSfntSize = self._calcSftnSize()
		self.totalCompressedSize = len(compressedData)
		self.length = self._calcTotalSize()
		self.majorVersion, self.minorVersion = self._getVersion()

		directory = sstruct.pack(self.directoryFormat, self)
		for entry in self.tables.values():
			directory = directory + entry.toString()
		self.file.seek(0)
		fontData = padData(directory + compressedData)
		self.file.write(fontData)

		self._writeFlavorData()

	def _calcTotalSize(self):
		# calculate total size of WOFF2 font, including any meta- or private data
		offset = self.directorySize
		for entry in self.tables.values():
			offset += len(entry.toString())
		offset += self.totalCompressedSize
		offset = (offset + 3) & ~3
		offset = self._calcFlavorDataOffsetsAndSize(offset)
		return offset

	def _writeMasterChecksum(self):
		checksumadjustment = self._calcMasterChecksum(b"")
		# write the checksum to the transformBuffer (not to file!)
		self.transformBuffer.seek(self.tables['head'].offset + 8)
		self.transformBuffer.write(struct.pack(">L", checksumadjustment))

	def transformTable(self, tag, data):
		"""Transform 'glyf' or 'loca' table data."""
		if tag not in woff2TransformedTableTags:
			raise TTLibError("Transform for table '%s' is unknown" % tag)
		if tag == "loca":
			data = b""
		elif tag == "glyf":
			indexFormat, = struct.unpack(">H", self.tables['head'].data[50:52])
			numGlyphs, = struct.unpack(">H", self.tables['maxp'].data[4:6])
			glyfTable = WOFF2GlyfTable()
			glyfTable.setLocaData(self.tables['loca'].data, indexFormat, numGlyphs)
			data = glyfTable.transform(data)
		else:
			raise NotImplementedError
		return data


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
		data = self.decodeData(data)
		return data

	def saveData(self, file, data):
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
			return data
		else:
			return compressedData


class WOFFFlavorData(object):

	flavor = "woff"

	def __init__(self, reader=None):
		self.majorVersion = None
		self.minorVersion = None
		self.metaData = b""
		self.privData = b""
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
		import zlib
		return zlib.decompress(rawData)

	def encodeData(self, data):
		import zlib
		return zlib.compress(data)


class WOFF2FlavorData(WOFFFlavorData):

	flavor = "woff2"

	def decodeData(self, rawData):
		import brotli
		return brotli.decompress(rawData)

	def encodeData(self, data):
		import brotli
		return brotli.compress(data)


def calcChecksum(data):
	"""Calculate the checksum for an arbitrary block of data.
	Optionally takes a 'start' argument, which allows you to
	calculate a checksum in chunks by feeding it a previous
	result.
	
	If the data length is not a multiple of four, it assumes
	it is to be padded with null byte. 

		>>> print(calcChecksum(b"abcd"))
		1633837924
		>>> print(calcChecksum(b"abcdxyz"))
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


def woff2NormaliseFont(ttFont):
	""" The WOFF 2.0 conversion is guaranteed to be lossless in a bitwise sense
	only for 'normalised' font files. Normalisation occurs before any transforms,
	and involves:
		- removing the DSIG table, since the encoding process can invalidate it;
		- setting bit 11 of head 'flags' field to indicate that the font has
		  undergone a 'lossless modifying transform'.
	For TrueType-flavoured OpenType fonts, normalisation also involves padding
	glyph offsets to multiple of 4 bytes.
	"""
	if "DSIG" in ttFont:
		del ttFont["DSIG"]
		ttFont['head'].flags |= 1 << 11

	# The notion of "nominal size" has been removed from the WOFF2 Specification,
	# but as of today (15 April 2015) most decoders still expects padded data.
	# TODO(user): delete next block once glyph padding is no longer required
	if ttFont.sfntVersion == '\x00\x01\x00\x00':
		# don't be lazy so that glyph data is 'expanded' on decompile
		ttFont.lazy = False
		# decompile glyf table to perform padding normalisation upon compile
		if not ttFont.isLoaded('glyf'):
			ttFont['glyf']


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


def getKnownTagIndex(tag):
	"""Return index of 'tag' in woff2KnownTags list. Return 63 if not found."""
	for i in range(len(woff2KnownTags)):
		if tag == woff2KnownTags[i]:
			return i
	return 0x3F


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
		self.origLength, data = unpackBase128(data)
		self.length = self.origLength
		if self.tag in woff2TransformedTableTags:
			self.length, data = unpackBase128(data)
			if self.tag == 'loca' and self.length != 0:
				raise TTLibError(
					"the transformLength of the loca table must be 0")
		# return left over data
		return data

	def toString(self):
		data = bytechr(self.flags)
		if (self.flags & 0x3f) == 0x3f:
			data += struct.pack('>4s', self.tag)
		data += packBase128(self.origLength)
		if self.tag in woff2TransformedTableTags:
			data += packBase128(self.length)
		return data


class WOFF2GlyfTable(getTableClass('glyf')):
	"""Decoder/encoder for WOFF2 'glyf' table transforms."""

	def __init__(self):
		self.tableTag = Tag('glyf')
		self.ttFont = TTFont(flavor="woff2", recalcBBoxes=False)
		self.ttFont['head'] = getTableClass('head')()
		self.ttFont['maxp'] = getTableClass('maxp')()
		self.ttFont['loca'] = getTableClass('loca')()

	def reconstruct(self, transformedGlyfData):
		""" Convert transformed 'glyf' table data to SFNT 'glyf' table data.
		Decompile the resulting 'loca' table data.
		"""
		data = transformedGlyfData
		inputDataSize = len(data)

		dummy, data = sstruct.unpack2(woff2GlyfTableFormat, data, self)
		numGlyphs = self.numGlyphs
		substreamOffset = woff2GlyfTableFormatSize

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

		if substreamOffset != inputDataSize:
			raise TTLibError(
				"incorrect size of transformed 'glyf' table: expected %d, received %d bytes"
				% (substreamOffset, inputDataSize))

		bboxBitmapSize = ((numGlyphs + 31) >> 5) << 2
		bboxBitmap = combinedBboxStream[:bboxBitmapSize]
		self.bboxBitmap = array.array('B', bboxBitmap)
		self.bboxStream = combinedBboxStream[bboxBitmapSize:]

		self.nContourStream = array.array("h", self.nContourStream)
		if sys.byteorder != "big":
			self.nContourStream.byteswap()
		assert len(self.nContourStream) == numGlyphs

		self.glyphOrder = glyphOrder = []
		for glyphID in range(numGlyphs):
			glyphName = "glyph%d" % glyphID
			glyphOrder.append(glyphName)
		self.ttFont.setGlyphOrder(glyphOrder)

		self.glyphs = {}
		for glyphID, glyphName in enumerate(glyphOrder):
			glyph = self._decodeGlyph(glyphID)
			self.glyphs[glyphName] = glyph

		glyfData = self.compile(self.ttFont)
		return glyfData

	def _decodeGlyph(self, glyphID):
		glyph = getTableModule('glyf').Glyph()
		glyph.numberOfContours = self.nContourStream[glyphID]
		if glyph.numberOfContours == 0:
			return glyph
		elif glyph.isComposite():
			self._decodeComponents(glyph)
		else:
			self._decodeCoordinates(glyph)
		self._decodeBBox(glyphID, glyph)
		return glyph

	def _decodeComponents(self, glyph):
		data = self.compositeStream
		glyph.components = []
		more = 1
		haveInstructions = 0
		while more:
			component = getTableModule('glyf').GlyphComponent()
			more, haveInstr, data = component.decompile(data, self)
			haveInstructions = haveInstructions | haveInstr
			glyph.components.append(component)
		self.compositeStream = data
		if haveInstructions:
			self._decodeInstructions(glyph)

	def _decodeCoordinates(self, glyph):
		data = self.nPointsStream
		endPtsOfContours = []
		endPoint = -1
		for i in range(glyph.numberOfContours):
			ptsOfContour, data = unpack255UShort(data)
			endPoint += ptsOfContour
			endPtsOfContours.append(endPoint)
		glyph.endPtsOfContours = endPtsOfContours
		self.nPointsStream = data
		self._decodeTriplets(glyph)
		self._decodeInstructions(glyph)

	def _decodeInstructions(self, glyph):
		glyphStream = self.glyphStream
		instructionStream = self.instructionStream
		instructionLength, glyphStream = unpack255UShort(glyphStream)
		glyph.program = ttProgram.Program()
		glyph.program.fromBytecode(instructionStream[:instructionLength])
		self.glyphStream = glyphStream
		self.instructionStream = instructionStream[instructionLength:]

	def _decodeBBox(self, glyphID, glyph):
		haveBBox = bool(self.bboxBitmap[glyphID >> 3] & (0x80 >> (glyphID & 7)))
		if glyph.isComposite() and not haveBBox:
			raise TTLibError('no bbox values for composite glyph %d' % glyphID)
		if haveBBox:
			dummy, self.bboxStream = sstruct.unpack2(bboxFormat, self.bboxStream, glyph)
		else:
			glyph.recalcBounds(self)

	def _decodeTriplets(self, glyph):

		def withSign(flag, baseval):
			assert 0 <= baseval and baseval < 65536, 'integer overflow'
			return baseval if flag & 1 else -baseval

		nPoints = glyph.endPtsOfContours[-1] + 1
		flagSize = nPoints
		if flagSize > len(self.flagStream):
			raise TTLibError("not enough 'flagStream' data")
		flagsData = self.flagStream[:flagSize]
		self.flagStream = self.flagStream[flagSize:]
		flags = array.array('B', flagsData)

		triplets = array.array('B', self.glyphStream)
		nTriplets = len(triplets)
		assert nPoints <= nTriplets

		x = 0
		y = 0
		glyph.coordinates = getTableModule('glyf').GlyphCoordinates.zeros(nPoints)
		glyph.flags = array.array("B")
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
			glyph.coordinates[i] = (x, y)
			glyph.flags.append(int(onCurve))
		bytesConsumed = tripletIndex
		self.glyphStream = self.glyphStream[bytesConsumed:]

	def getLocaData(self):
		""" Return compiled 'loca' table data (must be run after 'reconstruct'
		method).
		"""
		locaTable = self.ttFont['loca']
		assert hasattr(locaTable, 'locations') and hasattr(self, 'indexFormat'), \
			"'getLocaData' must be run after 'reconstruct' method"
		locations = locaTable.locations
		indexFormat = self.indexFormat
		if indexFormat == 0:
			if max(locations) >= 0x20000:
				raise TTLibError("indexFormat is 0 but local offsets > 0x20000")
			if not all(l % 2 == 0 for l in locations):
				raise TTLibError("indexFormat is 0 but local offsets not multiples of 2")
			offsetArray = array.array("H")
			for i in range(len(locations)):
				offsetArray.append(locations[i] // 2)
		else:
			offsetArray = array.array("I", locations)
		if sys.byteorder != "big":
			offsetArray.byteswap()
		return offsetArray.tostring()

	def setLocaData(self, locaData, indexFormat, numGlyphs):
		""" Decompile 'loca' table data using the specified 'indexFormat' and
		'numGlyphs' (must be run before 'transform' method).
		"""
		self.indexFormat = self.ttFont['head'].indexToLocFormat = indexFormat
		self.numGlyphs = self.ttFont['maxp'].numGlyphs = numGlyphs
		self.ttFont['loca'].decompile(locaData, self.ttFont)

	def transform(self, glyfData):
		""" Convert the SFNT 'glyf' table data to WOFF2 transformed 'glyf' data. """
		glyphOrder = ["glyph%d" % i for i in range(self.numGlyphs)]
		self.ttFont.setGlyphOrder(glyphOrder)
		self.ttFont.lazy = False

		self.decompile(glyfData, self.ttFont)

		self.nContourStream = b""
		self.nPointsStream = b""
		self.flagStream = b""
		self.glyphStream = b""
		self.compositeStream = b""
		self.bboxStream = b""
		self.instructionStream = b""
		bboxBitmapSize = ((self.numGlyphs + 31) >> 5) << 2
		self.bboxBitmap = array.array('B', [0]*bboxBitmapSize)

		for glyphID in range(self.numGlyphs):
			self._encodeGlyph(glyphID)

		self.bboxStream = self.bboxBitmap.tostring() + self.bboxStream

		self.version = 0

		self.nContourStreamSize = len(self.nContourStream)
		self.nPointsStreamSize = len(self.nPointsStream)
		self.flagStreamSize = len(self.flagStream)
		self.glyphStreamSize = len(self.glyphStream)
		self.compositeStreamSize = len(self.compositeStream)
		self.bboxStreamSize = len(self.bboxStream)
		self.instructionStreamSize = len(self.instructionStream)

		transfomedGlyfData = sstruct.pack(woff2GlyfTableFormat, self) + \
			self.nContourStream + self.nPointsStream + self.flagStream + \
			self.glyphStream + self.compositeStream + self.bboxStream + \
			self.instructionStream
		return transfomedGlyfData

	def _encodeGlyph(self, glyphID):
		glyphName = self.getGlyphName(glyphID)
		glyph = self.glyphs[glyphName]
		self.nContourStream += struct.pack(">h", glyph.numberOfContours)
		if glyph.numberOfContours == 0:
			return
		elif glyph.isComposite():
			self._encodeComponents(glyph)
		else:
			self._encodeCoordinates(glyph)
		self._encodeBBox(glyphID, glyph)

	def _encodeComponents(self, glyph):
		lastcomponent = len(glyph.components) - 1
		more = 1
		haveInstructions = 0
		for i in range(len(glyph.components)):
			if i == lastcomponent:
				haveInstructions = hasattr(glyph, "program")
				more = 0
			component = glyph.components[i]
			self.compositeStream += component.compile(more, haveInstructions, self)
		if haveInstructions:
			self._encodeInstructions(glyph)

	def _encodeCoordinates(self, glyph):
		lastEndPoint = -1
		for endPoint in glyph.endPtsOfContours:
			ptsOfContour = endPoint - lastEndPoint
			self.nPointsStream += pack255UShort(ptsOfContour)
			lastEndPoint = endPoint
		self._encodeTriplets(glyph)
		self._encodeInstructions(glyph)

	def _encodeInstructions(self, glyph):
		instructions = glyph.program.getBytecode()
		self.glyphStream += pack255UShort(len(instructions))
		self.instructionStream += instructions

	def _encodeBBox(self, glyphID, glyph):
		assert glyph.numberOfContours != 0, "empty glyph has no bbox"
		if not glyph.isComposite():
			# for simple glyphs, compare the encoded bounding box info with the calculated
			# values, and if they match omit the bounding box info
			currentBBox = glyph.xMin, glyph.yMin, glyph.xMax, glyph.yMax
			calculatedBBox = calcIntBounds(glyph.coordinates)
			if currentBBox == calculatedBBox:
				return
		self.bboxBitmap[glyphID >> 3] |= 0x80 >> (glyphID & 7)
		self.bboxStream += sstruct.pack(bboxFormat, glyph)

	def _encodeTriplets(self, glyph):
		assert len(glyph.coordinates) == len(glyph.flags)
		coordinates = glyph.coordinates.copy()
		coordinates.absoluteToRelative()

		flags = array.array('B')
		triplets = array.array('B')
		for i in range(len(coordinates)):
			onCurve = glyph.flags[i]
			x, y = coordinates[i]
			absX = abs(x)
			absY = abs(y)
			onCurveBit = 0 if onCurve else 128
			xSignBit = 0 if (x < 0) else 1
			ySignBit = 0 if (y < 0) else 1
			xySignBits = xSignBit + 2 * ySignBit

			if x == 0 and absY < 1280:
				flags.append(onCurveBit + ((absY & 0xf00) >> 7) + ySignBit)
				triplets.append(absY & 0xff)
			elif y == 0 and absX < 1280:
				flags.append(onCurveBit + 10 + ((absX & 0xf00) >> 7) + xSignBit)
				triplets.append(absX & 0xff)
			elif absX < 65 and absY < 65:
				flags.append(onCurveBit + 20 + ((absX - 1) & 0x30) + (((absY - 1) & 0x30) >> 2) + xySignBits)
				triplets.append((((absX - 1) & 0xf) << 4) | ((absY - 1) & 0xf))
			elif absX < 769 and absY < 769:
				flags.append(onCurveBit + 84 + 12 * (((absX - 1) & 0x300) >> 8) + (((absY - 1) & 0x300) >> 6) + xySignBits)
				triplets.append((absX - 1) & 0xff)
				triplets.append((absY - 1) & 0xff)
			elif absX < 4096 and absY < 4096:
				flags.append(onCurveBit + 120 + xySignBits)
				triplets.append(absX >> 4)
				triplets.append(((absX & 0xf) << 4) | (absY >> 8))
				triplets.append(absY & 0xff)
			else:
				flags.append(onCurveBit + 124 + xySignBits)
				triplets.append(absX >> 8)
				triplets.append(absX & 0xff)
				triplets.append(absY >> 8)
				triplets.append(absY & 0xff)

		self.flagStream += flags.tostring()
		self.glyphStream += triplets.tostring()


def unpackBase128(data):
	r""" Read one to five bytes from UIntBase128-encoded input string, and return
	a tuple containing the decoded integer plus any leftover data.

	>>> unpackBase128(b'\x3f\x00\x00') == (63, b"\x00\x00")
	True
	>>> unpackBase128(b'\x8f\xff\xff\xff\x7f')[0] == 4294967295
	True
	>>> unpackBase128(b'\x80\x80\x3f')  # doctest: +IGNORE_EXCEPTION_DETAIL
	Traceback (most recent call last):
	  File "<stdin>", line 1, in ?
	TTLibError: UIntBase128 value must not start with leading zeros
	>>> unpackBase128(b'\x8f\xff\xff\xff\xff\x7f')[0]  # doctest: +IGNORE_EXCEPTION_DETAIL
	Traceback (most recent call last):
	  File "<stdin>", line 1, in ?
	TTLibError: UIntBase128-encoded sequence is longer than 5 bytes
	>>> unpackBase128(b'\x90\x80\x80\x80\x00')[0]  # doctest: +IGNORE_EXCEPTION_DETAIL
	Traceback (most recent call last):
	  File "<stdin>", line 1, in ?
	TTLibError: UIntBase128 value exceeds 2**32-1
	"""
	result = 0
	assert len(data) > 0
	if byteord(data[0]) == 0x80:
		# font must be rejected if UIntBase128 value starts with 0x80
		raise TTLibError('UIntBase128 value must not start with leading zeros')
	for i in range(5):
		if len(data) == 0:
			raise TTLibError('not enough data to unpack UIntBase128')
		code = byteord(data[0])
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
	""" Return the length in bytes of a UIntBase128-encoded sequence with value n.

	>>> base128Size(0)
	1
	>>> base128Size(24567)
	3
	>>> base128Size(2**32-1)
	5
	"""
	assert n >= 0
	size = 1
	while n >= 128:
		size += 1
		n >>= 7
	return size

def packBase128(n):
	r""" Encode unsigned integer in range 0 to 2**32-1 (inclusive) to a string of
	bytes using UIntBase128 variable-length encoding. Produce the shortest possible
	encoding.

	>>> packBase128(63) == b"\x3f"
	True
	>>> packBase128(2**32-1) == b'\x8f\xff\xff\xff\x7f'
	True
	"""
	if n < 0 or n >= 2**32:
		raise TTLibError(
			"UIntBase128 format requires 0 <= integer <= 2**32-1")
	data = b''
	size = base128Size(n)
	for i in range(size):
		b = (n >> (7 * (size - i - 1))) & 0x7f
		if i < size - 1:
			b |= 0x80
		data += struct.pack('B', b)
	return data

def unpack255UShort(data):
	""" Read one to three bytes from 255UInt16-encoded input string, and return a
	tuple containing the decoded integer plus any leftover data.

	>>> unpack255UShort(bytechr(252))[0]
	252

	Note that some numbers (e.g. 506) can have multiple encodings:
	>>> unpack255UShort(struct.pack("BB", 254, 0))[0]
	506
	>>> unpack255UShort(struct.pack("BB", 255, 253))[0]
	506
	>>> unpack255UShort(struct.pack("BBB", 253, 1, 250))[0]
	506
	"""
	code = byteord(data[:1])
	data = data[1:]
	if code == 253:
		# read two more bytes as an unsigned short
		if len(data) < 2:
			raise TTLibError('not enough data to unpack 255UInt16')
		result, = struct.unpack(">H", data[:2])
		data = data[2:]
	elif code == 254:
		# read another byte, plus 253 * 2
		if len(data) == 0:
			raise TTLibError('not enough data to unpack 255UInt16')
		result = byteord(data[:1])
		result += 506
		data = data[1:]
	elif code == 255:
		# read another byte, plus 253
		if len(data) == 0:
			raise TTLibError('not enough data to unpack 255UInt16')
		result = byteord(data[:1])
		result += 253
		data = data[1:]
	else:
		# leave as is if lower than 253
		result = code
	# return result plus left over data
	return result, data

def pack255UShort(value):
	r""" Encode unsigned integer in range 0 to 65535 (inclusive) to a bytestring
	using 255UInt16 variable-length encoding.

	>>> pack255UShort(252) == b'\xfc'
	True
	>>> pack255UShort(506) == b'\xfe\x00'
	True
	>>> pack255UShort(762) == b'\xfd\x02\xfa'
	True
	"""
	if value < 0 or value > 0xFFFF:
		raise TTLibError(
			"255UInt16 format requires 0 <= integer <= 65535")
	if value < 253:
		return struct.pack(">B", value)
	elif value < 506:
		return struct.pack(">BB", 255, value - 253)
	elif value < 762:
		return struct.pack(">BB", 254, value - 506)
	else:
		return struct.pack(">BH", 253, value)

def padData(data):
	r""" Pad string with null bytes so that length is a multiple of 4.

	>>> len(padData(b'abcd'))
	4
	>>> len(padData(b'abcde'))
	8
	>>> padData(b'abcdef') == b'abcdef\x00\x00'
	True
	"""
	length = len(data)
	paddedLength = (length + 3) & ~3
	paddedData = tobytes(data) + b"\0" * (paddedLength - length)
	return paddedData


if __name__ == "__main__":
	import doctest, sys
	sys.exit(doctest.testmod().failed)
