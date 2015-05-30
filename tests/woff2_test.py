from __future__ import print_function, division, absolute_import, unicode_literals
from fontTools.misc.py23 import *
from fontTools.ttLib import TTFont, TTLibError
from fontTools.ttLib import woff2
import unittest


test_font = 'data/Lobster.ttx'


def setUpModule():
	""" called once, before anything else in this module """
	pass


def tearDownModule():
	""" called once, before anything else in this module """
	pass


class WOFF2ReaderTest(unittest.TestCase):

	@classmethod
	def setUpClass(cls):
		""" called once, before any tests """
		ttx = TTFont(None, recalcBBoxes=False, recalcTimestamp=False)
		ttx.importXML(test_font, quiet=True)
		ttx.flavor = "woff2"
		cls.file = StringIO()
		ttx.save(cls.file, reorderTables=False)

	@classmethod
	def tearDownClass(cls):
		""" called once, after all tests, if setUpClass successful """
		pass

	def setUp(self):
		""" called multiple times, before every test method """
		self.file.seek(0)

	def tearDown(self):
		""" called multiple times, after every test method """

	def test_bad_signature(self):
		with self.assertRaises(TTLibError):
			woff2.WOFF2Reader(StringIO(b'\xff\xff\xff\xff\xff'))

	def test_not_enough_data(self):
		incomplete_dir = self.file.read(47)
		with self.assertRaises(TTLibError):
			woff2.WOFF2Reader(StringIO(incomplete_dir))


class WOFF2WriterTest(unittest.TestCase):

	@classmethod
	def setUpClass(cls):
		""" called once, before any tests """
		pass

	@classmethod
	def tearDownClass(cls):
		""" called once, after all tests, if setUpClass successful """
		pass

	def setUp(self):
		""" called multiple times, before every test method """
		pass

	def tearDown(self):
		""" called multiple times, after every test method """


class WOFF2DirectoryEntryTest(unittest.TestCase):

	@classmethod
	def setUpClass(cls):
		""" called once, before any tests """
		pass

	@classmethod
	def tearDownClass(cls):
		""" called once, after all tests, if setUpClass successful """
		pass

	def setUp(self):
		""" called multiple times, before every test method """
		pass

	def tearDown(self):
		""" called multiple times, after every test method """


class WOFF2GlyfTableTest(unittest.TestCase):

	@classmethod
	def setUpClass(cls):
		""" called once, before any tests """
		pass

	@classmethod
	def tearDownClass(cls):
		""" called once, after all tests, if setUpClass successful """
		pass

	def setUp(self):
		""" called multiple times, before every test method """
		pass

	def tearDown(self):
		""" called multiple times, after every test method """


class WOFF2FlavorDataTest(unittest.TestCase):

	@classmethod
	def setUpClass(cls):
		""" called once, before any tests """
		pass

	@classmethod
	def tearDownClass(cls):
		""" called once, after all tests, if setUpClass successful """
		pass

	def setUp(self):
		""" called multiple times, before every test method """
		pass

	def tearDown(self):
		""" called multiple times, after every test method """


if __name__ == "__main__":
	unittest.main()
