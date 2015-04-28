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
from fontTools.ttLib import getSearchRange, TTLibError, haveBrotli
import sys
import struct
from collections import OrderedDict


class SFNTReader(object):

	flavor = None

	def __new__(cls, file, checkChecksums=1, fontNumber=-1):
		if cls is SFNTReader:
			sfntVersion = Tag(file.read(4))
			file.seek(0)
			if sfntVersion == "wOF2":
				if haveBrotli:
					# return new WOFF2Reader object
					from .woff2 import WOFF2Reader
					return super(SFNTReader, cls).__new__(WOFF2Reader)
				else:
					print('The WOFF2 encoder requires the Brotli Python extension:\n'
						  'https://github.com/google/brotli', file=sys.stderr)
					raise ImportError("No module named brotli")
			elif sfntVersion == "wOFF":
				# return new WOFFReader object
				from .woff import WOFFReader
				return super(SFNTReader, cls).__new__(WOFFReader)
			elif sfntVersion == "ttcf":
				# return new SFNTCollectionReader object
				return super(SFNTReader, cls).__new__(SFNTCollectionReader)
		# return default
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


class SFNTWriter(object):

	flavor = None

	def __new__(cls, file, numTables, sfntVersion="\000\001\000\000",
		        flavor=None, flavorData=None):
		if cls is SFNTWriter:
			if flavor == "woff2":
				if haveBrotli:
					# return new WOFF2Writer object
					from .woff2 import WOFF2Writer
					return super(SFNTWriter, cls).__new__(WOFF2Writer)
				else:
					print('The WOFF2 encoder requires the Brotli Python extension:\n'
						  'https://github.com/google/brotli', file=sys.stderr)
					raise ImportError("No module named brotli")
			elif flavor == "woff":
				# return new WOFFWriter object
				from .woff import WOFFWriter
				return super(SFNTWriter, cls).__new__(WOFFWriter)
			elif flavor == "ttc":
				# return new SFNTCollectionWriter object
				raise NotImplementedError
		# return default
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


if __name__ == "__main__":
	import doctest, sys
	sys.exit(doctest.testmod().failed)
