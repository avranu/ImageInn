import datetime
import logging
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch, MagicMock, mock_open
from scripts.import_sd import SDCards

class TestSDCards(unittest.TestCase):

	def setUp(self):
		self.sd_cards = SDCards()

		# Paths
		self.data_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'data')
		self.test_data_path = os.path.join(self.data_path, 'test_data')
		self.sample_image_path = os.path.join(self.data_path, "_ARW_2544.arw")
		self.sd_card_path = os.path.join(self.test_data_path, 'sd_card')
		self.network_path = os.path.join(self.test_data_path, 'network')
		self.backup_network_path = os.path.join(self.test_data_path, 'backup_network')
		# Ensure sd_card_path, network_path and backup_network_path all exist
		os.makedirs(self.sd_card_path)
		os.makedirs(self.network_path)
		os.makedirs(self.backup_network_path)
		self.temp_dir = tempfile.mkdtemp()

	def tearDown(self):
		shutil.rmtree(self.temp_dir)
		# Remove the test_data directory and its contents
		shutil.rmtree(self.test_data_path)

	def _create_file(self, path : str = None) -> str:
		if path is None:
			path = self.sd_card_path
		# Create a file to copy
		filepath = os.path.join(path, "img_001.jpg")
		with open(filepath, "w") as f:
			f.write("test data")
		return filepath
	
	def test_the_test(self):
		"""
		Test this unit test to be sure we are doing what we expect
		"""
		# Verify that each path is different
		self.assertNotEqual(self.sd_card_path, self.network_path, msg="SD card path and network path should be different")
		self.assertNotEqual(self.sd_card_path, self.backup_network_path, msg="SD card path and backup network path should be different")
		self.assertNotEqual(self.network_path, self.backup_network_path, msg="Network path and backup network path should be different")

		# Verify that no files exist at any of our paths (this is testing our test)
		for directory in [self.sd_card_path, self.network_path, self.backup_network_path]:
			files = os.listdir(directory)
			self.assertEqual(len(files), 0, msg="Directory should be empty. Cannot run test. Dir = {}, Files = {}".format(directory, files))

		filepath = self._create_file()
		filename = os.path.basename(filepath)
		self.assertGreater(len(filename), 0, msg="Filename should be greater than 0 characters: {}".format(filename))

		# Verify that the file was created
		self.assertTrue(os.path.isfile(filepath), msg="File should have been created at {}".format(filepath))
		files = os.listdir(self.sd_card_path)
		self.assertEqual(len(files), 1, msg="SD card should have one file. File list: {}".format(files))

	def test_teardown(self):
		""" 
		Run the test again, verifying that teardown reset everything.
		"""
		self.test_the_test()

	@patch("os.name", "nt")
	def test_get_media_dir_windows(self):
		self.assertEqual(self.sd_cards.get_media_dir(), 'D:\\')

	@patch("os.path.exists", return_value=False)
	def test_get_media_dir_unknown(self, mock_exists):
		with self.assertRaises(FileNotFoundError):
			self.sd_cards.get_media_dir()

	def test_is_path_valid_invalid(self):
		with patch("os.path.exists", return_value=False):
			self.assertFalse(self.sd_cards.is_path_valid("/invalid/path"))

	def test_is_path_valid_not_a_directory(self):
		with patch("os.path.exists", return_value=True), patch("os.path.isdir", return_value=False):
			self.assertFalse(self.sd_cards.is_path_valid("/not/a/directory"))

	def test_is_path_valid_true(self):
		with patch("os.path.exists", return_value=True), patch("os.path.isdir", return_value=True):
			self.assertTrue(self.sd_cards.is_path_valid("/valid/path"))

	def test_is_path_writable_false(self):
		with patch("os.access", return_value=False):
			self.assertFalse(self.sd_cards.is_path_writable("/non/writable/path"))

	def test_is_path_writable_true(self):
		with patch("os.access", return_value=True):
			self.assertTrue(self.sd_cards.is_path_writable("/writable/path"))

	def test_calculate_single_checksum(self):
		# Create a new file in self.network_path to calculate a checksum
		filepath = self._create_file()

		result = self.sd_cards.calculate_single_checksum(filepath)
		self.assertIsNotNone(result, msg="Checksum should not be None")
		self.assertGreater(len(result), 5, msg="Checksum should be longer than 5 characters")

		# Change the file contents, and check that the checksum changes
		with open(filepath, "w") as f:
			f.write("different test data")

		result2 = self.sd_cards.calculate_single_checksum(filepath)
		self.assertNotEqual(result, result2, msg="Checksums should be different for different file contents")

	@patch("os.path.isfile", return_value=True)
	@patch("os.access", return_value=True)
	@patch("builtins.open", mock_open(read_data=b"test data"))
	@patch("os.walk", return_value=[("/valid/path", ["dir1", "dir2"], ["file1", "file2"])])
	@patch.object(SDCards, "check_sd_path", return_value=True)
	@patch.object(SDCards, "is_path_valid", return_value=True)
	def test_calculate_checksums(self, mock_isfile, mock_access, mock_walk, mock_check_sd_path, mock_is_path_valid):
		checksums = self.sd_cards.calculate_checksums("/valid/path")
		self.assertTrue("/valid/path/file1" in checksums)
		self.assertTrue("/valid/path/file2" in checksums)

	def test_calculate_checksums_full(self):
		"""
		Instead of mocking, create a file and check that we are getting something unique for various file contents.
		"""
		# Create a file with a known checksum
		filepath = self._create_file()
		directory = os.path.dirname(filepath)
		results = self.sd_cards.calculate_checksums(directory)
		self.assertEqual(len(results), 1, msg="Should only be one result")

		checksum = results[filepath]
		self.assertIsNotNone(checksum, msg="Checksum should not be None")
		self.assertGreater(len(checksum), 5, msg="Checksum should be longer than 5 characters")

		# Modify the file so it gets a different checksum
		with open(filepath, "w") as f:
			f.write("different test data")
		results = self.sd_cards.calculate_checksums(directory)
		self.assertEqual(len(results), 1, msg="Should only be one result")

		checksum2 = results[filepath]
		self.assertNotEqual(checksum, checksum2, msg="Checksums should be different for different file contents")

	def test_calculate_checksums_invalid_path(self):
		with self.assertRaises(FileNotFoundError):
			self.sd_cards.calculate_checksums("/invalid/path")

	def test_calculate_checksums_not_a_file(self):
		with patch("os.path.isfile", return_value=False):
			with self.assertRaises(FileNotFoundError):
				self.sd_cards.calculate_checksums("/not/a/file")

	@patch.object(SDCards, "perform_rsync", return_value=True)
	@patch.object(SDCards, "validate_checksums", return_value=True)
	@patch.object(SDCards, "check_sd_path", return_value=True)
	@patch.object(SDCards, "is_path_valid", return_value=True)
	@patch.object(SDCards, "is_path_writable", return_value=True)
	@patch("os.access", return_value=True)
	@patch("os.makedirs", return_value=True)
	def test_successful_copy_mock_all(self, mock_rsync, mock_validate, mock_check_sd_path, mock_is_path_valid, mock_is_path_writable, mock_access, mock_mkdirs):
		result = self.sd_cards.copy_sd_card("/valid/sd/card", "/valid/network/path", "/valid/backup/network/path")
		self.assertTrue(result)

	@patch.object(SDCards, "generate_name", return_value="20230809_ILCE-7RM4_2544_-1 0EV_-7 7B_6400ISO_0 1SS_SAMYANG AF 12mm F2 0.arw")
	@patch('builtins.input', return_value='y')
	def test_successful_copy(self, mock_input, mock_generate_name):
		filepath = self._create_file()
		filename = os.path.basename(filepath)

		result = self.sd_cards.copy_sd_card(self.sd_card_path, self.network_path, self.backup_network_path)
		self.assertTrue(result, msg="Copy should have succeeded: {}".format(result))
		# Original still exists
		self.assertTrue(os.path.isfile(filepath), msg="Original file should still exist at {}".format(filepath))
		# Contents not changed
		with open(filepath, "r") as f:
			contents = f.read()
			self.assertEqual(contents, "test data", msg="Original file contents should not have changed. Found {}".format(contents))

		# Check that the file was copied to the backup location
		backup_filepath = os.path.join(self.backup_network_path, filename)
		# Get all files at the backup_network_path
		files = os.listdir(self.backup_network_path)
		self.assertEqual(len(files), 2, msg="There should be two files at the backup path after copy (img + checksum.txt). File list: {}".format(files))
		self.assertTrue(os.path.isfile(backup_filepath), msg="Backup file should exist at {}".format(backup_filepath))
		with open(backup_filepath, "r") as f:
			contents = f.read()
			self.assertEqual(contents, "test data", msg="Backup file contents should match original. Found {}".format(contents))

		# Check that the file was copied to the primary location (under a YYYY/YYYY-mm-dd directory)
		new_path = os.path.join(self.network_path, datetime.datetime.now().strftime("%Y/%Y-%m-%d"))
		# Use the mock name for the filename
		new_filepath = os.path.join(new_path, mock_generate_name.return_value)
		files = os.listdir(new_path)
		self.assertEqual(len(files), 1, msg="There should be one file at the network path after copy. File list: {}".format(files))
		self.assertTrue(os.path.isfile(new_filepath), msg="New file should exist at {}".format(new_path))
		with open(os.path.join(new_path, new_filepath), "r") as f:
			contents = f.read()
			self.assertEqual(contents, "test data", msg="New file contents should match original. Found {}".format(contents))

	@patch.object(SDCards, "perform_rsync", return_value=True)
	@patch.object(SDCards, "validate_checksums", return_value=False)
	def test_checksum_mismatch_mock(self, mock_rsync, mock_validate):
		result = self.sd_cards.copy_sd_card("/valid/sd/card", "/valid/network/path", "/valid/backup/network/path")
		self.assertFalse(result)

	@patch.object(SDCards, "perform_rsync", return_value=False)
	def test_rsync_failure_mock(self, mock_rsync):
		result = self.sd_cards.copy_sd_card("/valid/sd/card", "/valid/network/path", "/valid/backup/network/path")
		self.assertFalse(result)

	@patch.object(SDCards, "calculate_checksums")
	@patch.object(SDCards, "perform_rsync", return_value=True)
	def test_no_modification_of_source_mock(self, mock_rsync, mock_checksum):
		# Mocking the checksum function to return different values will simulate file modification
		mock_checksum.side_effect = [{"file1": "checksum1"}, {"file1": "checksum2"}]
		result = self.sd_cards.copy_sd_card("/valid/sd/card", "/valid/network/path", "/valid/backup/network/path")
		self.assertFalse(result)

	@patch("shutil.disk_usage", return_value=(1000, 500, 500))
	@patch("os.walk", return_value=[("root", ["dir1", "dir2"], ["file1", "file2"])])
	@patch("os.path.isfile", return_value=True)
	@patch("os.access", return_value=True)
	@patch("os.path.exists", return_value=True)
	@patch.object(SDCards, "check_sd_path", return_value=True)
	@patch.object(SDCards, "is_path_valid", return_value=True)
	def test_get_info_mock(self, mock_isfile, mock_access, mock_walk, mock_disk_usage, mock_exists, mock_check_sd_path, mock_is_path_valid):
		info = self.sd_cards.get_info("/valid/sd/card")
		self.assertEqual(info.path, "/valid/sd/card")
		self.assertEqual(info.total, 1000)
		self.assertEqual(info.used, 500)
		self.assertEqual(info.free, 500)
		self.assertEqual(info.num_files, 2)
		self.assertEqual(info.num_dirs, 2)

	@patch("os.path.isfile", return_value=False)
	def test_calculate_checksum_file_not_found(self, mock_isfile):
		with self.assertRaises(FileNotFoundError):
			self.sd_cards.calculate_checksum("/invalid/path")

	@patch.object(subprocess, "check_call", side_effect=subprocess.CalledProcessError(-1, "rsync"))
	def test_perform_rsync_failure(self, mock_check_call):
		result = self.sd_cards.perform_rsync("/valid/sd/card", "/valid/network/path")
		self.assertFalse(result)
		
	@patch("os.path.isfile", return_value=True)
	@patch("os.access", return_value=True)
	@patch("os.path.exists", return_value=True)
	@patch.object(SDCards, "calculate_checksums", return_value={"file1": "checksum1"})
	@patch.object(SDCards, "check_sd_path", return_value=True)
	@patch.object(SDCards, "is_path_valid", return_value=True)
	@patch.object(SDCards, "generate_name", return_value="20230809_ILCE-7RM4_2544_-1 0EV_-7 7B_6400ISO_0 1SS_SAMYANG AF 12mm F2 0.arw")
	@patch('builtins.open', mock_open(read_data=b"checksum1"))
	def test_validate_checksums_missing_file(self, mock_isfile, mock_access, mock_exists, mock_checksum, mock_check_sd_path, mock_is_path_valid, mock_generate_name):
		# Simulating a situation where "file2" is missing after rsync
		result = self.sd_cards.validate_checksums({"file1": "checksum1", "file2": "checksum2"}, "/valid/network/path")
		self.assertFalse(result)

	@patch("os.path.isfile", return_value=True)
	@patch("os.access", return_value=True)
	@patch("os.path.exists", return_value=True)
	@patch.object(SDCards, "calculate_checksums", return_value={"file1": "checksum5", "file2": "checksum2"})
	@patch.object(SDCards, "check_sd_path", return_value=True)
	@patch.object(SDCards, "is_path_valid", return_value=True)
	@patch.object(SDCards, "generate_name", return_value="20230809_ILCE-7RM4_2544_-1 0EV_-7 7B_6400ISO_0 1SS_SAMYANG AF 12mm F2 0.arw")
	@patch('builtins.open', mock_open(read_data=b"checksum1"))
	def test_validate_checksums_mismatch_file(self, mock_isfile, mock_access, mock_exists, mock_checksum, mock_check_sd_path, mock_is_path_valid, mock_generate_name):
		# Simulating a situation where "file2" is missing after rsync
		result = self.sd_cards.validate_checksums({"file1": "checksum1", "file2": "checksum2"}, "/valid/network/path")
		self.assertFalse(result)

	@patch("os.path.isfile", return_value=True)
	@patch("os.access", return_value=True)
	@patch("os.path.exists", return_value=True)
	@patch.object(SDCards, "calculate_checksums", return_value={"file1": "checksum1", "file2": "checksum4"})
	@patch.object(SDCards, "check_sd_path", return_value=True)
	@patch.object(SDCards, "is_path_valid", return_value=True)
	@patch.object(SDCards, "generate_name", return_value="20230809_ILCE-7RM4_2544_-1 0EV_-7 7B_6400ISO_0 1SS_SAMYANG AF 12mm F2 0.arw")
	@patch('builtins.open', mock_open(read_data=b"checksum1"))
	def test_validate_checksums_mismatch_backup(self, mock_isfile, mock_access, mock_exists, mock_checksum, mock_check_sd_path, mock_is_path_valid, mock_generate_name):
		# Simulating a situation where "file2" is missing after rsync
		result = self.sd_cards.validate_checksums({"file1": "checksum1", "file2": "checksum2"}, "/valid/network/path")
		self.assertFalse(result)

	def test_get_file_extension(self):
		tests = {
			"file.txt": "txt",
			"file.tar.gz": "gz",
			"file.arw": "arw",
			"file.jpg": "jpg",
			"file": ""
		}

		for test_input, test_output in tests.items():
			result = self.sd_cards.get_file_extension(test_input)
			self.assertEqual(result, test_output, f"Failed to get file extension for {test_input}")

	def test_get_filename_number_suffix(self):
		tests = {
			'ABC_1234.JPG': 1234,
			'BCD_2345.ARW': 2345,
			'CDE_3456': 3456,
			'_DEF_4567.jpeg': 4567,
			'E_5678.jpg': 5678,
		}

		for test_input, test_output in tests.items():
			result = self.sd_cards.get_filename_number_suffix(test_input)
			self.assertEqual(result, test_output, f"Failed to get filename number suffix for {test_input}")

	def test_get_lens(self):
		result = self.sd_cards.get_lens(self.sample_image_path)
		self.assertEqual(result, "SAMYANG AF 12mm F2.0")

	def test_get_camera(self):
		result = self.sd_cards.get_camera_model(self.sample_image_path)
		self.assertEqual(result, "ILCE-7RM4")

	def test_get_iso_speed(self):
		result = self.sd_cards.get_iso_speed(self.sample_image_path)
		self.assertEqual(result, 6400)

	def test_get_brightness_value(self):
		result = self.sd_cards.get_brightness_value(self.sample_image_path)
		self.assertEqual(result, -7.7)

	def test_get_exposure_bias(self):
		result = self.sd_cards.get_exposure_bias(self.sample_image_path)
		self.assertEqual(result, -1.0)

	def test_get_shutter_speed(self):
		result = self.sd_cards.get_shutter_speed(self.sample_image_path)
		self.assertEqual(result, 0.1)

	def test_generate_name(self):
		name = self.sd_cards.generate_name(self.sample_image_path)
		# Name begins with the current date
		date = datetime.datetime.now().strftime("%Y%m%d")
		filename = f"{date}_ILCE-7RM4_2544_-1 0EV_-7 7B_6400ISO_0 1SS_SAMYANG AF 12mm F2 0.arw"
		self.assertEqual(name, filename)

	def test_generate_path(self):
		path = self.sd_cards.generate_path(self.sample_image_path, "/valid/network/path")

		# Name begins with the current date
		date = datetime.datetime.now()
		filename = f"{date.strftime('%Y%m%d')}_ILCE-7RM4_2544_-1 0EV_-7 7B_6400ISO_0 1SS_SAMYANG AF 12mm F2 0.arw"
		filepath = f"/valid/network/path/{date.strftime('%Y')}/{date.strftime('%Y-%m-%d')}/{filename}"
		self.assertEqual(path, filepath)

	def test_generate_truncated_path(self):
		# Our normally expected filepath
		# Name begins with the current date
		date = datetime.datetime.now()
		filename = f"{date.strftime('%Y%m%d')}_ILCE-7RM4_2544_-1 0EV_-7 7B_6400ISO_0 1SS_SAMYANG AF 12mm F2 0.arw"
		filepath = f"{date.strftime('%Y')}/{date.strftime('%Y-%m-%d')}/{filename}"

		# (destination network path size, target file path, expected output)
		# Note: The expected output is None if the path is too long, and an error is expected
		tests = [
			# Not truncated
			(10, self.sample_image_path, filepath),
			(100, self.sample_image_path, filepath),
			# Path too long => shortened filename (not truncated)
			(185, self.sample_image_path, f"{date.strftime('%Y')}/{date.strftime('%Y-%m-%d')}/2544_-1 0EV_-7 7B_6400ISO_0 1SS.arw"),
			# Path even longer => truncated filename
			(200, self.sample_image_path, f"{date.strftime('%Y')}/{date.strftime('%Y-%m-%d')}/2544_-1 0EV_-7 7B_6400---.arw"),
			# Path way too long => fail
			(250, self.sample_image_path, None),
		]

		i : int = 0
		for (path_size, target_file_path, expected_output) in tests:
			i+=1

			# Construct a sample path of the given size, including slashes
			network_path = "/".join(["a" * (path_size // 10)] * 10)

			if expected_output is None:
				with self.assertRaises(ValueError, msg=f"Failed (loop {i}) to raise ValueError for {target_file_path} with network path size {path_size}"):
					result = self.sd_cards.generate_path(target_file_path, network_path)
			else:
				result = self.sd_cards.generate_path(target_file_path, network_path)
				# Use absolute paths, but prefix relative paths with the network location
				if expected_output.startswith("/") or expected_output is None:
					expected_path = expected_output
				else:
					expected_path = os.path.join(network_path, expected_output)
				self.assertEqual(result, expected_path, msg=f"Failed (loop {i}) to generate truncated path for {target_file_path} with network path size {path_size}")	
				self.assertLessEqual(len(result), 255, msg=f"Generated path (loop {i}) is too long for {target_file_path} with network path size {path_size}")

	@patch('builtins.input', return_value='y')
	@patch.object(SDCards, "generate_name", return_value='test_generated_name')
	def test_copy_sd_card_success(self, mock_input, mock_generate_name):
		# Test successful copy when there is nothing to copy
		self.assertTrue(self.sd_cards.copy_sd_card(self.sd_card_path, self.network_path, self.backup_network_path))


	@patch('builtins.input', return_value='y')
	@patch.object(SDCards, "generate_name", return_value='test_generated_name')
	def test_copy_sd_card_invalid(self, mock_input, mock_generate_name):
		# Test invalid paths
		self.assertFalse(self.sd_cards.copy_sd_card('invalid_path', self.network_path, self.backup_network_path))
		self.assertFalse(self.sd_cards.copy_sd_card(self.sd_card_path, 'invalid_path', self.backup_network_path))
		self.assertFalse(self.sd_cards.copy_sd_card(self.sd_card_path, self.network_path, 'invalid_path'))

	@patch('builtins.input', return_value='y')
	@patch.object(SDCards, "generate_name", return_value='test_generated_name')
	def test_copy_sd_card_noaccess(self, mock_input, mock_generate_name):
		# Test unwritable paths
		with patch('os.access', return_value=False):
			self.assertFalse(self.sd_cards.copy_sd_card(self.sd_card_path, self.network_path, self.backup_network_path))

	@patch('builtins.input', return_value='y')
	@patch.object(SDCards, "generate_name", return_value='test_generated_name')
	def test_copy_sd_card_rsync_fail(self, mock_input, mock_generate_name):
		# Test rsync failure
		with patch('subprocess.check_call', side_effect=subprocess.CalledProcessError(1, '')):
			self.assertFalse(self.sd_cards.copy_sd_card(self.sd_card_path, self.network_path, self.backup_network_path))

	@patch('builtins.input', return_value='y')
	@patch.object(SDCards, "generate_name", return_value='test_generated_name')
	def test_copy_sd_card_validate_fail(self, mock_input, mock_generate_name):
		# Test checksum validation failure on backup
		with patch.object(self.sd_cards, 'validate_checksums', return_value=False):
			self.assertFalse(self.sd_cards.copy_sd_card(self.sd_card_path, self.network_path, self.backup_network_path))

	@patch('builtins.input', return_value='y')
	@patch.object(SDCards, "generate_name", return_value='test_generated_name')
	def test_copy_sd_card_teracopy_fail(self, mock_input, mock_generate_name):
		# Test teracopy failure
		with patch('subprocess.check_call', side_effect=subprocess.CalledProcessError(1, '')):
			self.assertFalse(self.sd_cards.copy_sd_card(self.sd_card_path, self.network_path, self.backup_network_path))

	@patch('builtins.input', return_value='y')
	@patch.object(SDCards, "generate_name", return_value='test_generated_name')
	def test_copy_sd_card_validate_list_fail(self, mock_input, mock_generate_name):
		# Test checksum validation failure on organize
		with patch.object(self.sd_cards, 'validate_checksum_list', return_value=False):
			self.assertFalse(self.sd_cards.copy_sd_card(self.sd_card_path, self.network_path, self.backup_network_path))

	@patch('builtins.input', return_value='y')
	@patch.object(SDCards, "generate_name", return_value="20230809_ILCE-7RM4_2544_-1 0EV_-7 7B_6400ISO_0 1SS_SAMYANG AF 12mm F2 0.arw")
	def test_file_still_exists_after_copy(self, mock_input, mock_generate_name):
		# Create a file to copy
		filepath = self._create_file()

		# Test that the file still exists after a copy
		result = self.sd_cards.copy_sd_card(self.sd_card_path, self.network_path, self.backup_network_path)

		self.assertTrue(result, msg="Failed to copy SD card. Cannot test if file still exists after copy.")
		self.assertTrue(os.path.exists(filepath), msg="Original file does not exist after copy.")

	def test_perform_rsync(self):
		# Test successful rsync
		self.assertTrue(self.sd_cards.perform_rsync(self.sd_card_path, self.backup_network_path))

		# Test rsync failure
		with patch('subprocess.check_call', side_effect=subprocess.CalledProcessError(1, '')):
			self.assertFalse(self.sd_cards.perform_rsync(self.sd_card_path, self.backup_network_path))

	def test_perform_teracopy(self):
		# Test successful teracopy
		self.assertTrue(self.sd_cards.perform_teracopy(self.sd_card_path, self.temp_dir))

		# Test teracopy failure
		with patch('subprocess.check_call', side_effect=subprocess.CalledProcessError(1, '')):
			self.assertFalse(self.sd_cards.perform_teracopy(self.sd_card_path, self.temp_dir))


	@patch.object(SDCards, "generate_name", return_value='test_generated_name.jpg')
	def test_organize_files(self, mock_generate_name):
		# Organize no files
		results = self.sd_cards.organize_files(self.network_path, self.sd_card_path)
		self.assertEqual(len(results), 0)

		# Create 1 file to organize
		with open(os.path.join(self.sd_card_path, 'IMG_0001.jpg'), 'w') as f:
			f.write('test')

		# Test successful organization
		results = self.sd_cards.organize_files(self.sd_card_path, self.network_path)
		self.assertEqual(len(results), 1)
		for original_path, new_path in results.items():
			self.assertTrue(os.path.exists(new_path), msg=f"Failed to move {original_path} to {new_path}. New path doesn't exist")
			self.assertNotEqual(original_path, new_path, msg=f"Failed to move {original_path} to {new_path}. New path is the same as the original path")
			
			# Test that it was renamed and placed into a new YYYY/YYYY-mm-dd directory
			date = datetime.datetime.now()
			new_directory = os.path.join(self.network_path, str(date.year), date.strftime('%Y-%m-%d'))
			new_path = os.path.join(self.network_path, new_directory, 'test_generated_name.jpg')
			self.assertTrue(os.path.exists(new_path), msg=f"Failed to rename to {new_path}")

		# Test invalid source path
		results = self.sd_cards.organize_files('invalid_path', self.network_path)
		self.assertEqual(len(results), 0)

		# Test invalid destination path
		results = self.sd_cards.organize_files(self.sd_card_path, 'invalid_path')
		self.assertEqual(len(results), 0)

	def test_no_clobber_rsync(self):
		# Test that perform_rsync doesnt clobber existing files
		# Create a file in the destination directory
		with open(os.path.join(self.backup_network_path, 'IMG_0001.jpg'), 'w') as f:
			f.write('foo')

		# Create a file in the source directory with the same name
		with open(os.path.join(self.sd_card_path, 'IMG_0001.jpg'), 'w') as f:
			f.write('bar')

		# Perform the rsync
		result = self.sd_cards.perform_rsync(self.sd_card_path, self.backup_network_path)
		self.assertTrue(result, 'Rsync returned failed when it encountered an existing file')

		# Test that the file in the destination directory was not overwritten
		with open(os.path.join(self.backup_network_path, 'IMG_0001.jpg'), 'r') as f:
			self.assertEqual(f.read(), 'foo', 'Rsync overwrote an existing file')

	def test_no_clobber_teracopy(self):
		# Test that perform_teracopy doesnt clobber existing files
		# Create a file in the destination directory
		with open(os.path.join(self.temp_dir, 'IMG_0001.jpg'), 'w') as f:
			f.write('foo')

		# Create a file in the source directory with the same name
		with open(os.path.join(self.sd_card_path, 'IMG_0001.jpg'), 'w') as f:
			f.write('bar')

		# Perform the teracopy
		result = self.sd_cards.perform_teracopy(self.sd_card_path, self.temp_dir)
		self.assertTrue(result, 'Teracopy returned failed when it encountered an existing file')

		# Test that the file in the destination directory was not overwritten
		with open(os.path.join(self.temp_dir, 'IMG_0001.jpg'), 'r') as f:
			self.assertEqual(f.read(), 'foo', 'Teracopy overwrote an existing file')

	@patch.object(SDCards, "generate_name", return_value='IMG_0001.jpg')
	def test_no_clobber_organize(self, mock_generate_name):
		"""
		Test that organize_files doesnt clobber existing files
		"""

		# Get today's date and time
		date = datetime.datetime.now()
		parent_directory = os.path.join(self.network_path, str(date.year), date.strftime('%Y-%m-%d'))

		# Create a file in the destination directory, where we expect our new file to be organized
		new_path = os.path.join(self.network_path, parent_directory, 'IMG_0001.jpg')
		os.makedirs(os.path.dirname(new_path), exist_ok=True)
		with open(new_path, 'w') as f:
			f.write('foo')

		# Create a file in the source directory with the same name
		original_path = os.path.join(self.sd_card_path, 'IMG_0001.jpg')
		with open(original_path, 'w') as f:
			f.write('bar')

		# Perform the organize
		result = self.sd_cards.organize_files(self.sd_card_path, self.network_path)
		self.assertEqual(len(result), 1, 'Organize did not return results when it encountered an existing file')
		# Test that the new_path still exists
		self.assertTrue(os.path.exists(new_path), 'Existing file no longer exists after organize_files')

		# Test that the file in the destination directory was not overwritten
		with open(new_path, 'r') as f:
			self.assertEqual(f.read(), 'foo', 'Organize overwrote an existing file')

		# Test that the original file was not moved or changed
		self.assertTrue(os.path.exists(original_path), 'Original file was moved when it should not have been')
		with open(original_path, 'r') as f:
			self.assertEqual(f.read(), 'bar', 'Original file was modified when it should not have been')

		# Test that a new file was not created in the destination
		# Root directory not affected
		files = os.listdir(self.network_path)
		self.assertEqual(len(files), 1, 'Organize created a new file when it should not have')
		self.assertTrue(os.path.isdir(os.path.join(self.network_path, files[0])), 'Organize changed the structure: no longer a dir')
		self.assertTrue(files[0].startswith(str(date.year)), 'Organize changed the directory structure')
		# Subdirectory not affected
		files = os.listdir(os.path.join(self.network_path, str(date.year)))
		self.assertEqual(len(files), 1, 'Organize created a new file when it should not have')
		self.assertTrue(os.path.isdir(os.path.join(self.network_path, str(date.year), files[0])), 'Organize changed the structure: no longer a dir')
		self.assertTrue(files[0].startswith(date.strftime('%Y-%m-%d')), 'Organize changed the directory structure')
		# Container not affected
		files = os.listdir(os.path.join(self.network_path, str(date.year), date.strftime('%Y-%m-%d')))
		self.assertEqual(len(files), 1, 'Organize created a new file when it should not have')
		self.assertTrue(os.path.isfile(os.path.join(self.network_path, str(date.year), date.strftime('%Y-%m-%d'), files[0])), 'Organize changed the structure: no longer a file')
		self.assertTrue(files[0].startswith('IMG_0001.jpg'), 'Organize changed the directory structure')

		self.assertIsNone(result[original_path], 'Organize did not return None when it encountered an existing file')

	@patch.object(SDCards, "generate_name", return_value='IMG_0001.jpg')
	@patch.object(SDCards, "validate_checksums", return_value=False)
	@patch('builtins.input', return_value='y')
	def test_copy_sd_card_checksum_fail(self, mock_generate_name, mock_validate_checksums, mock_input):
		"""
		Test that the copy_sd_card function fails if the source and destination checksums do not match after copy.
		"""
		# Create a file in the source directory
		with open(os.path.join(self.sd_card_path, 'IMG_0001.jpg'), 'w') as f:
			f.write('bar')

		# Perform the copy
		result = self.sd_cards.copy_sd_card(self.sd_card_path, self.network_path, self.backup_network_path)
		self.assertFalse(result, 'Copy succeeded when checksum matching failed')

	@patch.object(SDCards, "generate_name", return_value='IMG_0001.jpg')
	@patch.object(SDCards, "validate_checksum_list", return_value=False)
	@patch('builtins.input', return_value='y')
	def test_copy_sd_card_checksum_list_fail(self, mock_generate_name, mock_validate_checksum_list, mock_input):
		"""
		Test that the copy_sd_card function fails if the source and destination checksums do not match after copy.
		"""
		# Create a file in the source directory
		with open(os.path.join(self.sd_card_path, 'IMG_0001.jpg'), 'w') as f:
			f.write('bar')

		# Perform the copy
		result = self.sd_cards.copy_sd_card(self.sd_card_path, self.network_path, self.backup_network_path)
		self.assertFalse(result, 'Copy succeeded when checksum list matching failed')