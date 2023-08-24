"""

	Metadata:

		File: test_workflow.py
		Project: imageinn
		Created Date: 12 Aug 2023
		Author: Jess Mann
		Email: jess.a.mann@gmail.com

		-----

		Last Modified: Wed Aug 23 2023
		Modified By: Jess Mann

		-----

		Copyright (c) 2023 Jess Mann
"""
import os
import tempfile
import unittest
from unittest.mock import patch
import subprocess
import shutil

from scripts.import_sd.workflow import Workflow
from scripts.import_sd.photo import Photo
from scripts.import_sd.validator import Validator
from scripts.import_sd.sd import SDCard
from scripts.import_sd.queue import Queue
from scripts.import_sd.operations import CopyOperation

class TestWorkflow(unittest.TestCase):
	def setUp(self):
		# Paths
		self.data_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'data')
		self.test_data_path = os.path.join(self.data_path, 'test_data')
		self.sample_image_path = os.path.join(self.data_path, "_ARW_2544.arw")
		self.sd_card_path = os.path.join(self.test_data_path, 'sd_card')
		self.base_path = os.path.join(self.test_data_path, 'network')
		self.jpg_path = os.path.join(self.test_data_path, 'jpgs')
		self.empty_path = os.path.join(self.test_data_path, 'empty')
		self.backup_path = os.path.join(self.test_data_path, 'backup_network')
		self.list_path = os.path.join(self.test_data_path, 'file_list.txt')
		
		# Ensure sd_card_path, network_path and backup_network_path all exist
		os.makedirs(self.data_path, exist_ok=True)
		os.makedirs(self.test_data_path, exist_ok=True)
		os.makedirs(self.sd_card_path, exist_ok=True)
		os.makedirs(self.base_path, exist_ok=True)
		os.makedirs(self.jpg_path, exist_ok=True)
		os.makedirs(self.empty_path, exist_ok=True)
		os.makedirs(self.backup_path, exist_ok=True)
		self.temp_dir = tempfile.mkdtemp()

		self.files = [
			os.path.join(self.sd_card_path, "img_001.jpg"),
			os.path.join(self.sd_card_path, "img_002.jpg"),
			os.path.join(self.sd_card_path, "img_003.jpg"),
			os.path.join(self.base_path, "img_001.jpg"),
			os.path.join(self.base_path, "img_002.jpg"),
		]
		self.file_contents = [
			"test data",
			"test data",
			"test data",
			"test data",
			"different data",
		]

		# Create files
		for file, contents in zip(self.files, self.file_contents):
			with open(file, 'w') as f:
				f.write(contents)

		with open(self.list_path, 'w') as f:
			for file in self.files:
				f.write(file + '\n')

		self.sd_card = SDCard(self.sd_card_path)
		self.workflow = Workflow(self.base_path, self.jpg_path, self.backup_path, 'arw', self.sd_card)

	def tearDown(self):
		for file in self.files:
			os.remove(file)
		shutil.rmtree(self.temp_dir)
		shutil.rmtree(self.test_data_path)

	def _same_path(self, path1, path2):
		"""
		Check that the paths are the same, after being normalized and removing the trailing slash
		"""
		return os.path.normpath(path1).rstrip('/') == os.path.normpath(path2).rstrip('/')

	def test_init(self):
		self.assertTrue(self._same_path(self.workflow.base_path, self.base_path), msg="base_path not set correctly")
		self.assertTrue(self._same_path(self.workflow.jpg_path, self.jpg_path), msg="jpg_path not set correctly")
		self.assertTrue(self._same_path(self.workflow.backup_path, self.backup_path), msg="backup_path not set correctly")
		self.assertEqual(self.workflow.sd_card, self.sd_card, msg="sd_card not set correctly")
		self.assertIsInstance(self.workflow.sd_card, SDCard, msg="sd_card not set correctly")

	def test_sd_card_property(self):
		self.assertEqual(self.workflow.sd_card, self.sd_card, msg="sd_card not set correctly")
		self.assertTrue(self._same_path(self.workflow.sd_card.path, self.sd_card.path), msg="sd_card not set correctly")
		self.assertIsInstance(self.workflow.sd_card, SDCard, msg="sd_card is not an SD Card")

		with patch.object(os.path, 'exists', return_value=False):
			with self.assertRaises(FileNotFoundError):
				_ = Workflow(self.base_path, self.jpg_path, self.backup_path).sd_card

	def test_path_properties(self):
		# Valid path
		self.workflow.base_path = self.empty_path
		self.assertTrue(self._same_path(self.workflow.base_path, os.path.join(self.empty_path, '')), msg="base_path not set correctly")

		# Invalid path
		with self.assertRaises(FileNotFoundError):
			self.workflow.base_path = os.path.join(self.empty_path, 'non_existent_folder')

		# Test similar behavior for jpg_path and backup_path
		self.workflow.jpg_path = self.empty_path
		self.assertTrue(self._same_path(self.workflow.jpg_path, os.path.join(self.empty_path, '')), msg="jpg_path not set correctly")

		with self.assertRaises(FileNotFoundError):
			self.workflow.jpg_path = os.path.join(self.empty_path, 'non_existent_folder')

		self.workflow.backup_path = self.empty_path
		self.assertTrue(self._same_path(self.workflow.backup_path, os.path.join(self.empty_path, '')), msg="backup_path not set correctly")

		with self.assertRaises(FileNotFoundError):
			self.workflow.backup_path = os.path.join(self.empty_path, 'non_existent_folder')

	def test_bucket_path_property_fail(self):
		with patch.object(Validator, 'is_writeable', return_value=False):
			with self.assertRaises(PermissionError):
				_ = self.workflow.bucket_path

	def test_run(self):
		with patch.object(Validator, 'is_dir', return_value=True), \
			 patch.object(Validator, 'is_writeable', return_value=True), \
			 patch.object(self.workflow, 'queue_files', return_value=Queue()), \
			 patch.object(self.workflow, 'copy_from_list', return_value=True), \
			 patch.object(self.workflow, 'organize_files', return_value={'/a/img.jpg': '/b/img.jpg'}), \
			 patch.object(Validator, 'validate_checksum_list', return_value=True):
			# Successful run
			self.assertTrue(self.workflow.run(), msg="Workflow should have run successfully")

		with patch.object(Validator, 'is_dir', return_value=False):
			# Invalid paths
			self.assertFalse(self.workflow.run(), msg="Workflow should have failed due to invalid paths")

		with patch.object(Validator, 'is_dir', return_value=True), \
			 patch.object(Validator, 'is_writeable', return_value=False):
			# Unwritable paths
			self.assertFalse(self.workflow.run(), msg="Workflow should have failed due to unwritable paths")

	def test_copy_from_list(self):
		list_path = self.list_path
		destination_path = self.backup_path
		checksums_before = {"file1": "checksum1"}
		operation = CopyOperation.TERACOPY

		with patch.object(self.workflow, 'teracopy_from_list', return_value=True), \
			 patch.object(Validator, 'validate_checksums', return_value=True):
			self.assertTrue(self.workflow.copy_from_list(list_path, destination_path, checksums_before, operation), msg="Copy should have succeeded")

		# Copy failure
		with patch.object(self.workflow, 'teracopy_from_list', return_value=False), \
			 patch.object(Validator, 'validate_checksums', return_value=True), \
			 patch('builtins.input', return_value='y'):
			self.assertFalse(self.workflow.copy_from_list(list_path, destination_path, checksums_before, operation), msg="Copy should have failed")

		# Checksum validation failure
		with patch.object(self.workflow, 'teracopy_from_list', return_value=True), \
			 patch.object(Validator, 'validate_checksums', return_value=False), \
			 patch('builtins.input', return_value='y'):
			self.assertFalse(self.workflow.copy_from_list(list_path, destination_path, checksums_before, operation), msg="Checksum validation should have failed")

	def test_rsync_fail(self):
		source_path = self.sd_card_path
		destination_path = os.path.join(self.empty_path, '/destination/')
		self.workflow.rsync(source_path, destination_path)

		# Rsync failed
		with patch.object(subprocess, 'check_call', side_effect=subprocess.CalledProcessError(-1, "")):
			self.assertFalse(self.workflow.rsync(source_path, destination_path), msg="Rsync should have failed")

	def test_rsync_succeed(self):
		source_path = self.sd_card_path
		destination_path = self.base_path
		self.workflow.rsync(source_path, destination_path)

		with patch.object(subprocess, 'check_call', return_value = 1000):
			self.assertTrue(self.workflow.rsync(source_path, destination_path), msg="Rsync should have succeeded")

	def test_teracopy_succeed(self):
		source_path = self.sd_card_path
		destination_path = self.base_path
		with patch.object(subprocess, 'check_call', return_value = 1000):
			self.assertTrue(self.workflow.teracopy(source_path, destination_path), msg="Teracopy should have succeeded")

	def test_teracopy_fail(self):
		source_path = self.sd_card_path
		destination_path = os.path.join(self.empty_path, '/destination/')
		# Teracopy failed
		with patch('subprocess.check_call', side_effect=subprocess.CalledProcessError(-1, "")):
			self.assertFalse(self.workflow.teracopy(source_path, destination_path), msg="Teracopy should have failed")

	def test_queue_files(self):
		# Test the logic inside queue_files
		files = self.workflow.queue_files()
		self.assertIsInstance(files, Queue, msg="Files should be a Queue.")

	def test_organize_files(self):
		# Create files in the bucket, so they can be organized
		files = [ 'img_001.jpg', 'img_002.jpg', 'img_003.jpg', 'img_001.arw' ]
		paths = []
		for file in files:
			path = os.path.join(self.workflow.bucket_path, file)
			with open(path, 'w') as f:
				paths.append(path)
				f.write(path)

		results = self.workflow.organize_files()
		self.assertIsInstance(results, dict, msg="Results should be a dict.")
		# Contents should include all of self.files as keys, with a new path as values
		self.assertEqual(len(results.keys()), len(files), msg="Results should include all files.")
		for file in paths:
			self.assertIn(file, results.keys(), msg="Results should include all files.")
			self.assertIsInstance(results[file], str, msg="Results should include all files.")
			# Contents of the copied file should be the same as the original
			with open(results[file], 'r') as f:
				self.assertEqual(f.read(), file, msg="Contents of the copied file should be the same as the original.")