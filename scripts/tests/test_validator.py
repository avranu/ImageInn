"""

	Metadata:

		File: test_validator.py
		Project: tests
		Created Date: 12 Aug 2023
		Author: Jess Mann
		Email: jess.a.mann@gmail.com

		-----

		Last Modified: Sat Aug 12 2023
		Modified By: Jess Mann

		-----

		Copyright (c) 2023 Jess Mann
"""
import unittest
import tempfile
import shutil
import os

from scripts.import_sd.workflow import Workflow
from scripts.import_sd.photo import Photo
from scripts.import_sd.validator import Validator
from scripts.import_sd.sd import SDCard
from scripts.import_sd.queue import Queue
from scripts.import_sd.operations import CopyOperation

class TestValidator(unittest.TestCase):

	def setUp(self):
		self.temp_dir = tempfile.mkdtemp()
		self.temp_file = os.path.join(self.temp_dir, 'temp_file.txt')
		with open(self.temp_file, 'w') as f:
			f.write("Test content")

	def tearDown(self):
		shutil.rmtree(self.temp_dir)

	def test_is_dir(self):
		self.assertTrue(Validator.is_dir(self.temp_dir))
		self.assertFalse(Validator.is_dir(self.temp_file))
		self.assertFalse(Validator.is_dir("/non/existent/path"))

	def test_is_file(self):
		self.assertTrue(Validator.is_file(self.temp_file))
		self.assertFalse(Validator.is_file(self.temp_dir))
		self.assertFalse(Validator.is_file("/non/existent/file.txt"))

	def test_is_writeable(self):
		self.assertTrue(Validator.is_writeable(self.temp_dir))
		self.assertTrue(Validator.is_writeable(self.temp_file))

	def test_ensure_dir(self):
		new_dir = os.path.join(self.temp_dir, 'new_dir')
		self.assertTrue(Validator.ensure_dir(new_dir))
		self.assertTrue(os.path.isdir(new_dir))
		self.assertTrue(Validator.ensure_dir(self.temp_dir))

	def test_calculate_checksums(self):
		checksums = Validator.calculate_checksums(self.temp_dir)
		self.assertEqual(len(checksums), 1)
		self.assertEqual(Validator.calculate_checksum(
			self.temp_file), list(checksums.values())[0])

	def test_calculate_checksum(self):
		checksum = Validator.calculate_checksum(self.temp_file)
		self.assertIsInstance(checksum, str)

	def test_compare_checksums(self):
		copy_file_path = os.path.join(self.temp_dir, 'copy_file.txt')
		shutil.copyfile(self.temp_file, copy_file_path)
		self.assertTrue(Validator.compare_checksums(self.temp_file, copy_file_path))

	def test_validate_checksums(self):
		copy_dir_path = tempfile.mkdtemp()
		checksums_before = Validator.calculate_checksums(self.temp_dir)
		shutil.copyfile(self.temp_file, os.path.join(copy_dir_path, 'temp_file.txt'))
		self.assertTrue(Validator.validate_checksums(
			checksums_before, copy_dir_path))
		shutil.rmtree(copy_dir_path)

	def test_validate_checksum_list(self):
		copy_file_path = os.path.join(self.temp_dir, 'copy_file.txt')
		shutil.copyfile(self.temp_file, copy_file_path)
		checksums_before = {
			self.temp_file: Validator.calculate_checksum(self.temp_file)}
		files = {self.temp_file: copy_file_path}
		self.assertTrue(Validator.validate_checksum_list(checksums_before, files))


if __name__ == '__main__':
	unittest.main()
