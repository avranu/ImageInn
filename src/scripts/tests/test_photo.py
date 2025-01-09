"""

	Metadata:

		File: test_photo.py
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
import unittest
from unittest.mock import patch
from decimal import Decimal
import exifread
from scripts.import_sd.photo import Photo
from scripts.import_sd.exif import ExifTag

class TestPhoto(unittest.TestCase):

	def setUp(self):
		self.sample_path = '/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw'
		self.photo = Photo(self.sample_path)

	def test_init(self):
		self.assertEqual(self.photo.path, self.sample_path)
		self.assertEqual(self.photo.number, 1234)

		photo = Photo(self.sample_path, number=5678)
		self.assertEqual(photo.path, self.sample_path)
		self.assertEqual(photo.number, 5678)

	def test_is_jpg(self):
		jpg_photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.jpg')
		self.assertTrue(jpg_photo.is_jpg())

		jpeg_photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.jpeg')
		self.assertTrue(jpeg_photo.is_jpg())

		self.assertFalse(self.photo.is_jpg())

	def test_str(self):
		self.assertEqual(str(self.photo), self.sample_path)

	@patch('os.path.exists', return_value=False)
	def test_path_not_found(self):
		with self.assertRaises(FileNotFoundError):
			Photo('/path/to/nonexistent/file.jpg')

	@patch('os.path.exists', return_value=True)
	@patch('os.path.isfile', return_value=False)
	def test_path_not_file(self, mock_exists, mock_isfile):
		with self.assertRaises(ValueError):
			Photo('/path/to/directory')

	@patch('exifread.process_file')
	def test_attr(self, mock_process_file):
		exif_data = {
			ExifTag.APERTURE: exifread.utils.Ratio(28, 10),
			ExifTag.ISO: [100],
			ExifTag.CAMERA: 'a7r4'
		}
		mock_process_file.return_value = exif_data

		self.assertEqual(self.photo.attr(ExifTag.APERTURE), Decimal('2.8'))
		self.assertEqual(self.photo.attr(ExifTag.ISO), 100)
		self.assertEqual(self.photo.attr(ExifTag.CAMERA), 'a7r4')
		self.assertIsNone(self.photo.attr(ExifTag.EXPOSURE_MODE))

if __name__ == '__main__':
	unittest.main()
