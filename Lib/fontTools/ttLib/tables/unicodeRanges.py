""" Unicode ranges data from the OpenType OS/2 table specification v1.7. """

OS2_UNICODE_RANGES = (
	(('Basic Latin',                              (0x0000, 0x007F)),),
	(('Latin-1 Supplement',                       (0x0080, 0x00FF)),),
	(('Latin Extended-A',                         (0x0100, 0x017F)),),
	(('Latin Extended-B',                         (0x0180, 0x024F)),),
	(('IPA Extensions',                           (0x0250, 0x02AF)),
	 ('Phonetic Extensions',                      (0x1D00, 0x1D7F)),
	 ('Phonetic Extensions Supplement',           (0x1D80, 0x1DBF))),
	(('Spacing Modifier Letters',                 (0x02B0, 0x02FF)),
	 ('Modifier Tone Letters',                    (0xA700, 0xA71F))),
	(('Combining Diacritical Marks',              (0x0300, 0x036F)),
	 ('Combining Diacritical Marks Supplement',   (0x1DC0, 0x1DFF))),
	(('Greek and Coptic',                         (0x0370, 0x03FF)),),
	(('Coptic',                                   (0x2C80, 0x2CFF)),),
	(('Cyrillic',                                 (0x0400, 0x04FF)),
	 ('Cyrillic Supplement',                      (0x0500, 0x052F)),
	 ('Cyrillic Extended-A',                      (0x2DE0, 0x2DFF)),
	 ('Cyrillic Extended-B',                      (0xA640, 0xA69F))),
	(('Armenian',                                 (0x0530, 0x058F)),),
	(('Hebrew',                                   (0x0590, 0x05FF)),),
	(('Vai',                                      (0xA500, 0xA63F)),),
	(('Arabic',                                   (0x0600, 0x06FF)),
	 ('Arabic Supplement',                        (0x0750, 0x077F))),
	(('NKo',                                      (0x07C0, 0x07FF)),),
	(('Devanagari',                               (0x0900, 0x097F)),),
	(('Bengali',                                  (0x0980, 0x09FF)),),
	(('Gurmukhi',                                 (0x0A00, 0x0A7F)),),
	(('Gujarati',                                 (0x0A80, 0x0AFF)),),
	(('Oriya',                                    (0x0B00, 0x0B7F)),),
	(('Tamil',                                    (0x0B80, 0x0BFF)),),
	(('Telugu',                                   (0x0C00, 0x0C7F)),),
	(('Kannada',                                  (0x0C80, 0x0CFF)),),
	(('Malayalam',                                (0x0D00, 0x0D7F)),),
	(('Thai',                                     (0x0E00, 0x0E7F)),),
	(('Lao',                                      (0x0E80, 0x0EFF)),),
	(('Georgian',                                 (0x10A0, 0x10FF)),
	 ('Georgian Supplement',                      (0x2D00, 0x2D2F))),
	(('Balinese',                                 (0x1B00, 0x1B7F)),),
	(('Hangul Jamo',                              (0x1100, 0x11FF)),),
	(('Latin Extended Additional',                (0x1E00, 0x1EFF)),
	 ('Latin Extended-C',                         (0x2C60, 0x2C7F)),
	 ('Latin Extended-D',                         (0xA720, 0xA7FF))),
	(('Greek Extended',                           (0x1F00, 0x1FFF)),),
	(('General Punctuation',                      (0x2000, 0x206F)),
	 ('Supplemental Punctuation',                 (0x2E00, 0x2E7F))),
	(('Superscripts And Subscripts',              (0x2070, 0x209F)),),
	(('Currency Symbols',                         (0x20A0, 0x20CF)),),
	(('Combining Diacritical Marks For Symbols',  (0x20D0, 0x20FF)),),
	(('Letterlike Symbols',                       (0x2100, 0x214F)),),
	(('Number Forms',                             (0x2150, 0x218F)),),
	(('Arrows',                                   (0x2190, 0x21FF)),
	 ('Supplemental Arrows-A',                    (0x27F0, 0x27FF)),
	 ('Supplemental Arrows-B',                    (0x2900, 0x297F)),
	 ('Miscellaneous Symbols and Arrows',         (0x2B00, 0x2BFF))),
	(('Mathematical Operators',                   (0x2200, 0x22FF)),
	 ('Supplemental Mathematical Operators',      (0x2A00, 0x2AFF)),
	 ('Miscellaneous Mathematical Symbols-A',     (0x27C0, 0x27EF)),
	 ('Miscellaneous Mathematical Symbols-B',     (0x2980, 0x29FF))),
	(('Miscellaneous Technical',                  (0x2300, 0x23FF)),),
	(('Control Pictures',                         (0x2400, 0x243F)),),
	(('Optical Character Recognition',            (0x2440, 0x245F)),),
	(('Enclosed Alphanumerics',                   (0x2460, 0x24FF)),),
	(('Box Drawing',                              (0x2500, 0x257F)),),
	(('Block Elements',                           (0x2580, 0x259F)),),
	(('Geometric Shapes',                         (0x25A0, 0x25FF)),),
	(('Miscellaneous Symbols',                    (0x2600, 0x26FF)),),
	(('Dingbats',                                 (0x2700, 0x27BF)),),
	(('CJK Symbols And Punctuation',              (0x3000, 0x303F)),),
	(('Hiragana',                                 (0x3040, 0x309F)),),
	(('Katakana',                                 (0x30A0, 0x30FF)),
	 ('Katakana Phonetic Extensions',             (0x31F0, 0x31FF))),
	(('Bopomofo',                                 (0x3100, 0x312F)),
	 ('Bopomofo Extended',                        (0x31A0, 0x31BF))),
	(('Hangul Compatibility Jamo',                (0x3130, 0x318F)),),
	(('Phags-pa',                                 (0xA840, 0xA87F)),),
	(('Enclosed CJK Letters And Months',          (0x3200, 0x32FF)),),
	(('CJK Compatibility',                        (0x3300, 0x33FF)),),
	(('Hangul Syllables',                         (0xAC00, 0xD7AF)),),
	(('Non-Plane 0 *',                            (0xD800, 0xDFFF)),),
	(('Phoenician',                               (0x10900, 0x1091F)),),
	(('CJK Unified Ideographs',                   (0x4E00, 0x9FFF)),
	 ('CJK Radicals Supplement',                  (0x2E80, 0x2EFF)),
	 ('Kangxi Radicals',                          (0x2F00, 0x2FDF)),
	 ('Ideographic Description Characters',       (0x2FF0, 0x2FFF)),
	 ('CJK Unified Ideographs Extension A',       (0x3400, 0x4DBF)),
	 ('CJK Unified Ideographs Extension B',       (0x20000, 0x2A6DF)),
	 ('Kanbun',                                   (0x3190, 0x319F))),
	(('Private Use Area (plane 0)',               (0xE000, 0xF8FF)),),
	(('CJK Strokes',                              (0x31C0, 0x31EF)),
	 ('CJK Compatibility Ideographs',             (0xF900, 0xFAFF)),
	 ('CJK Compatibility Ideographs Supplement',  (0x2F800, 0x2FA1F))),
	(('Alphabetic Presentation Forms',            (0xFB00, 0xFB4F)),),
	(('Arabic Presentation Forms-A',              (0xFB50, 0xFDFF)),),
	(('Combining Half Marks',                     (0xFE20, 0xFE2F)),),
	(('Vertical Forms',                           (0xFE10, 0xFE1F)),
	 ('CJK Compatibility Forms',                  (0xFE30, 0xFE4F))),
	(('Small Form Variants',                      (0xFE50, 0xFE6F)),),
	(('Arabic Presentation Forms-B',              (0xFE70, 0xFEFF)),),
	(('Halfwidth And Fullwidth Forms',            (0xFF00, 0xFFEF)),),
	(('Specials',                                 (0xFFF0, 0xFFFF)),),
	(('Tibetan',                                  (0x0F00, 0x0FFF)),),
	(('Syriac',                                   (0x0700, 0x074F)),),
	(('Thaana',                                   (0x0780, 0x07BF)),),
	(('Sinhala',                                  (0x0D80, 0x0DFF)),),
	(('Myanmar',                                  (0x1000, 0x109F)),),
	(('Ethiopic',                                 (0x1200, 0x137F)),
	 ('Ethiopic Supplement',                      (0x1380, 0x139F)),
	 ('Ethiopic Extended',                        (0x2D80, 0x2DDF))),
	(('Cherokee',                                 (0x13A0, 0x13FF)),),
	(('Unified Canadian Aboriginal Syllabics',    (0x1400, 0x167F)),),
	(('Ogham',                                    (0x1680, 0x169F)),),
	(('Runic',                                    (0x16A0, 0x16FF)),),
	(('Khmer',                                    (0x1780, 0x17FF)),
	 ('Khmer Symbols',                            (0x19E0, 0x19FF))),
	(('Mongolian',                                (0x1800, 0x18AF)),),
	(('Braille Patterns',                         (0x2800, 0x28FF)),),
	(('Yi Syllables',                             (0xA000, 0xA48F)),
	 ('Yi Radicals',                              (0xA490, 0xA4CF))),
	(('Tagalog',                                  (0x1700, 0x171F)),
	 ('Hanunoo',                                  (0x1720, 0x173F)),
	 ('Buhid',                                    (0x1740, 0x175F)),
	 ('Tagbanwa',                                 (0x1760, 0x177F))),
	(('Old Italic',                               (0x10300, 0x1032F)),),
	(('Gothic',                                   (0x10330, 0x1034F)),),
	(('Deseret',                                  (0x10400, 0x1044F)),),
	(('Byzantine Musical Symbols',                (0x1D000, 0x1D0FF)),
	 ('Musical Symbols',                          (0x1D100, 0x1D1FF)),
	 ('Ancient Greek Musical Notation',           (0x1D200, 0x1D24F))),
	(('Mathematical Alphanumeric Symbols',        (0x1D400, 0x1D7FF)),),
	(('Private Use (plane 15)',                   (0xFF000, 0xFFFFD)),
	 ('Private Use (plane 16)',                   (0x100000, 0x10FFFD))),
	(('Variation Selectors',                      (0xFE00, 0xFE0F)),
	 ('Variation Selectors Supplement',           (0xE0100, 0xE01EF))),
	(('Tags',                                     (0xE0000, 0xE007F)),),
	(('Limbu',                                    (0x1900, 0x194F)),),
	(('Tai Le',                                   (0x1950, 0x197F)),),
	(('New Tai Lue',                              (0x1980, 0x19DF)),),
	(('Buginese',                                 (0x1A00, 0x1A1F)),),
	(('Glagolitic',                               (0x2C00, 0x2C5F)),),
	(('Tifinagh',                                 (0x2D30, 0x2D7F)),),
	(('Yijing Hexagram Symbols',                  (0x4DC0, 0x4DFF)),),
	(('Syloti Nagri',                             (0xA800, 0xA82F)),),
	(('Linear B Syllabary',                       (0x10000, 0x1007F)),
	 ('Linear B Ideograms',                       (0x10080, 0x100FF)),
	 ('Aegean Numbers',                           (0x10100, 0x1013F))),
	(('Ancient Greek Numbers',                    (0x10140, 0x1018F)),),
	(('Ugaritic',                                 (0x10380, 0x1039F)),),
	(('Old Persian',                              (0x103A0, 0x103DF)),),
	(('Shavian',                                  (0x10450, 0x1047F)),),
	(('Osmanya',                                  (0x10480, 0x104AF)),),
	(('Cypriot Syllabary',                        (0x10800, 0x1083F)),),
	(('Kharoshthi',                               (0x10A00, 0x10A5F)),),
	(('Tai Xuan Jing Symbols',                    (0x1D300, 0x1D35F)),),
	(('Cuneiform',                                (0x12000, 0x123FF)),
	 ('Cuneiform Numbers and Punctuation',        (0x12400, 0x1247F))),
	(('Counting Rod Numerals',                    (0x1D360, 0x1D37F)),),
	(('Sundanese',                                (0x1B80, 0x1BBF)),),
	(('Lepcha',                                   (0x1C00, 0x1C4F)),),
	(('Ol Chiki',                                 (0x1C50, 0x1C7F)),),
	(('Saurashtra',                               (0xA880, 0xA8DF)),),
	(('Kayah Li',                                 (0xA900, 0xA92F)),),
	(('Rejang',                                   (0xA930, 0xA95F)),),
	(('Cham',                                     (0xAA00, 0xAA5F)),),
	(('Ancient Symbols',                          (0x10190, 0x101CF)),),
	(('Phaistos Disc',                            (0x101D0, 0x101FF)),),
	(('Carian',                                   (0x102A0, 0x102DF)),
	 ('Lycian',                                   (0x10280, 0x1029F)),
	 ('Lydian',                                   (0x10920, 0x1093F))),
	(('Domino Tiles',                             (0x1F030, 0x1F09F)),
	 ('Mahjong Tiles',                            (0x1F000, 0x1F02F))),
)


_unicodeRangeSets = []

def _getUnicodeRangeSets():
	# build the sets of codepoints for each unicode range bit, and cache result
	global _unicodeRangeSets
	if not _unicodeRangeSets:
		for bit, blocks in enumerate(OS2_UNICODE_RANGES):
			rangeset = set()
			for _, (start, stop) in blocks:
				rangeset.update(set(range(start, stop+1)))
			if bit == 57:
				# The spec says that bit 57 ("Non Plane 0") implies that there's
				# at least one codepoint beyond the BMP; so I also include all
				# the non-BMP codepoints here
				rangeset.update(set(range(0x10000, 0x110000)))
			_unicodeRangeSets.append(rangeset)
	return _unicodeRangeSets


def intersect(unicodes, inverse=False):
	""" Intersect a sequence of (int) Unicode codepoints with the Unicode block
	ranges defined in the OpenType specification v1.7, and return the set of
	'ulUnicodeRanges' bits for which there is at least ONE intersection.
	If 'inverse' is True, return the the bits for which there is NO intersection.

	>>> intersect([0x0410]) == {9}
	True
	>>> intersect([0x0410, 0x1F000]) == {9, 57, 122}
	True
	>>> intersect([0x0410, 0x1F000], inverse=True) == (set(range(123)) - {9, 57, 122})
	True
	"""
	unicodes = set(unicodes)
	uniranges = _getUnicodeRangeSets()
	bits = set([
		bit for bit, unirange in enumerate(uniranges)
		if not unirange.isdisjoint(unicodes) ^ inverse])
	return bits


if __name__ == "__main__":
	import doctest, sys
	sys.exit(doctest.testmod().failed)
