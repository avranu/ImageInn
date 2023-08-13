"""
	
	Metadata:
	
		File: test_workflow.py
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
import os
import unittest
from unittest.mock import MagicMock
import subprocess

from scripts.import_sd.workflow import Workflow
from scripts.import_sd.photo import Photo
from scripts.import_sd.validator import Validator
from scripts.import_sd.sd import SDCard
from scripts.import_sd.queue import Queue
from scripts.import_sd.operations import CopyOperation

class TestWorkflow(unittest.TestCase):
	def setUp(self):
		self.raw_path = "/path/to/raw"
		self.jpg_path = "/path/to/jpg"
		self.backup_path = "/path/to/backup"
		self.sd_card = SDCard("/path/to/sd_card")
		self.workflow = Workflow(self.raw_path, self.jpg_path, self.backup_path, sd_card=self.sd_card)

	def test_init(self):
		self.assertEqual(self.workflow.raw_path, self.raw_path)
		self.assertEqual(self.workflow.jpg_path, self.jpg_path)
		self.assertEqual(self.workflow.backup_path, self.backup_path)
		self.assertEqual(self.workflow.sd_card, self.sd_card)

	def test_sd_card_property(self):
		self.assertEqual(self.workflow.sd_card, self.sd_card)
		self.workflow.sd_card = "/new/path/to/sd_card"
		self.assertIsInstance(self.workflow.sd_card, SDCard)

		SDCard.get_media_dir = MagicMock(return_value=None)
		with self.assertRaises(FileNotFoundError):
			_ = Workflow(self.raw_path, self.jpg_path, self.backup_path).sd_card

	def test_path_properties(self):
		valid_path = "/valid/path"
		invalid_path = "/invalid/path"

		Validator.is_dir = MagicMock(return_value=True)
		self.workflow.raw_path = valid_path
		self.assertEqual(self.workflow.raw_path, valid_path)

		Validator.is_dir = MagicMock(return_value=False)
		with self.assertRaises(FileNotFoundError):
			self.workflow.raw_path = invalid_path

		# Test similar behavior for jpg_path and backup_path
		self.workflow.jpg_path = valid_path
		self.workflow.backup_path = valid_path
		self.assertEqual(self.workflow.jpg_path, valid_path)
		self.assertEqual(self.workflow.backup_path, valid_path)

		with self.assertRaises(FileNotFoundError):
			self.workflow.jpg_path = invalid_path

		with self.assertRaises(FileNotFoundError):
			self.workflow.backup_path = invalid_path

	def test_bucket_path_property(self):
		bucket_path = os.path.join(self.raw_path, 'Import Bucket')

		Validator.is_dir = MagicMock(return_value=False)
		Validator.is_writeable = MagicMock(return_value=True)
		os.makedirs = MagicMock()

		self.assertEqual(self.workflow.bucket_path, bucket_path)
		os.makedirs.assert_called_once_with(bucket_path, exist_ok=True)

		Validator.is_writeable = MagicMock(return_value=False)
		with self.assertRaises(PermissionError):
			_ = self.workflow.bucket_path

	def test_run(self):
		Validator.is_dir = MagicMock(return_value=True)
		Validator.is_writeable = MagicMock(return_value=True)
		self.workflow.queue_files = MagicMock(return_value=Queue())
		self.workflow.copy_from_list = MagicMock(return_value=True)
		self.workflow.organize_files = MagicMock(return_value={})
		Validator.validate_checksum_list = MagicMock(return_value=True)

		# Successful run
		self.assertTrue(self.workflow.run())

		# Invalid paths
		Validator.is_dir = MagicMock(return_value=False)
		self.assertFalse(self.workflow.run())

		# Unwritable paths
		Validator.is_dir = MagicMock(return_value=True)
		Validator.is_writeable = MagicMock(return_value=False)
		self.assertFalse(self.workflow.run())

	def test_copy_from_list(self):
		list_path = "list_path"
		destination_path = "destination_path"
		checksums_before = {"file1": "checksum1"}
		operation = CopyOperation.TERACOPY

		self.workflow.perform_copy = MagicMock(return_value=True)
		Validator.validate_checksums = MagicMock(return_value=True)
		self.assertTrue(self.workflow.copy_from_list(list_path, destination_path, checksums_before, operation))

		# Copy failure
		self.workflow.perform_copy = MagicMock(return_value=False)
		self.assertFalse(self.workflow.copy_from_list(list_path, destination_path, checksums_before, operation))

		# Checksum validation failure
		self.workflow.perform_copy = MagicMock(return_value=True)
		Validator.validate_checksums = MagicMock(return_value=False)
		self.assertFalse(self.workflow.copy_from_list(list_path, destination_path, checksums_before, operation))

	def test_rsync(self):
		source_path = "source_path"
		destination_path = "destination_path"
		self.workflow.rsync(source_path, destination_path)

		# Rsync failed
		subprocess.check_call = MagicMock(side_effect=[subprocess.CalledProcessError(-1, ""), subprocess.CalledProcessError(-1, ""), True])
		self.assertFalse(self.workflow.rsync(source_path, destination_path))

	def test_teracopy(self):
		source_path = "source_path"
		destination_path = "destination_path"
		subprocess.check_call = MagicMock(return_value=True)

		self.assertTrue(self.workflow.teracopy(source_path, destination_path))
		# Teracopy failed
		subprocess.check_call = MagicMock(side_effect=subprocess.CalledProcessError(-1, ""))
		self.assertFalse(self.workflow.teracopy(source_path, destination_path))

	def test_queue_files(self):
		# Simulate the behavior for testing
		self.sd_card.walk = os.walk
		photo = Photo("photo_path.arw")
		Photo.is_jpg = MagicMock(return_value=False)

		self.workflow.generate_path = MagicMock(return_value="final_path")
		os.path.exists = MagicMock(return_value=False)
		photo.matches = MagicMock(return_value=False)

		# Test the logic inside queue_files
		files = self.workflow.queue_files()
		self.assertIsInstance(files, Queue)

	def test_organize_files(self):
		# Test organizing files
		file_path = "/path/to/file.arw"
		new_file_path = "/new/path/to/file.arw"

		os.walk = MagicMock(return_value=[("/path/to", [], ["file.arw"])])
		self.workflow.generate_path = MagicMock(return_value=new_file_path)
		Validator.compare_checksums = MagicMock(return_value=False)
		os.makedirs = MagicMock()
		os.rename = MagicMock()

		results = self.workflow.organize_files()
		self.assertEqual(results, {file_path: new_file_path})

	def test_generate_name(self):
		photo = Photo("photo_path.arw")
		photo.date = MagicMock()
		photo.camera = "camera"
		photo.number = "1234"
		photo.exposure_bias = "2"
		photo.brightness = "10"
		photo.iso = "800"
		photo.ss = "1/100"
		photo.lens = "lens"
		photo.extension = "arw"

		# Test generating the name
		name = self.workflow.generate_name(photo)
		short_name = self.workflow.generate_name(photo, short=True)
		self.assertIn("1234", name)
		self.assertIn("1234", short_name)

	def test_generate_path(self):
		photo = Photo("photo_path.arw")
		photo.date = MagicMock()
		photo.extension = "arw"

		# Test generating the path
		path = self.workflow.generate_path(photo)
		self.assertIn(self.raw_path, path)
		self.assertIn("arw", path)

	def test_ask_user_continue(self):
		# Simulate user choice
		input = MagicMock(return_value="y")
		self.assertTrue(self.workflow.ask_user_continue())

		input = MagicMock(return_value="n")
		with self.assertRaises(KeyboardInterrupt):
			self.workflow.ask_user_continue()

if __name__ == "__main__":
	unittest.main()
