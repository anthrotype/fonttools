from __future__ import print_function, division, absolute_import
from __future__ import unicode_literals
from fontTools.misc.py23 import BytesIO, Tag
from fontTools.ttLib.sfnt import SFNTReader, SFNTDirectoryEntry
from fontTools.ttLib.sfnt import sfntDirectorySize, sfntDirectoryEntrySize
from fontTools.ttLib.sfnt import calcChecksum
from fontTools.ttLib import TTLibError, sortedTagList, identifierToTag
from collections import OrderedDict 
import struct
import os
import pytest


data_dir = os.path.join(os.path.dirname(__file__), 'testdata')
ttf_path = os.path.join(data_dir, "tinyfont.ttf")
otf_path = os.path.join(data_dir, "tinyfont.otf")
ttc_path = os.path.join(data_dir, "tinyfont.ttc")
woff_path = os.path.join(data_dir, "tinyfont.woff")
ttf_tables_dir = os.path.join(data_dir, "tinyfont_tables_ttf")
otf_tables_dir = os.path.join(data_dir, "tinyfont_tables_otf")


@pytest.fixture(params=[ttf_path, otf_path], ids=["ttf", "otf"])
def font(request):
	with open(request.param, 'rb') as f:
		sfntVersion = f.read(4)
		f.seek(0)
		bio = BytesIO(f.read())
	bio.sfntVersion = Tag(sfntVersion)
	return bio


@pytest.fixture
def ttc():
	with open(ttc_path, 'rb') as f:
		bio = BytesIO(f.read())
	return bio


@pytest.fixture
def woff():
	with open(woff_path, 'rb') as f:
		bio = BytesIO(f.read())
	return bio


@pytest.fixture(scope="module")
def tables():

	def read_tables(data_dir):
		result = {}
		for fn in [fn for fn in os.listdir(data_dir) if fn.endswith(".bin")]:
			tag = identifierToTag(os.path.splitext(fn)[0])
			with open(os.path.join(data_dir, fn), 'rb') as fobj:
				result[tag] = fobj.read()
		return result

	ttf_tables = read_tables(ttf_tables_dir)
	otf_tables = read_tables(otf_tables_dir)
	# reuse table data which doesn't change across TTF and OTF fonts
	for tag in ttf_tables:
		if tag not in ("glyf", "loca") and tag not in otf_tables:
			otf_tables[tag] = ttf_tables[tag]
	result = {}
	for fmt, tables in zip(("ttf", "otf"), (ttf_tables, otf_tables)):
		sorted_tags = sortedTagList(tables.keys())
		result[fmt] = OrderedDict([(t, tables[t]) for t in sorted_tags])
	return result


class SFNTReaderTest:

	def test_read_sfnt_directory(self, font, tables):
		tables = tables['otf'] if font.sfntVersion == "OTTO" else tables['ttf']
		reader = SFNTReader(font)
		assert reader.file
		assert reader.checkChecksums == 1
		assert reader.flavor == None
		assert reader.flavorData == None
		assert reader.DirectoryEntry == SFNTDirectoryEntry
		assert reader.sfntVersion == font.sfntVersion
		assert reader.numTables == len(tables)
		assert list(reader.keys()) == list(tables.keys())
		offset = sfntDirectorySize + len(tables) * sfntDirectoryEntrySize
		for tag in tables.keys():
			entry = reader.tables[tag]
			assert entry.tag == tag
			assert entry.length == len(tables[tag])
			assert entry.offset == offset
			offset += (entry.length + 3) & ~3

	def test_bad_sfntVersion(self, font):
		font.write(b'\xff')
		font.seek(0)
		with pytest.raises(TTLibError) as excinfo:
			SFNTReader(font)
		assert "bad sfntVersion" in str(excinfo.value)

	def test_not_enough_data(self):
		with pytest.raises(TTLibError) as excinfo:
			SFNTReader(BytesIO(b""))
		assert "not enough data" in str(excinfo.value)

	def test_get_table_data(self, font, tables):
		reader = SFNTReader(font)
		tables = tables['otf'] if font.sfntVersion == "OTTO" else tables['ttf']
		for tag in tables.keys():
			assert reader[tag] == tables[tag]

	def test_checkChecksums(self, font):
		font.seek(16)
		font.write(b"\0\0\0\0")
		font.seek(0)
		reader = SFNTReader(font, checkChecksums=2)
		first_tag = sorted(reader.keys())[0]
		with pytest.raises(AssertionError) as excinfo:
			reader[first_tag]
		assert "bad checksum" in str(excinfo.value)

	def test_del_item(self, font):
		reader = SFNTReader(font)
		del reader['head']
		assert 'head' not in reader

	def test_close(self, font):
		reader = SFNTReader(font)
		reader.close()
		assert font.closed

	# XXX these below should move to their own individual test modules

	def test_read_ttc_header_with_fontNumber(self, ttc):
		reader = SFNTReader(ttc, fontNumber=0)
		assert reader.TTCTag == "ttcf"
		assert reader.Version == 0x10000
		assert reader.numFonts == 1
		assert reader.DirectoryEntry == SFNTDirectoryEntry
		assert reader.sfntVersion == "\0\1\0\0"
		assert reader.flavor == None
		assert reader.flavorData == None

	def test_read_ttc_header_bad_fontNumber(self, ttc):
		with pytest.raises(TTLibError) as excinfo:
			reader = SFNTReader(ttc, fontNumber=-1)
		assert "specify a font number" in str(excinfo.value)

	def test_read_woff_header(self, woff):
		from fontTools.ttLib.woff import WOFFDirectoryEntry
		reader = SFNTReader(woff)
		assert reader.flavor == "woff"
		assert reader.signature == "wOFF"
		assert reader.DirectoryEntry == WOFFDirectoryEntry
		assert reader.sfntVersion == "\0\1\0\0"
		assert reader.flavorData.metaData == b""
		assert reader.flavorData.privData == b""
		assert reader.flavorData.majorVersion == reader.majorVersion
		assert reader.flavorData.minorVersion == reader.minorVersion
