from __future__ import print_function, division, absolute_import
from fontTools.misc.py23 import *
import unittest
from fontTools.t1Lib import T1Font


t1path = "/Users/cosimolupo/Downloads/utopia-1.0/putb.pfa"
t1font = T1Font(t1path)
t1font.parse()
print(t1font.font.keys())

# from extractor.formats.type1 import extractFontFromType1
# from defcon.objects.font import Font
# import os
# ufofont = Font()
# extractFontFromType1(t1path, ufofont)
# ufopath = os.path.splitext(t1path)[0] + '.ufo'
# ufofont.save(ufopath)
