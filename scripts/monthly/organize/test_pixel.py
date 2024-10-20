"""*********************************************************************************************************************
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    METADATA:                                                                                                         *
*                                                                                                                      *
*        File:    test_pixel.py                                                                                        *
*        Project: imageinn                                                                                             *
*        Version: 1.0.0                                                                                                *
*        Created: 2024-09-16                                                                                           *
*        Author:  Jess Mann                                                                                            *
*        Email:   jess.a.mann@gmail.com                                                                                *
*        Copyright (c) 2024 Jess Mann                                                                                  *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    LAST MODIFIED:                                                                                                    *
*                                                                                                                      *
*        2024-10-19     By Jess Mann                                                                                   *
*                                                                                                                      *
*********************************************************************************************************************"""
import unittest
import tempfile
import shutil
from pathlib import Path
import hashlib
from unittest.mock import patch
from scripts.exceptions import ShouldTerminateException
from scripts.monthly.exceptions import (
    OneFileException,
    DuplicationHandledException
)
from scripts.monthly.organize.pixel import PixelFileOrganizer
import logging

# Disable logging during tests to keep the output clean
logging.disable(logging.CRITICAL)

class TestPixelFileOrganizer(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for testing
        self.test_dir = tempfile.mkdtemp()
        # Instantiate the organizer with the test directory
        self.organizer = PixelFileOrganizer(directory=self.test_dir, dry_run=False)

    def tearDown(self):
        # Remove the temporary directory after each test
        shutil.rmtree(self.test_dir)

    def create_file(self, path : Path, content=b"Test content"):
        """Helper method to create a file with specified content."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            f.write(content)

    def test_find_subdir(self):
        filename = "PXL_20211009_143747197.jpg"
        expected_subdir = self.organizer.directory / "2021-10"
        subdir = self.organizer.create_subdir(filename)
        self.assertEqual(subdir, expected_subdir)
        # Check that the directory is created
        self.assertTrue(subdir.exists())

    def test_hash(self):
        # Create a temporary file
        file_path = Path(self.test_dir) / "test_file.txt"
        content = b"This is a test file."
        self.create_file(file_path, content)
        # Calculate the expected hash
        expected_hash = hashlib.md5(content).hexdigest()
        actual_hash = self.organizer.hash_file(file_path)
        self.assertEqual(actual_hash, expected_hash)

    def test_handle_single_conflict_no_conflict(self):
        # Create a source file
        source_file = Path(self.test_dir) / "PXL_20211009_143747197.jpg"
        self.create_file(source_file)
        # Destination file does not exist
        destination = (
            self.organizer.directory
            / "2021-10"
            / "PXL_20211009_143747197.jpg"
        )
        result = self.organizer.handle_single_conflict(source_file, destination)
        self.assertEqual(result, destination)

    def test_handle_single_conflict_duplicate(self):
        # Create a source file
        source_file = Path(self.test_dir) / "PXL_20211009_143747197.jpg"
        content = b"This is a test file."
        self.create_file(source_file, content)
        # Create destination file with the same content
        destination = (
            self.organizer.directory
            / "2021-10"
            / "PXL_20211009_143747197.jpg"
        )
        self.create_file(destination, content)
        # Run handle_single_conflict
        with self.assertRaises(DuplicationHandledException):
            self.organizer.handle_single_conflict(source_file, destination)
        # Check that the source file is deleted
        self.assertFalse(source_file.exists())

    def test_handle_single_conflict_different_files(self):
        # Create a source file
        source_file = Path(self.test_dir) / "PXL_20211009_143747197.jpg"
        source_content = b"This is a test file."
        self.create_file(source_file, source_content)
        # Create destination file with different content
        destination = (
            self.organizer.directory
            / "2021-10"
            / "PXL_20211009_143747197.jpg"
        )
        destination_content = b"Different content."
        self.create_file(destination, destination_content)
        # Run handle_single_conflict
        result = self.organizer.handle_single_conflict(source_file, destination)
        self.assertFalse(result)
        # Check that the source file still exists
        self.assertTrue(source_file.exists())

    def test_handle_collision_rename(self):
        # Create a source file
        source_file = Path(self.test_dir) / "PXL_20211009_143747197.jpg"
        source_content = b"This is a test file."
        self.create_file(source_file, source_content)
        # Create destination file with different content
        destination = (
            self.organizer.directory
            / "2021-10"
            / "PXL_20211009_143747197.jpg"
        )
        destination_content = b"Different content."
        self.create_file(destination, destination_content)
        # Run handle_collision
        new_target_file = self.organizer.handle_collision(source_file, destination)
        # Check that new_target_file has a different name
        self.assertNotEqual(new_target_file.name, destination.name)
        self.assertTrue(new_target_file.name.startswith("PXL_20211009_143747197_"))

    def test_process_file(self):
        # Create a source file
        source_file = Path(self.test_dir) / "PXL_20211009_143747197.jpg"
        source_content = b"This is a test file."
        self.create_file(source_file, source_content)
        # Run process_file
        self.organizer.process_file(source_file)
        # Check that the source file is moved
        target_dir = self.organizer.directory / "2021-10"
        target_file = target_dir / "PXL_20211009_143747197.jpg"
        self.assertTrue(target_file.exists())
        self.assertFalse(source_file.exists())
        # Check that content is preserved
        with open(target_file, "rb") as f:
            content = f.read()
        self.assertEqual(content, source_content)

    def test_organize_files(self):
        # Create multiple source files
        filenames = [
            "PXL_20211009_143747197.jpg",
            "PXL_20211009_143757120.jpg",
            "PXL_20211010_143757121.jpg",
            "PXL_20211109_143757122.jpg",
        ]
        contents = [
            b"Content A",
            b"Content B",
            b"Content C",
            b"Content D",
        ]
        for filename, content in zip(filenames, contents):
            source_file = Path(self.test_dir) / filename
            self.create_file(source_file, content)
        # Run organize_files
        return_none = self.organizer.organize_files()
        self.assertIsNone(return_none)

        # Check that files are moved to correct directories
        target_files = [
            self.organizer.directory / "2021-10" / "PXL_20211009_143747197.jpg",
            self.organizer.directory / "2021-10" / "PXL_20211009_143757120.jpg",
            self.organizer.directory / "2021-10" / "PXL_20211010_143757121.jpg",
            self.organizer.directory / "2021-11" / "PXL_20211109_143757122.jpg",
        ]
        for target_file in target_files:
            self.assertTrue(target_file.exists())
        # Check that source files no longer exist
        for filename in filenames:
            source_file = Path(self.test_dir) / filename
            self.assertFalse(source_file.exists())

    def test_dry_run(self):
        # Create a source file
        source_file = Path(self.test_dir) / "PXL_20211009_143747197.jpg"
        source_content = b"This is a test file."
        self.create_file(source_file, source_content)
        # Instantiate organizer in dry-run mode
        dry_run_organizer = PixelFileOrganizer(directory=self.test_dir, dry_run=True)
        # Run process_file
        dry_run_organizer.process_file(source_file)
        # Check that source file still exists
        self.assertTrue(source_file.exists())
        # Check that the target directory is not created
        target_dir = dry_run_organizer.directory / "2021-10"
        target_file = target_dir / "PXL_20211009_143747197.jpg"
        self.assertFalse(target_file.exists())

    @patch("scripts.monthly.organize.PixelFileOrganizer.hash_file")
    def test_checksum_mismatch(self, mock_hash_file):
        # Create a source file
        source_file = Path(self.test_dir) / "PXL_20211009_143747197.jpg"
        source_content = b"Original content."
        self.create_file(source_file, source_content)

        # Define a fake hash function
        def fake_hash(file_path):
            if file_path == source_file:
                return "sourcehash"
            else:
                return "destinationhash"

        mock_hash_file.side_effect = fake_hash
        # Run process_file and expect ShouldTerminateException
        with self.assertRaises(ShouldTerminateException):
            self.organizer.process_file(source_file)

    def test_invalid_filename(self):
        # Create a file with an invalid filename
        invalid_file = Path(self.test_dir) / "INVALID_FILENAME.jpg"
        self.create_file(invalid_file)
        # Run process_file and expect OneFileException
        with self.assertRaises(OneFileException):
            self.organizer.process_file(invalid_file)
        # Check that the file still exists
        self.assertTrue(invalid_file.exists())

    def test_max_attempts_exceeded(self):
        # Create a source file
        base_name = "PXL_20211009_143747197"
        ext = ".jpg"
        source_file = Path(self.test_dir) / f"{base_name}{ext}"
        source_content = b"Unique content."
        self.create_file(source_file, source_content)
        # Create a lot of conflicting destination files
        destination_dir = self.organizer.directory / "2021-10"
        destination_dir.mkdir(parents=True, exist_ok=True)
        self.create_file(destination_dir / f"{base_name}{ext}", b"Different content.")
        for i in range(11):
            conflicting_file = destination_dir / f"{base_name}_{i}{ext}"
            self.create_file(conflicting_file, b"Different content.")
        # Run handle_collision and expect OneFileException
        destination = destination_dir / f"{base_name}{ext}"
        with self.assertRaises(OneFileException):
            self.organizer.handle_collision(source_file, destination, max_attempts=10)
        # Check that the source file still exists
        self.assertTrue(source_file.exists())

if __name__ == "__main__":
    unittest.main()
