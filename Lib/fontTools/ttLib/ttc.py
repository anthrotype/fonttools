from __future__ import print_function, division, absolute_import
# from fontTools.misc.py23 import *
from fontTools.ttLib import TTLibError
from fontTools.ttLib.sfnt import SFNTReader, SFNTWriter
import struct
from fontTools.misc import sstruct


# -- TTC directory helpers and cruft

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


class TTCReader(SFNTReader):

    flavor = "ttc"

    def __init__(self, file, checkChecksums=1, fontNumber=-1):
        self.file = file
        self.checkChecksums = checkChecksums

        self._readCollectionHeader()
        if fontNumber == -1:
            # read the whole collection
            raise NotImplementedError
        else:
            # read single font from collection
            self.flavor = None
            self._seekOffsetTable(fontNumber)
        self._readDirectory()

    def _readCollectionHeader(self):
        if self.file.read(4) != b"ttcf":
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
            # TODO(anthrotype): use flavorData to store version 2.0 signatures?
            pass

    def _seekOffsetTable(self, fontNumber):
        """Move current position to the offset table of font 'fontNumber'."""
        if not 0 <= fontNumber < self.numFonts:
            raise TTLibError("specify a font number between 0 and %d (inclusive)" % (self.numFonts - 1))
        self.file.seek(self.offsetTables[fontNumber])