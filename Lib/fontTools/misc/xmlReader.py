from __future__ import print_function, division, absolute_import
from fontTools.misc.py23 import *
from fontTools import ttLib
from fontTools.misc.textTools import safeEval
from fontTools.ttLib.tables.DefaultTable import DefaultTable
from fontTools.ttLib import TTFont
import os


class TTXParseError(Exception): pass

BUFSIZE = 0x4000


class XMLReader(object):

	def __init__(self, fileOrPath, ttFont, progress=None, quiet=False):
		if fileOrPath == '-':
			fileOrPath = sys.stdin
		if not hasattr(fileOrPath, "read"):
			self.file = open(fileOrPath, "rb")
			self._closeStream = True
		else:
			# assume readable file object
			self.file = fileOrPath
			self._closeStream = False
		self.rootFont = ttFont
		self.currentFont = ttFont
		self.progress = progress
		self.quiet = quiet
		self.root = None
		self.contentStack = []
		self.stackSize = 0
		self.fontDepth = 0
		self.tableDepth = 1
		self.tablePropertyDepth = 2

	def read(self):
		if self.progress:
			self.file.seek(0, 2)
			fileSize = self.file.tell()
			self.progress.set(0, fileSize // 100 or 1)
			self.file.seek(0)
		self._parseFile(self.file)
		if self._closeStream:
			self.close()

	def close(self):
		self.file.close()

	def _parseFile(self, file):
		from xml.parsers.expat import ParserCreate
		parser = ParserCreate()
		parser.StartElementHandler = self._startElementHandler
		parser.EndElementHandler = self._endElementHandler
		parser.CharacterDataHandler = self._characterDataHandler

		pos = 0
		while True:
			chunk = file.read(BUFSIZE)
			if not chunk:
				parser.Parse(chunk, 1)
				break
			pos = pos + len(chunk)
			if self.progress:
				self.progress.set(pos // 100)
			parser.Parse(chunk, 0)

	def _startNewFont(self):
		return TTFont(flavor=self.rootFont.flavor,
       recalcBBoxes=self.rootFont.recalcBBoxes,
       recalcTimestamp=self.rootFont.recalcTimestamp,
       verbose=self.rootFont.verbose, allowVID=self.rootFont.allowVID)

	def _startElementHandler(self, name, attrs):
		stackSize = self.stackSize
		self.stackSize = stackSize + 1
		if stackSize <= self.fontDepth:
			if name != "ttFont":
				raise TTXParseError("illegal root tag: %s" % name)

			if stackSize == 1:
				self.currentFont = self._startNewFont()
				self.rootFont.fonts.append(self.currentFont)


			sfntVersion = attrs.get("sfntVersion")
			if sfntVersion is not None:
				if len(sfntVersion) != 4:
					sfntVersion = safeEval('"' + sfntVersion + '"')
				self.currentFont.sfntVersion = sfntVersion
			self.contentStack.append([])

			if sfntVersion == 'ttcf':
				print('Adjusting depths for collection') # TEMPORARY
				self.rootFont.fonts = []
				self.rootFont.reuseMap = {}
				self.fontDepth = 1
				self.tableDepth = 2
				self.tablePropertyDepth = 3

		elif stackSize == self.tableDepth:
			subFile = attrs.get("src")
			if subFile is not None:
				if hasattr(self.file, 'name'):
					# if file has a name, get its parent directory
					dirname = os.path.dirname(self.file.name)
				else:
					# else fall back to using the current working directory
					dirname = os.getcwd()
				subFile = os.path.join(dirname, subFile)
				subReader = XMLReader(subFile, self.currentFont, self.progress, self.quiet)
				subReader.read()
				self.contentStack.append([])
				return

			reuse_from = attrs.get("reuse_from")
			tag = ttLib.xmlToTag(name)
			msg = "Parsing '%s' table..." % tag
			if reuse_from is not None:
				reuse_from = int(reuse_from)
				if not -1 < reuse_from < len(self.rootFont.fonts):
					raise TTXParseError("Table '%s' illegal reuse_from %d" % (tag, reuse_from))
				msg = "Reusing '%s' table from font %d..." % (tag, reuse_from)
			if self.progress:
				self.progress.setLabel(msg)
			elif self.currentFont.verbose:
				ttLib.debugmsg(msg)
			else:
				if not self.quiet:
					print(msg)

			if reuse_from is not None:
				self.currentFont[tag] = self.rootFont.fonts[reuse_from][tag]
				self.contentStack.append([])

				reuse_key = (len(self.rootFont.fonts) - 1, tag)
				self.rootFont.reuseMap[reuse_key] = reuse_from
				return

			if tag == "GlyphOrder":
				tableClass = ttLib.GlyphOrder
			elif "ERROR" in attrs or ('raw' in attrs and safeEval(attrs['raw'])):
				tableClass = DefaultTable
			else:
				tableClass = ttLib.getTableClass(tag)
				if tableClass is None:
					tableClass = DefaultTable
			if tag == 'loca' and tag in self.currentFont:
				# Special-case the 'loca' table as we need the
				#    original if the 'glyf' table isn't recompiled.
				self.currentTable = self.currentFont[tag]
			else:
				self.currentTable = tableClass(tag)
				self.currentFont[tag] = self.currentTable
			self.contentStack.append([])
		elif stackSize == self.tablePropertyDepth:
			self.contentStack.append([])
			self.root = (name, attrs, self.contentStack[-1])
		else:
			l = []
			self.contentStack[-1].append((name, attrs, l))
			self.contentStack.append(l)

	def _characterDataHandler(self, data):
		if self.stackSize > 1:
			self.contentStack[-1].append(data)

	def _endElementHandler(self, name):
		self.stackSize = self.stackSize - 1
		del self.contentStack[-1]
		if self.stackSize == self.tableDepth:
			self.root = None
		elif self.stackSize == self.tablePropertyDepth:
			name, attrs, content = self.root
			self.currentTable.fromXML(name, attrs, content, self.currentFont)
			self.root = None


class ProgressPrinter(object):

	def __init__(self, title, maxval=100):
		print(title)

	def set(self, val, maxval=None):
		pass

	def increment(self, val=1):
		pass

	def setLabel(self, text):
		print(text)
