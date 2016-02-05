import sys
from fontTools import ttLib

def fail(msg):
	print >> sys.stderr, msg
	sys.exit(1)

ttf = ttLib.TTFont(sys.argv[1])

if not ttf.isCollection():
	fail("Not a collection")

if 4 != ttf.fonts[0]['OS/2'].version:
	fail("Wrong OS/2 version")