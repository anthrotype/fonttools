from __future__ import print_function
from fontTools.t1Lib import T1Font
from extractor.formats.type1 import extractFontFromType1
from defcon.objects.font import Font
import os

t1path = "/Users/cosimolupo/Downloads/utopia-1.0/putb.pfa"
t1font = T1Font(t1path)
t1font.parse()
print(t1font.font.keys())

ufofont = Font()
extractFontFromType1(t1path, ufofont)
ufopath = os.path.splitext(t1path)[0] + '.ufo'
ufofont.save(ufopath)
