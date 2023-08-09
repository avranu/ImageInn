import logging
import subprocess
import unittest
from unittest.mock import patch, MagicMock, mock_open
from scripts.import_sd import SDCards

class TestSDCards(unittest.TestCase):

	def setUp(self):
		# Suppress logging
		logging.disable(logging.CRITICAL)
		self.sd_cards = SDCards()

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
	def test_successful_copy(self, mock_rsync, mock_validate, mock_check_sd_path, mock_is_path_valid, mock_is_path_writable):
		result = self.sd_cards.copy_sd_card("/valid/sd/card", "/valid/network/path", "/valid/backup/network/path")
		self.assertTrue(result)

	@patch.object(SDCards, "perform_rsync", return_value=True)
	@patch.object(SDCards, "validate_checksums", return_value=False)
	def test_checksum_mismatch(self, mock_rsync, mock_validate):
		result = self.sd_cards.copy_sd_card("/valid/sd/card", "/valid/network/path", "/valid/backup/network/path")
		self.assertFalse(result)

	@patch.object(SDCards, "perform_rsync", return_value=False)
	def test_rsync_failure(self, mock_rsync):
		result = self.sd_cards.copy_sd_card("/valid/sd/card", "/valid/network/path", "/valid/backup/network/path")
		self.assertFalse(result)

	@patch.object(SDCards, "calculate_checksums")
	@patch.object(SDCards, "perform_rsync", return_value=True)
	def test_no_modification_of_source(self, mock_rsync, mock_checksum):
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
	def test_get_info(self, mock_isfile, mock_access, mock_walk, mock_disk_usage, mock_exists, mock_check_sd_path, mock_is_path_valid):
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
	@patch('builtins.open', mock_open(read_data=b"checksum1"))
	def test_validate_checksums_missing_file(self, mock_isfile, mock_access, mock_exists, mock_checksum, mock_check_sd_path, mock_is_path_valid):
		# Simulating a situation where "file2" is missing after rsync
		result = self.sd_cards.validate_checksums({"file1": "checksum1", "file2": "checksum2"}, "/valid/network/path")
		self.assertFalse(result)

	@patch("os.path.isfile", return_value=True)
	@patch("os.access", return_value=True)
	@patch("os.path.exists", return_value=True)
	@patch.object(SDCards, "calculate_checksums", return_value={"file1": "checksum5", "file2": "checksum2"})
	@patch.object(SDCards, "check_sd_path", return_value=True)
	@patch.object(SDCards, "is_path_valid", return_value=True)
	@patch('builtins.open', mock_open(read_data=b"checksum1"))
	def test_validate_checksums_mismatch_file(self, mock_isfile, mock_access, mock_exists, mock_checksum, mock_check_sd_path, mock_is_path_valid):
		# Simulating a situation where "file2" is missing after rsync
		result = self.sd_cards.validate_checksums({"file1": "checksum1", "file2": "checksum2"}, "/valid/network/path")
		self.assertFalse(result)

	@patch("os.path.isfile", return_value=True)
	@patch("os.access", return_value=True)
	@patch("os.path.exists", return_value=True)
	@patch.object(SDCards, "calculate_checksums", return_value={"file1": "checksum1", "file2": "checksum4"})
	@patch.object(SDCards, "check_sd_path", return_value=True)
	@patch.object(SDCards, "is_path_valid", return_value=True)
	@patch('builtins.open', mock_open(read_data=b"checksum1"))
	def test_validate_checksums_mismatch_backup(self, mock_isfile, mock_access, mock_exists, mock_checksum, mock_check_sd_path, mock_is_path_valid):
		# Simulating a situation where "file2" is missing after rsync
		result = self.sd_cards.validate_checksums({"file1": "checksum1", "file2": "checksum2"}, "/valid/network/path")
		self.assertFalse(result)
