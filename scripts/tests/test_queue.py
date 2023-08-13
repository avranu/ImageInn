"""
	
	Metadata:
	
		File: test_queue.py
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
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock

from scripts.import_sd.photo import Photo
from scripts.import_sd.queue import Queue
from scripts.import_sd.validator import Validator

class TestQueue(unittest.TestCase):
	def setUp(self):
		self.queue = Queue()

		# Paths
		self.data_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'data')
		self.test_data_path = os.path.join(self.data_path, 'test_data')
		self.sample_image_path = os.path.join(self.data_path, "_ARW_2544.arw")
		self.sd_card_path = os.path.join(self.test_data_path, 'sd_card')
		self.network_path = os.path.join(self.test_data_path, 'network')
		self.empty_path = os.path.join(self.test_data_path, 'empty')
		self.backup_network_path = os.path.join(self.test_data_path, 'backup_network')
		self.list_path = os.path.join(self.test_data_path, 'file_list.txt')
		# Ensure sd_card_path, network_path and backup_network_path all exist
		os.makedirs(self.sd_card_path, exist_ok=True)
		os.makedirs(self.network_path, exist_ok=True)
		os.makedirs(self.backup_network_path, exist_ok=True)
		os.makedirs(self.empty_path, exist_ok=True)
		self.temp_dir = tempfile.mkdtemp()

		self.files = [
			os.path.join(self.sd_card_path, "img_001.jpg"),
			os.path.join(self.sd_card_path, "img_002.jpg"),
			os.path.join(self.sd_card_path, "img_003.jpg"),
			os.path.join(self.network_path, "img_001.jpg"),
			os.path.join(self.network_path, "img_002.jpg"),
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

	def tearDown(self):
		for file in self.files:
			os.remove(file)
		shutil.rmtree(self.temp_dir)
		shutil.rmtree(self.test_data_path)

	def test_append(self):
		photo = Photo(self.files[0])
		destination = Photo(self.files[3])

		# Test appending a photo with the same checksum as the destination
		self.queue.calculate_checksums = MagicMock(return_value={photo: "1234", destination: "1234"})
		result = self.queue.append(photo, destination)
		self.assertFalse(result)
		self.assertIn(photo, self.queue.get_skipped())

		# Test appending a photo with a different checksum as the destination
		self.queue.calculate_checksums = MagicMock(return_value={photo: "1234", destination: "5678"})
		result = self.queue.append(photo, destination)
		self.assertTrue(result)
		self.assertIn(photo, self.queue._mismatched)

		# Test appending a photo without destination existing
		destination.exists = MagicMock(return_value=False)
		result = self.queue.append(photo, destination)
		self.assertTrue(result)
		self.assertIn(photo, self.queue.get(os.path.dirname(destination.path)))

	def test_skip_and_flag(self):
		photo = Photo(self.files[0])
		existing = Photo(self.files[2])
		self.queue.skip(photo)
		self.assertIn(photo, self.queue.get_skipped())
		self.queue.flag(photo, existing)
		self.assertIn(photo, self.queue.get_mismatched())

	def test_calculate_checksums(self):
		photo1 = Photo(self.files[0])
		photo2 = Photo(self.files[1])
		Validator.calculate_checksum = MagicMock(side_effect=["1234", "5678"])
		checksums = self.queue.calculate_checksums([photo1, photo2])
		self.assertEqual(checksums[photo1], "1234")
		self.assertEqual(checksums[photo2], "5678")
		self.assertEqual(self.queue.get_checksum(photo1), "1234")

	def test_get_methods(self):
		self.assertEqual(self.queue.get(self.empty_path), [])
		self.assertEqual(self.queue.get_queue(), {})
		self.assertEqual(self.queue.get_skipped(), [])
		self.assertEqual(self.queue.get_mismatched(), {})
		self.assertEqual(self.queue.get_checksums(), {})

	def test_count(self):
		photo = Photo(self.files[0])
		destination = Photo(self.files[3])
		self.queue.append(photo, destination)
		self.assertEqual(self.queue.count("skipped"), 1, msg="Failed to count skipped photos")
		self.assertEqual(self.queue.count("mismatched"), 0, msg="Failed to count mismatched photos")
		self.assertEqual(self.queue.count("checksums"), 1, msg="Failed to count checksums")
		self.assertEqual(self.queue.count("queue"), 0, msg="Failed to count queue")
		self.assertEqual(self.queue.count("all"), 1, msg="Failed to count all")
		self.assertEqual(self.queue.count(), 0, msg="Failed to count all")

	def test_write(self):
		photo = Photo(self.files[0])
		destination = Photo(self.files[3])
		print('Appending ', photo.path, ' => ', destination.path)
		result = self.queue.append(photo, destination)
		self.assertTrue(result, msg="Failed to append photo to queue")
		output_path = self.queue.write(self.network_path, os.path.join(self.temp_dir, "queue.txt"))
		with open(output_path, "r") as file:
			content = file.read().strip()
			self.assertEqual(content, photo.path, msg="Failed to write queue to file")

	def test_to_dict(self):
		result = self.queue.to_dict()
		self.assertEqual(result, {
			"queue": {},
			"skipped": [],
			"mismatched": {},
			"checksums": {}
		})

	def test_len_and_str(self):
		photo = Photo(self.files[0])
		destination = Photo(self.files[3])
		self.queue.append(photo, destination)
		self.assertEqual(len(self.queue), 1)
		self.assertEqual(str(self.queue), "Queue: 1 photos")
