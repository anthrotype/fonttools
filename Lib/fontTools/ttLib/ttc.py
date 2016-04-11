from __future__ import print_function, division, absolute_import
# from fontTools.misc.py23 import *
from fontTools.ttLib import TTLibError, TTFont
from fontTools.ttLib.sfnt import SFNTReader, SFNTWriter
import struct
from fontTools.misc import sstruct
from collections import MutableSequence


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


class TTCollection(MutableSequence):

    def __init__(self, fileOrTTFonts=None, **kwargs):
        self.fonts = []
        self.reader = None
        if not fileOrTTFonts:
            return
        if isinstance(fileOrTTFonts, (TTCollection, tuple, list)):
            for font in fileOrTTFonts:
                if not isinstance(font, TTFont):
                    raise TTLibError("expected TTFont, found %s" % type(font).__name__)
            self.fonts = list(fileOrTTFonts)
            self.reader = None
        else:
            self.fonts = []
            if not hasattr(fileOrTTFonts, "read"):
                closeStream = True
                file = open(fileOrTTFonts, 'rb')
            else:
                # assume "file" is a readable file object
                file = fileOrTTFonts
                closeStream = False
            checkChecksums = kwargs.pop("checkChecksums", False)
            self.reader = TTCReader(file, checkChecksums)
            for i in range(self.reader.numFonts):
                self.reader.seekOffsetTable(i)
                font = TTFont(**kwargs)
                font.reader = SFNTReader(file, self.reader.checkChecksums)
                self.fonts.append(font)

    def __len__(self):
        return len(self.fonts)

    def __getitem__(self, i):
        return self.fonts[i]

    def __setitem__(self, i, item):
        if not isinstance(item, TTFont):
            raise TTLibError("TTCollection can only contain TTFont instances")
        self.fonts[i] = item

    def __delitem__(self, i):
        del self.fonts[i]

    def insert(self, i, item):
        if not isinstance(item, TTFont):
            raise TTLibError("TTCollection can only contain TTFont instances")
        self.fonts.insert(i, item)

    def __repr__(self):
        return "TTCollection(%r)" % self.fonts


class TTCReader(SFNTReader):

    flavor = "ttc"

    def __init__(self, file, checkChecksums=1, fontNumber=None):
        self.file = file
        self.checkChecksums = checkChecksums

        self._readCollectionHeader()
        if fontNumber is None:
            self.flavor = self.__class__.flavor
        else:
            # read single font from collection
            self.flavor = None
            self.seekOffsetTable(fontNumber)
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

    def seekOffsetTable(self, fontNumber):
        """Move current position to the offset table of font 'fontNumber'."""
        if not 0 <= fontNumber < self.numFonts:
            raise TTLibError("specify a font number between 0 and %d (inclusive)" % (self.numFonts - 1))
        self.file.seek(self.offsetTables[fontNumber])
