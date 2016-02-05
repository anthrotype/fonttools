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
from collections import OrderedDict
import logging


log = logging.getLogger(__name__)


class SFNTReader(object):

	def __new__(cls, *args, **kwargs):
		""" Return an instance of the SFNTReader sub-class which is compatible
		with the input file type.
		"""
		if args and cls is SFNTReader:
			infile = args[0]
			sfntVersion = Tag(infile.read(4))
			infile.seek(0)
			if sfntVersion == "wOF2":
				# return new WOFF2Reader object
				from fontTools.ttLib.woff2 import WOFF2Reader
				return object.__new__(WOFF2Reader)
		# return default object
		return object.__new__(cls)

	def __init__(self, file, checkChecksums=1, fontNumber=-1):
		self.file = file
		self.checkChecksums = checkChecksums

		self.flavor = None
		self.flavorData = None
		self.DirectoryEntry = SFNTDirectoryEntry
		self.sfntVersion = self.file.read(4)
		self.file.seek(0)
		self.fontNumber = fontNumber

		if self.sfntVersion == b"ttcf":
			ttcHeader = TTCHeader(self.file)
			if not -1 <= fontNumber < ttcHeader.numFonts:
				from fontTools import ttLib
				raise ttLib.TTLibError("specify a font number between 0 and %d (inclusive)" % (ttcHeader.numFonts - 1))

			if fontNumber > -1:
				# unpack a single font from a collection
				log.debug('sfntVersion %s fontNumber %d offset %d' % (self.sfntVersion, fontNumber, ttcHeader.offsetTable[fontNumber]))
				self.file.seek(ttcHeader.offsetTable[fontNumber])
				log.debug('Read %d bytes starting at %d. End is %d. closed: %r.' % (sfntDirectorySize, self.file.tell(), len(self.file.getvalue()), self.file.closed)) # TEMPORARY
				data = self.file.read(sfntDirectorySize)
				if len(data) != sfntDirectorySize:
					from fontTools import ttLib
					raise ttLib.TTLibError("Not a Font Collection (not enough data)")
				sstruct.unpack(sfntDirectoryFormat, data, self)
			else:
				# unpack the entire collection
				self.fonts = []
				for idx in range(ttcHeader.numFonts):
					log.debug('unpacking font %d' % idx) # TEMPORARY
					font = SFNTReader(file, checkChecksums=checkChecksums, fontNumber=idx)
					font.offset = ttcHeader.offsetTable[idx]
					self.fonts.append(font)

		elif self.sfntVersion == b"wOFF":
			self.flavor = "woff"
			self.DirectoryEntry = WOFFDirectoryEntry
			data = self.file.read(woffDirectorySize)
			if len(data) != woffDirectorySize:
				from fontTools import ttLib
				raise ttLib.TTLibError("Not a WOFF font (not enough data)")
			sstruct.unpack(woffDirectoryFormat, data, self)
		else:
			data = self.file.read(sfntDirectorySize)
			if len(data) != sfntDirectorySize:
				from fontTools import ttLib
				raise ttLib.TTLibError("Not a TrueType or OpenType font (not enough data)")
			sstruct.unpack(sfntDirectoryFormat, data, self)
		self.sfntVersion = Tag(self.sfntVersion)

		if self.sfntVersion not in ("\x00\x01\x00\x00", "OTTO", "true", "ttcf"):
			from fontTools import ttLib
			raise ttLib.TTLibError("Not a TrueType or OpenType font (bad sfntVersion %s)" % self.sfntVersion)

		def createDirectoryEntry(font, file):
				entry = font.DirectoryEntry()
				entry.fromFile(file)
				return (Tag(entry.tag), entry)

		self.tables = {}
		if not self.isCollection():
			for i in range(self.numTables):
				(tag, entry) = createDirectoryEntry(self, self.file)
				self.tables[entry.tag] = entry
			self.tables = OrderedDict(sorted(self.tables.items(), key=lambda i: i[1].offset))
		else:
			for font_idx, font in enumerate(self.fonts):
				self.file.seek(font.offset + sfntDirectorySize)
				if self.file.tell() != font.offset + sfntDirectorySize:
					from fontTools import ttLib
					raise ttLib.TTLibError("Not a Font Collection (not enough data)")

				font.tables = {}
				for i in range(font.numTables):
					(tag, entry) = createDirectoryEntry(font, self.file)
					font.tables[tag] = entry
				font.tables = OrderedDict(sorted(font.tables.items(), key=lambda i: i[1].offset))

			# note which tables are reused
			self.reuseMap = {}
			owning_font_by_offset = {}
			for font_idx, font in enumerate(self.fonts):
				for table in font.tables.values():
					if table.offset not in owning_font_by_offset:
						owning_font_by_offset[table.offset] = font_idx
					else:
						owner_idx = owning_font_by_offset[table.offset]
						self.reuseMap[(font_idx, table.tag)] = owner_idx
			log.debug('reuseMap from offsets: %s' % self.reuseMap) # TEMPORARY

		# Load flavor data if any
		if self.flavor == "woff":
			self.flavorData = WOFFFlavorData(self)

		self.tables = OrderedDict(sorted(self.tables.items(), key=lambda i: i[1].offset))

		#TEMPORARY
		if self.isCollection():
			for idx, font in enumerate(self.fonts):
				log.debug('font %d numTables %d tables: %s' % (idx, font.numTables, font.keys()))
		else:
			log.debug('font %d numTables %d len(self.tables) %d tables: %s' % (
				self.fontNumber, self.numTables, len(self.tables), [(t.tag, t.offset) for t in self.tables.values()]))

	def isCollection(self):
		return self.sfntVersion == "ttcf" and self.fontNumber == -1

	def numTables(self, countReuses=False):
		if not self.isCollection():
			count = len(self.tables)
		else:
			count = 0
			for font_idx, font in enumerate(self.fonts):
				for table in font.tables.values():
					if countReuses or not (font_idx, table.tag) in self.reuseMap:
						count += 1
		return count

	def has_key(self, tag):
		return tag in self.tables

	__contains__ = has_key

	def keys(self):
		return self.tables.keys()

	def __getitem__(self, tag):
		"""Fetch the raw table data."""
		entry = self.tables[Tag(tag)]
		data = entry.loadData (self.file)
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
				# Be friendly, and just log a warning.
				log.warning("bad checksum for '%s' table", tag)
		return data

	def __delitem__(self, tag):
		del self.tables[Tag(tag)]

	def close(self):
		self.file.close()


# default compression level for WOFF 1.0 tables and metadata
ZLIB_COMPRESSION_LEVEL = 6

# if set to True, use zopfli instead of zlib for compressing WOFF 1.0.
# The Python bindings are available at https://github.com/anthrotype/py-zopfli
USE_ZOPFLI = False

# mapping between zlib's compression levels and zopfli's 'numiterations'.
# Use lower values for files over several MB in size or it will be too slow
ZOPFLI_LEVELS = {
	# 0: 0,  # can't do 0 iterations...
	1: 1,
	2: 3,
	3: 5,
	4: 8,
	5: 10,
	6: 15,
	7: 25,
	8: 50,
	9: 100,
}


def compress(data, level=ZLIB_COMPRESSION_LEVEL):
	""" Compress 'data' to Zlib format. If 'USE_ZOPFLI' variable is True,
	zopfli is used instead of the zlib module.
	The compression 'level' must be between 0 and 9. 1 gives best speed,
	9 gives best compression (0 gives no compression at all).
	The default value is a compromise between speed and compression (6).
	"""
	if not (0 <= level <= 9):
		raise ValueError('Bad compression level: %s' % level)
	if not USE_ZOPFLI or level == 0:
		from zlib import compress
		return compress(data, level)
	else:
		from zopfli.zlib import compress
		return compress(data, numiterations=ZOPFLI_LEVELS[level])


class SFNTWriter(object):

	def __new__(cls, *args, **kwargs):
		""" Return an instance of the SFNTWriter sub-class which is compatible
		with the specified 'flavor'.
		"""
		flavor = None
		if kwargs and 'flavor' in kwargs:
			flavor = kwargs['flavor']
		elif args and len(args) > 3:
			flavor = args[3]
		if cls is SFNTWriter:
			if flavor == "woff2":
				# return new WOFF2Writer object
				from fontTools.ttLib.woff2 import WOFF2Writer
				return object.__new__(WOFF2Writer)
		# return default object
		return object.__new__(cls)

	def __init__(self, file, numTables, sfntVersion="\000\001\000\000",
			flavor=None, flavorData=None, collectionSize=-1):
		self.file = file
		self.numTables = numTables
		self.sfntVersion = Tag(sfntVersion)
		self.flavor = flavor
		self.flavorData = flavorData
		self.collectionSize = collectionSize
		self.reuseHits = 0

		if self.flavor == "woff":
			self.directoryFormat = woffDirectoryFormat
			self.directorySize = woffDirectorySize
			self.DirectoryEntry = WOFFDirectoryEntry

			self.signature = "wOFF"

			# to calculate WOFF checksum adjustment, we also need the original SFNT offsets
			self.origNextTableOffset = sfntDirectorySize + numTables * sfntDirectoryEntrySize
		elif self.sfntVersion == 'ttcf':
			if collectionSize == -1:
				from fontTools import ttLib
				raise ttLib.TTLibError("Must specify collectionSize for a collection")
			self.directoryFormat = ttcHeaderFormat
			self.directorySize = ttcHeaderSize
			self.DirectoryEntry = SFNTDirectoryEntry
			self.TTCTag = 'ttcf'
			self.Version = 0x00010000
			self.numFonts = collectionSize
			self.offsetTable = []
			self.reuseMaps = []
		else:
			assert not self.flavor, "Unknown flavor '%s'" % self.flavor
			self.directoryFormat = sfntDirectoryFormat
			self.directorySize = sfntDirectorySize
			self.DirectoryEntry = SFNTDirectoryEntry

			self.searchRange, self.entrySelector, self.rangeShift = getSearchRange(numTables, 16)

		self.nextTableOffset = self.directorySize + numTables * self.DirectoryEntry.formatSize
		if self.sfntVersion == 'ttcf':
			self.nextTableOffset = self.directorySize + collectionSize * ttcOffsetTableEntrySize

		log.debug('dirSz %d collectionSize %d numTables %d dirFmtSz %d nextOffset %d' % (
			self.directorySize, self.collectionSize, self.numTables, self.DirectoryEntry.formatSize, self.nextTableOffset)) # TEMPORARY
		# clear out directory area
		self.file.seek(self.nextTableOffset)
		# make sure we're actually where we want to be. (old cStringIO bug)
		self.file.write(b'\0' * (self.nextTableOffset - self.file.tell()))
		self.tables = OrderedDict()
		self.fontIndex = -1

	def _isCollection(self):
		return self.sfntVersion == 'ttcf'

	def startCollectionFont(self, numTables, reuseMap):
		self.fontIndex += 1
		self.offsetTable.append(self.file.tell())
		self.reuseMaps.append(reuseMap)

		self.nextTableOffset += sfntDirectorySize + numTables * sfntDirectoryEntrySize
		log.debug('write %d 0s at %d to reserve space for font %d directory of %d tables' % (
				self.nextTableOffset - self.file.tell(), self.file.tell(), self.fontIndex, numTables))
		self.file.write(b'\0' * (self.nextTableOffset - self.file.tell()))

	def __setitem__(self, tag, data):
		"""Write raw table data to disk."""
		reuseMap = self.reuseMaps[self.fontIndex]
		if self._isCollection() and tag in reuseMap:
			key = (self.reuseMaps[self.fontIndex][tag], tag)
			self.tables[(self.fontIndex, tag)] = self.tables[key]
			return

		if (self.fontIndex, tag) in self.tables:
			from fontTools import ttLib
			raise ttLib.TTLibError("cannot rewrite '%s' table" % tag)

		entry = self.DirectoryEntry()
		entry.tag = tag
		entry.offset = self.nextTableOffset
		log.debug('%s starts at %d' % (tag, entry.offset)) # TEMPORARY
		if tag == 'head':
			entry.checkSum = calcChecksum(data[:8] + b'\0\0\0\0' + data[12:])
			self.headTable = data
			entry.uncompressed = True
		else:
			entry.checkSum = calcChecksum(data)
		entry.saveData(self.file, data)

		if self.flavor == "woff":
			entry.origOffset = self.origNextTableOffset
			self.origNextTableOffset += (entry.origLength + 3) & ~3

		self.nextTableOffset = self.nextTableOffset + ((entry.length + 3) & ~3)
		# Add NUL bytes to pad the table data to a 4-byte boundary.
		# Don't depend on f.seek() as we need to add the padding even if no
		# subsequent write follows (seek is lazy), ie. after the final table
		# in the font.
		self.file.write(b'\0' * (self.nextTableOffset - self.file.tell()))
		assert self.nextTableOffset == self.file.tell()

		self.tables[(self.fontIndex, tag)] = entry

	def close(self):
		"""All tables must have been written to disk. Now write the
		directory.
		"""
		tables = sorted(self.tables.items())
		if len(tables) != self.numTables:
			from fontTools import ttLib
			raise ttLib.TTLibError("wrong number of tables; expected %d, found %d" % (self.numTables, len(tables)))

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
				compressedMetaData = compress(data.metaData)
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
			assert not self.flavor, "Unknown flavor '%s'" % self.flavor
			pass

		directory = sstruct.pack(self.directoryFormat, self)
		if self._isCollection():
			if len(self.offsetTable) != self.collectionSize:
				from fontTools import ttLib
				raise ttLib.TTLibError("Wrong number of offsets. Got %d, expected %d" % (len(self.offsetTable), self.collectionSize))
			if len(self.reuseMaps) != self.collectionSize:
				from fontTools import ttLib
				raise ttLib.TTLibError("Wrong number of reuse maps. Got %d, expected %d" % (len(self.reuseMaps), self.collectionSize))
			for offset in self.offsetTable:
				directory += struct.pack('>L', offset)
			self.file.seek(0)
			self.file.write(directory)

			# Drop in the table headers for each font, including reused tables.
			for fontIndex in range(self.collectionSize):
				tables = [table for (i, _), table in self.tables.items() if fontIndex == i]
				reuseMap = self.reuseMaps[fontIndex]

				# write a sfnt directory
				sfntDir = SFNTDirectory()
				sfntDir.numTables = len(tables)
				sfntDir.updateDerivedFields()

				log.debug('font %d has %d tables (%d tables, %d reused)' % (fontIndex, sfntDir.numTables, len(tables), len(reuseMap)))
				log.debug('reuse for %d: %s' % (fontIndex, reuseMap))
				log.debug('sfntDir %d: %s' % (fontIndex, sfntDir))
				self.file.seek(self.offsetTable[fontIndex])
				self.file.write(sstruct.pack(sfntDirectoryFormat, sfntDir))
				log.debug('Wrote %d byte directory at %d for font %d' % (self.file.tell() - self.offsetTable[fontIndex], self.offsetTable[fontIndex], fontIndex))

				for table in tables:
					self.file.write(table.toString())

		# checksums aren't well defined for collections
		# TODO: something reasonable. 0s?
		if not self._isCollection():
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
		keys = list(self.tables.keys())
		checksums = []
		for i in range(len(keys)):
			checksums.append(self.tables[keys[i]].checkSum)

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
		checksumadjustment = self._calcMasterChecksum(directory)
		# write the checksum to the file
		# Writes for all 'head' if this is a collection
		heads = [table for (_, tag), table in self.tables.items() if tag == 'head']
		if not heads:
			from fontTools import ttLib
			raise ttLib.TTLibError("At least one 'head' table expected")
		for head in heads:
			self.file.seek(table.offset + 8)
			self.file.write(struct.pack(">L", checksumadjustment))

	def reordersTables(self):
		return False


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

ttcOffsetTableEntrySize = 4  # ULong offset for each font

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
		self.reuse_from = None

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

class TTCHeaderEntry(DirectoryEntry):
	format = ttcHeaderFormat
	formatSize = ttcOffsetTableEntrySize

class SFNTDirectoryEntry(DirectoryEntry):

	format = sfntDirectoryEntryFormat
	formatSize = sfntDirectoryEntrySize

class WOFFDirectoryEntry(DirectoryEntry):

	format = woffDirectoryEntryFormat
	formatSize = woffDirectoryEntrySize
	zlibCompressionLevel = ZLIB_COMPRESSION_LEVEL

	def decodeData(self, rawData):
		import zlib
		if self.length == self.origLength:
			data = rawData
		else:
			assert self.length < self.origLength
			data = zlib.decompress(rawData)
			assert len(data) == self.origLength
		return data

	def encodeData(self, data):
		self.origLength = len(data)
		if not self.uncompressed:
			compressedData = compress(data, self.zlibCompressionLevel)
		if self.uncompressed or len(compressedData) >= self.origLength:
			# Encode uncompressed
			rawData = data
			self.length = self.origLength
		else:
			rawData = compressedData
			self.length = len(rawData)
		return rawData

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

class SFNTDirectory():
	def __init__(self):
		self.sfntVersion = Tag("\000\001\000\000")
		self.numTables = 0
		self.searchRange = 0
		self.entrySelector = 0
		self.rangeShift = 0

	def updateDerivedFields(self):
		self.searchRange, self.entrySelector, self.rangeShift = getSearchRange(self.numTables, 16)

class TTCHeader():
	def __init__(self, file):
		file.seek(0)
		data = file.read(ttcHeaderSize)
		if len(data) != ttcHeaderSize:
			from fontTools import ttLib
			raise ttLib.TTLibError("Not a Font Collection (not enough data)")
		sstruct.unpack(ttcHeaderFormat, data, self)
		self.offsetTable = struct.unpack(">%dL" % self.numFonts, file.read(self.numFonts * 4))
		assert self.Version == 0x00010000 or self.Version == 0x00020000, "unrecognized TTC version 0x%08x" % self.Version
		if self.Version == 0x00020000:
			# ignoring version 2.0 signatures
			pass

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
	import sys
	import doctest
	sys.exit(doctest.testmod().failed)
