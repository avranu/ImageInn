"""
	
	Metadata:
	
		File: test_sd.py
		Project: tests
		Created Date: 12 Aug 2023
		Author: Jess Mann
		Email: jess.a.mann@gmail.com
	
		-----
	
		Last Modified: Sun Aug 13 2023
		Modified By: Jess Mann
	
		-----
	
		Copyright (c) 2023 Jess Mann
"""
import unittest
from unittest.mock import patch
import tempfile
import os
import shutil

from scripts.import_sd.sd import SDCard

class TestSDCard(unittest.TestCase):

	def setUp(self):
		# Paths
		self.temp_dir = tempfile.mkdtemp()
		self.sd_card_path = os.path.join(self.temp_dir, 'SD_CARD')
		self.data_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'data')
		self.test_data_path = os.path.join(self.data_path, 'test_data')
		self.sample_image_path = os.path.join(self.data_path, "_ARW_2544.arw")
		self.sd_card_path = os.path.join(self.test_data_path, 'sd_card')
		self.network_path = os.path.join(self.test_data_path, 'network')
		self.empty_path = os.path.join(self.test_data_path, 'empty')
		self.backup_network_path = os.path.join(self.test_data_path, 'backup_network')
		self.list_path = os.path.join(self.test_data_path, 'file_list.txt')
		# Ensure all paths exist
		os.makedirs(self.sd_card_path, exist_ok=True)
		os.makedirs(self.network_path, exist_ok=True)
		os.makedirs(self.backup_network_path, exist_ok=True)
		os.makedirs(self.empty_path, exist_ok=True)
		os.makedirs(os.path.join(self.sd_card_path, 'DCIM'), exist_ok=True)

		self.files = [
			os.path.join(self.sd_card_path, "img_001.jpg"),
			os.path.join(self.sd_card_path, "img_002.jpg"),
			os.path.join(self.sd_card_path, "img_003.jpg"),
		]

	def tearDown(self):
		shutil.rmtree(self.temp_dir)
		shutil.rmtree(self.test_data_path)

	def test_init(self):
		sd_card = SDCard(self.sd_card_path)
		self.assertEqual(sd_card.path, self.sd_card_path + '/')

	def test_get_media_dir_windows(self):
		with patch('os.name', 'nt'):
			self.assertEqual(SDCard.get_media_dir(), 'D:\\')

	def test_get_media_dir_chromebook(self):
		with patch.dict('os.environ', {'CHROMEOS': '1'}), patch('os.path.exists', return_value=True):
			self.assertEqual(SDCard.get_media_dir(), '/mnt/chromeos/MyFiles/Removable')

	def test_get_media_dir_linux(self):
		with patch('os.name', 'posix'), patch('os.path.exists', side_effect=[False, True]):
			self.assertEqual(SDCard.get_media_dir(), '/media/removable')

	def test_get_media_dir_unsupported(self):
		with patch('os.path.exists', return_value=False):
			with self.assertRaises(FileNotFoundError):
				SDCard.get_media_dir()

	def test_sd_contains_photos(self):
		self.assertTrue(SDCard.sd_contains_photos(self.sd_card_path))
		self.assertFalse(SDCard.sd_contains_photos(
			"/non/existent/path", raise_errors=False))

	def test_get_list(self):
		with patch('os.listdir', return_value=[self.sd_card_path]):
			sd_cards = SDCard.get_list(self.sd_card_path)
			self.assertEqual(len(sd_cards), 1, msg="Should only be one SD card")
			self.assertEqual(sd_cards[0].path, self.sd_card_path, msg="Path should be the same")

	@patch.object(shutil, 'disk_usage', return_value=(9000, 5000, 4000))
	@patch.object(os, 'walk', return_value=iter([ ('/media/sd/', [], ['file1', 'file2', 'file3']) ]))
	def test_get_info_instance_method(self, mock_os_walk, mock_disk_usage):
		sd_card = SDCard(self.sd_card_path)
		info = sd_card.get_info()
		self.assertEqual(info.path, self.sd_card_path + '/')
		self.assertEqual(info.total, 9000)
		self.assertEqual(info.used, 5000)
		self.assertEqual(info.free, 4000)
		self.assertEqual(info.num_files, 3)
		self.assertEqual(info.num_dirs, 0)

	@patch.object(shutil, 'disk_usage', return_value=(9000, 5000, 4000))
	@patch.object(os, 'walk', return_value=iter([('/media/sd/', [], ['file1', 'file2', 'file3'])]))
	def test_get_info_class_method(self, mock_os_walk, mock_disk_usage):
		info = SDCard.get_info_for(self.sd_card_path)
		self.assertEqual(info.path, self.sd_card_path)
		self.assertEqual(info.total, 9000)
		self.assertEqual(info.used, 5000)
		self.assertEqual(info.free, 4000)
		self.assertEqual(info.num_files, 3)
		self.assertEqual(info.num_dirs, 0)

	def test_determine_subpath(self):
		card = SDCard(self.sd_card_path)
		filepath = os.path.join(self.sd_card_path, 'DCIM', '100CANON', 'IMG_0001.JPG')
		result = card.determine_subpath(filepath)
		self.assertEqual(result, '100CANON/', msg="Should return the subpath relative to the DCIM folder")

if __name__ == '__main__':
	unittest.main()
