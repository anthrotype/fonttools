from __future__ import print_function, division, absolute_import
from fontTools.misc.py23 import *
from fontTools.ttLib import getSearchRange, TTLibError
from fontTools.ttLib.sfnt import (SFNTReader, SFNTWriter, DirectoryEntry,
    sfntDirectorySize, sfntDirectoryEntrySize, sfntDirectoryFormat,
    SFNTDirectoryEntry)
import struct
from fontTools.misc import sstruct
from fontTools.misc.textTools import pad


# -- WOFF directory helpers and cruft

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
            assert len(data) == self.origLength
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

    @staticmethod
    def decodeData(rawData):
        import zlib
        return zlib.decompress(rawData)

    @staticmethod
    def encodeData(data):
        import zlib
        return zlib.compress(data)


class WOFFMixin(object):
    flavor = "woff"
    signature = b"wOFF"
    FlavorData = WOFFFlavorData
    directoryFormat = woffDirectoryFormat
    directorySize = woffDirectorySize
    DirectoryEntry = WOFFDirectoryEntry


class WOFFReader(WOFFMixin, SFNTReader):

    def __init__(self, file, checkChecksums=1, fontNumber=-1):
        signature = Tag(file.read(4))
        file.seek(0)
        if signature != self.signature:
            raise TTLibError("Not a %s font (bad signature)" % self.flavor.upper())

        super(WOFFReader, self).__init__(file, checkChecksums, fontNumber)

        self.file.seek(0, 2)
        if self.length != self.file.tell():
            raise TTLibError("reported 'length' doesn't match the actual file size")

        self.flavorData = self.FlavorData(self)


class WOFFWriter(WOFFMixin, SFNTWriter):

    def setFlavorData(self, flavorData):
        self.flavorData = self.FlavorData()
        if flavorData is not None:
            if not isinstance(flavorData, WOFFFlavorData):
                raise TypeError("expected WOFFFlavorData, found %s" % type(flavorData))
            # copy instead of replacing flavorData, to exchange between WOFF/WOFF2
            self.flavorData.__dict__.update(flavorData.__dict__)

    def close(self):
        self._assertNumTables()

        self.signature = self.__class__.signature
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
            compressedMetaData = pad(compressedMetaData, 4)
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


if __name__ == "__main__":
    import doctest, sys
    sys.exit(doctest.testmod().failed)
