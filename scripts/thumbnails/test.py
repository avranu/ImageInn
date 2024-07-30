import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import tempfile
import shutil
from scripts.thumbnails.sync import JPGSyncer

class TestJPGSyncer(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for the source and target
        self.temp_dir = tempfile.TemporaryDirectory()
        self.source_dir = Path(self.temp_dir.name) / "source"
        self.target_dir = Path(self.temp_dir.name) / "target"
        self.source_dir.mkdir(parents=True, exist_ok=True)
        self.target_dir.mkdir(parents=True, exist_ok=True)

        # Create a sample JPG file
        self.sample_file = self.source_dir / "sample.jpg"
        self.sample_file.write_text("This is a test file.")

        # Instance of JPGSyncer
        self.syncer = JPGSyncer(self.source_dir, self.target_dir)

    def tearDown(self):
        # Clean up the temporary directory
        self.temp_dir.cleanup()

    @patch('scripts.thumbnails.sync.subprocess.run')
    def test_find_jpg_files(self, mock_subprocess):
        jpg_files = self.syncer.find_jpg_files()
        self.assertIn(self.sample_file, jpg_files)

    @patch('scripts.thumbnails.sync.subprocess.run')
    def test_get_file_structure(self, mock_subprocess):
        expected_path = self.target_dir / "2024/2024-07-30/sample.jpg"
        result_path = self.syncer.get_file_structure(self.sample_file)
        self.assertEqual(result_path, expected_path)

    @patch('scripts.thumbnails.sync.JPGSyncer.generate_file_hash')
    @patch('scripts.thumbnails.sync.subprocess.run')
    def test_check_and_copy(self, mock_subprocess, mock_generate_file_hash):
        mock_generate_file_hash.return_value = "mocked_hash"
        dest_path = self.syncer.get_file_structure(self.sample_file)
        self.syncer.check_and_copy(self.sample_file, dest_path)
        mock_subprocess.assert_called_once_with(["rsync", "-a", self.sample_file.as_posix(), dest_path.as_posix()], check=True)

    @patch('scripts.thumbnails.sync.subprocess.run')
    def test_resolve_collision(self, mock_subprocess):
        dest_path = self.target_dir / "2024/2024-07-30/sample.jpg"
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_text("This is a test file.")
        
        new_dest_path = self.syncer.resolve_collision(dest_path)
        self.assertEqual(new_dest_path, self.target_dir / "2024/2024-07-30/sample-1.jpg")

    @patch('scripts.thumbnails.sync.JPGSyncer.check_and_copy')
    def test_sync(self, mock_check_and_copy):
        self.syncer.sync()
        mock_check_and_copy.assert_called_once_with(self.sample_file, self.syncer.get_file_structure(self.sample_file))

    @patch('scripts.thumbnails.sync.subprocess.run')
    @patch('scripts.thumbnails.sync.JPGSyncer.generate_file_hash')
    def test_process_file(self, mock_generate_file_hash, mock_subprocess):
        mock_generate_file_hash.return_value = "mocked_hash"
        dest_path = self.syncer.get_file_structure(self.sample_file)
        self.syncer.process_file(self.sample_file)
        mock_subprocess.assert_called_once_with(["rsync", "-a", self.sample_file.as_posix(), dest_path.as_posix()], check=True)

if __name__ == "__main__":
    unittest.main()