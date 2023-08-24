"""

	Metadata:

		File: test_path.py
		Project: imageinn
		Created Date: 21 Aug 2023
		Author: Jess Mann
		Email: jess.a.mann@gmail.com

		-----

		Last Modified: Wed Aug 23 2023
		Modified By: Jess Mann

		-----

		Copyright (c) 2023 Jess Mann
"""
import os
import unittest
from unittest.mock import patch
import shutil
import tempfile
import unittest
from scripts.lib.path import FilePath
from scripts.import_sd.validator import Validator

class TestFilePath(unittest.TestCase):

	def setUp(self):
		# Paths
		self.data_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'data')
		self.test_data_path = os.path.join(self.data_path, 'test_data')
		self.photos_path = os.path.join(self.test_data_path, 'photos')
		self.sample_image_path = os.path.join(self.data_path, "_ARW_2544.arw")
		self.empty_path = os.path.join(self.test_data_path, 'empty')
		# Ensure all directories exist
		os.makedirs(self.test_data_path, exist_ok=True)
		os.makedirs(self.empty_path, exist_ok=True)
		self.temp_dir = tempfile.mkdtemp()

		self.files = [
			os.path.join(self.photos_path, "img_001.jpg"),
			os.path.join(self.photos_path, "img_002.jpg"),
			os.path.join(self.photos_path, "img_003.jpg"),
		]

		for file in self.files:
			with open(file, "w") as f:
				f.write("test data")

	def tearDown(self) -> None:
		# Remove the test_data directory and its contents
		shutil.rmtree(self.temp_dir)
		shutil.rmtree(self.test_data_path)

	def test_init_with_string(self):
		test_cases = {
			'/path/to/file.txt': '/path/to/file.txt',
			'path/to/file.txt': os.path.join(os.getcwd(), 'path/to/file.txt'),
			'/path_/_to/file_w1th.$pecial.txt': '/path_/_to/file_w1th.$pecial.txt',
		}
		for test_case, expected in test_cases.items():
			path = FilePath(test_case)
			self.assertEqual(path.path, expected, msg="Failed initializing with str: {}".format(test_case))

	def test_init_with_list(self):
		test_cases = {
			['path', 'to', 'file.txt']: os.path.join(os.getcwd(), 'path/to/file.txt'),
			['/path', 'to', 'file.txt']: '/path/to/file.txt',
			['/path', 'to', 'file.txt', 'with', 's p 3cial.txt']: '/path/to/file.txt/with/s p 3cial.txt',
		}
		for test_case, expected in test_cases.items():
			path = FilePath(test_case)
			self.assertEqual(path.path, expected, msg="Failed initializing with list: {}".format(test_case))

	def test_init_with_filepath(self):
		test_cases = {
			FilePath('/path/to/file.txt'): '/path/to/file.txt',
			FilePath('path/to/file.txt'): os.path.join(os.getcwd(), 'path/to/file.txt'),
			FilePath('/path_/_to/file_w1th.$pecial.txt'): '/path_/_to/file_w1th.$pecial.txt',
		}
		for test_case, expected in test_cases.items():
			path = FilePath(test_case)
			self.assertEqual(path.path, expected, msg="Failed initializing with FilePath: {}".format(test_case))

	def test_windows_paths(self):
		test_cases = {
			'c:\\path\\to\\file.txt': 'c:/path/to/file.txt',
			'c:/path/to/file.txt': 'c:/path/to/file.txt',
			'C:\\path/to/file.txt': 'c:/path/to/file.txt',
			'C:/path\\to/file.txt': 'c:/path/to/file.txt',
			FilePath('c:\\path\\to\\file.txt'): 'c:/path/to/file.txt',
			FilePath('c:/path/to/file.txt'): 'c:/path/to/file.txt',
			['c:\\path', 'to', 'file.txt']: 'c:/path/to/file.txt',
			['c:/path', 'to', 'file.txt']: 'c:/path/to/file.txt',
		}
		for test_case, expected in test_cases.items():
			path = FilePath(test_case)
			self.assertEqual(path.path, expected, msg="Failed for windows path: {}".format(test_case))

	def test_properties(self):
		test_cases = {
			'/path/to/file.txt': { 'filename': 'file.txt', 'extension': 'txt', 'filename_stem': 'file', 'directory': '/path/to' },
			'path/to/file.txt': { 'filename': 'file.txt', 'extension': 'txt', 'filename_stem': 'file', 'directory': os.path.join(os.getcwd(), 'path/to') },
			'/path_/_to/file_w1th.$pecial.txt': { 'filename': 'file_w1th.$pecial.txt', 'extension': 'txt', 'filename_stem': 'file_w1th.$pecial', 'directory': '/path_/_to' },
		}
		for test_case, expected in test_cases.items():
			path = FilePath(test_case)
			self.assertEqual(path.filename, expected['filename'], msg="Failed getting filename prop: {}".format(test_case))
			self.assertEqual(path.extension, expected['extension'], msg="Failed for extension prop: {}".format(test_case))
			self.assertEqual(path.filename_stem, expected['filename_stem'], msg="Failed for filename_stem prop: {}".format(test_case))
			self.assertEqual(path.directory, expected['directory'], msg="Failed for directory prop: {}".format(test_case))

	@patch('os.path.exists', return_value=True)
	def test_exists(self, mock_exists):
		path = FilePath('/path/to/file.txt')
		self.assertTrue(path.exists)

		for value in [True, False]:
			with patch('os.path.isfile', return_value=value):
				self.assertTrue(path.exists, msg="Failed for isfile: {}".format(value))
			with patch('os.path.isdir', return_value=value):
				self.assertTrue(path.exists, msg="Failed for isdir: {}".format(value))

	@patch('os.path.exists', return_value=False)
	def test_not_exists(self, mock_exists):
		path = FilePath('/path/to/file.txt')
		self.assertFalse(path.exists)

		for value in [True, False]:
			with patch('os.path.isfile', return_value=value):
				self.assertFalse(path.exists, msg="Failed for isfile: {}".format(value))
			with patch('os.path.isdir', return_value=value):
				self.assertFalse(path.exists, msg="Failed for isdir: {}".format(value))

	def test_append_suffix(self):
		test_cases = {
			('/path/to/file.txt', '_1'): '/path/to/file_1.txt',
			('/path/to/file.txt', '1'): '/path/to/file1.txt',
			('/path/to/file.txt', '1.txt'): '/path/to/file1.txt.txt',
			('/path/to/file.txt', '$p ec 1al'): '/path/to/file$p ec 1al.txt',
			('/path.to/file.txt', '_1'): '/path.to/file_1.txt',
		}
		for (test_path, suffix), expected in test_cases.items():
			path = FilePath(test_path)
			new_path = path.append_suffix(suffix)
			self.assertEqual(str(new_path), expected, msg="Failed appending suffix: {}".format(suffix))

	def test_remove_suffix(self):
		test_cases = {
			('/path/to/file_1.txt', '_1'): '/path/to/file.txt',
			('/path/to/file1.txt', '1'): '/path/to/file.txt',
			('/path/to/file1.txt.txt', '1.txt'): '/path/to/file.txt',
			('/path/to/file$p ec 1al.txt', '$p ec 1al'): '/path/to/file.txt',
			('/path.to/file_1.txt', '_1'): '/path.to/file.txt',
		}
		for (test_path, suffix), expected in test_cases.items():
			path = FilePath(test_path)
			new_path = path.remove_suffix(suffix)
			self.assertEqual(str(new_path), expected, msg="Failed removing suffix: {}".format(suffix))

	@patch.object(Validator, 'calculate_checksum', return_value='12345')
	def test_checksum(self, _mock_checksum):
		path = FilePath('/path/to/file.txt')
		self.assertEqual(path.checksum, '12345')

	@patch.object(Validator, 'calculate_checksum', return_value='12345')
	def test_matches(self, _mock_checksum):
		path1 = FilePath('/path/to/file1.txt')
		path2 = FilePath('/path/to/file2.txt')
		self.assertTrue(path1.matches(path2))

	@patch.object(Validator, 'calculate_checksum', side_effect=['12345', '67890'])
	def test_not_matches(self, _mock_checksum):
		path1 = FilePath('/path/to/file1.txt')
		path2 = FilePath('/path/to/file2.txt')
		self.assertFalse(path1.matches(path2))

	def test_str_repr(self):
		path = FilePath('/path/to/file.txt')
		self.assertEqual(str(path), '/path/to/file.txt')
		self.assertEqual(repr(path), '/path/to/file.txt')

	def test_equals_str(self):
		path = FilePath('/path/to/file.txt')
		self.assertEqual(path.path, '/path/to/file.txt')
		self.assertEqual(path, '/path/to/file.txt')
		self.assertIsInstance(path, str)
		self.assertIsInstance(path, FilePath)

	def test_string_concat(self):
		path = FilePath('/path/to/file.txt')
		new_path = path + '_copy.txt'
		self.assertEqual(str(new_path), '/path/to/file.txt_copy.txt')
		self.assertEqual(f'{path}_copy2', '/path/to/file.txt_copy2')

	def test_empty_path(self):
		path = FilePath('')
		self.assertEqual(path.path, '')
		self.assertEqual(path.filename, '')
		self.assertEqual(path.extension, '')
		self.assertEqual(path.filename_stem, '')
		self.assertEqual(path.directory, '')

	def test_no_extension(self):
		path = FilePath('/path/to/filename')
		self.assertEqual(path.extension, '')
		self.assertEqual(path.filename_stem, 'filename')

	def test_append_remove_suffix_no_extension(self):
		path = FilePath('/path/to/filename')
		new_path = path.append_suffix('_v2')
		self.assertEqual(str(new_path), '/path/to/filename_v2')
		removed_path = new_path.remove_suffix('_v2')
		self.assertEqual(str(removed_path), '/path/to/filename')

	def test_checksum_no_file(self):
		with patch.object(Validator, 'calculate_checksum', return_value='12345'):
			path = FilePath('/path/to/nonexistent_file.txt')
			self.assertEqual(path.checksum, '')

	def test_matches_no_file(self):
		with patch.object(Validator, 'calculate_checksum', return_value='12345'):
			path1 = FilePath('/path/to/nonexistent_file1.txt')
			path2 = FilePath('/path/to/nonexistent_file2.txt')
			self.assertFalse(path1.matches(path2))

	def test_init_with_non_string_and_non_list(self):
		with self.assertRaises(TypeError):
			FilePath(12345)

	def test_append_suffix_with_non_string(self):
		path = FilePath('/path/to/file.txt')
		with self.assertRaises(TypeError):
			path.append_suffix(12345)

	def test_remove_suffix_with_non_string(self):
		path = FilePath('/path/to/file.txt')
		with self.assertRaises(TypeError):
			path.remove_suffix(12345)


if __name__ == '__main__':
	unittest.main()
