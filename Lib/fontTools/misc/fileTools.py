"""fontTools.misc.fixedTools.py -- tools for working with files or folders.
"""
from __future__ import print_function, division, absolute_import
from fontTools.misc.py23 import *
import os
import re
from fontTools.misc.macCreatorType import getMacCreatorAndType


numberAddedRE = re.compile("#\d+$")
opentypeheaderRE = re.compile('''sfntVersion=['"]OTTO["']''')


def makeOutputFileName(input, outputDir, extension, overWrite=False):
    dirName, fileName = os.path.split(input)
    fileName, ext = os.path.splitext(fileName)
    if outputDir:
        dirName = outputDir
    fileName = numberAddedRE.split(fileName)[0]
    output = os.path.join(dirName, fileName + extension)
    n = 1
    if not overWrite:
        while os.path.exists(output):
            output = os.path.join(dirName, fileName + "#" + repr(n) + extension)
            n = n + 1
    return output


def guessFileType(fileOrPath):
	""" Take a path or file object, and return its file type.
	Return None if the file type can't be found.
	Supported file types: TTF, OTF, TTC, WOFF, WOFF2, DFONT, TTX, OTX
	"""
	if not hasattr(fileOrPath, "read"):
		# assume fileOrPath is a file name
		fileName = fileOrPath
		try:
			f = open(fileName, "rb")
		except IOError:
			return None
	else:
		# assume fileOrPath is a readable file object
		f = fileOrPath
		# get file name, if it has one
		if hasattr(f, 'name') and os.path.exists(f.name):
			fileName = f.name
		else:
			fileName = ""
	if fileName:
		base, ext = os.path.splitext(fileName)
		if ext == ".dfont":
			return "DFONT"
		cr, tp = getMacCreatorAndType(fileName)
		if tp in ("sfnt", "FFIL"):
			return "TTF"
	# seek to start, but remember the current position
	pos = f.tell()
	f.seek(0)
	header = f.read(256)
	f.seek(pos)
	head = Tag(header[:4])
	if head == "OTTO":
		return "OTF"
	elif head == "ttcf":
		return "TTC"
	elif head in ("\0\1\0\0", "true"):
		return "TTF"
	elif head == "wOFF":
		return "WOFF"
	elif head == "wOF2":
		return "WOFF2"
	elif head.lower() == "<?xm":
		# Use 'latin1' because that can't fail.
		header = tostr(header, 'latin1')
		if opentypeheaderRE.search(header):
			return "OTX"
		else:
			return "TTX"
	return None