import argparse
import errno
import hashlib
import os
import sys
import shutil
import subprocess
import logging
from typing import Any, Dict, Optional, TypedDict

logger = logging.getLogger(__name__)

# The maximum number of times to retry a copy before giving up
MAX_RETRIES = 3

class SDDirectory:
	"""
	Represents a directory on an SD card.
	"""
	path: str
	total: int | None
	used: int | None
	free: int | None
	num_files: int | None
	num_dirs: int | None

	def __init__(self, path: str, total: Optional[int] = None, used: Optional[int] = None, free: Optional[int] = None, num_files: Optional[int] = None, num_dirs: Optional[int] = None):
		self.path = path
		self.total = total
		self.used = used
		self.free = free
		self.num_files = num_files
		self.num_dirs = num_dirs

class SDCards:
	"""
	Allows us to interact with sd cards mounted to the server this code is running on.
	"""

	def get_media_dir(self) -> str:
		"""
		Get the media directory for the current operating system.
		
		Returns:
			str: The media directory for the current operating system.
			
		Raises:
			FileNotFoundError: If the media directory does not exist.
			
			Examples:
				>>> sd_cards = SDCards()
				>>> sd_cards.get_media_dir()
				'/media'
		"""
		# Windows
		if os.name == 'nt':
			return 'D:\\'
			
		# Chromebook
		if 'CHROMEOS' in os.environ and os.path.exists('/mnt/chromeos/MyFiles/Removable'):
			return '/mnt/chromeos/MyFiles/Removable'
		if os.name == 'posix' and os.path.exists('/mnt/chromeos/removable'):
			return '/mnt/chromeos/removable'
		if os.name == 'posix' and os.path.exists('/media/removable'):
			return '/media/removable'
		
		# Linux + Mac
		if os.name == 'posix' or sys.platform == 'darwin':
			if os.path.exists('/Volumes'):
				return '/Volumes'
			if os.path.exists('/media'):
				return '/media'
			elif os.path.exists('/mnt'):
				return '/mnt'
			
		# Try media
		if os.path.exists('/media'):
			logger.warning('Unknown operating system, trying /media')
			return '/media'
		
		# Unsupported
		raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), '/media')
			
	def is_path_valid(self, path: str) -> bool:
		"""
		Check if the given path exists and is a directory.
		"""
		if not os.path.exists(path):
			logger.error(f'The path does not exist: {path}')
			return False
		
		if not os.path.isdir(path):
			logger.error(f'The path is not a directory: {path}')
			return False

		return True

	def is_path_writable(self, path: str) -> bool:
		"""
		Check if the given path is writable.
		"""
		if not os.access(path, os.W_OK):
			logger.error(f'Cannot write to path: {path}')
			return False

		return True

	def calculate_checksums(self, base_path: str) -> dict[str, str]:
		"""
		Calculate checksums for all files under the given base_path.
		"""
		if not self.is_path_valid(base_path):
			raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), base_path)

		checksums = {}
		for root, _dirs, files in os.walk(base_path):
			for file in files:
				file_path = os.path.join(root, file)
				if os.path.isfile(file_path) and os.access(file_path, os.R_OK):
					with open(file_path, 'rb') as afile:
						hasher = hashlib.sha256()
						for buf in iter(lambda: afile.read(4096), b""):
							hasher.update(buf)
						checksums[file_path] = hasher.hexdigest()
				else:
					logger.error(f'File not accessible: {file_path}')

		return checksums
			
	def get_list(self, media_path : Optional[str] = None) -> list[SDDirectory]:
		"""
		Get all SD cards mounted to the server this code is running on.
		
		Returns:
			list[SDDirectory]: A list containing each SD card path

		Examples:
			>>> sd_cards = SDCards()
			>>> sd_cards.get_sd_cards()
			[
				SDDirectory {
					'path': '/media/pi/SD',
				}
			]	
				
		"""
		# Handle multiple operating systems
		if not media_path:
			media_path = self.get_media_dir()

		# Ensure the path exists
		if not self.check_sd_path(media_path):
			return []

		sd_cards = []

		# Loop over all directories in the media_path, but not subdirectories
		for dir in os.listdir(media_path):
			sd_directory = SDDirectory(os.path.join(media_path, dir))
			sd_cards.append(sd_directory)

		return sd_cards

	def get_info(self, sd_card_path : Optional[str] = None) -> SDDirectory:
		"""
		Get info about the SD card at the given path. 
		
		This includes the total size, used space, and free space, number of files, etc.

		Args:
			sd_card_path (str): The path to the SD card to get info about.

		Returns:
			SDDirectory: An object containing info about the SD card.

		Raises:
			FileNotFoundError: If the SD card does not exist.

		Examples:
			>>> sd_cards = SDCards()
			>>> sd_cards.get_sd_card('/media/pi/SD')
			SDDirectory {
				'path': '/media/pi/SD',
				'total': 32000000000,
				'used': 10000000000,
				'free': 22000000000,
				'num_files': 100,
				'num_dirs': 10
			}
		"""
		if not sd_card_path:
			sd_card_path = self.get_media_dir()

		# Ensure the path exists
		if not self.check_sd_path(sd_card_path):
			raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), sd_card_path)
		
		# Get the total size of the SD card
		total, used, free = shutil.disk_usage(sd_card_path)

		# Get the number of files and dirs on the SD card
		num_files = 0
		num_dirs = 0
		for _root, dirs, files in os.walk(sd_card_path):
			num_files += len(files)
			num_dirs += len(dirs)

		return SDDirectory(
			path = sd_card_path,
			total = total,
			used = used,
			free = free,
			num_files = num_files,
			num_dirs = num_dirs
		)
	
	def calculate_checksum(self, file_path : str) -> str:
		"""
		Calculate the checksum of the given file.
		
		Args:
			file_path (str): The path to the file to calculate the checksum of.
			
		Returns:
			str: The checksum of the given file.

		Raises:
			FileNotFoundError: If the file does not exist.

		Examples:
			>>> calculate_checksum('/home/pi/test.txt')
			'098f6bcd4621d373cade4e832627b4f6'
		"""
		if not os.path.isfile(file_path) or not os.access(file_path, os.R_OK):
			logger.error(f'File not accessible: {file_path}')
			raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), file_path)

		# We use sha256 because rsync uses MD5, and we want to do both
		hasher = hashlib.sha256()

		with open(file_path, 'rb') as afile:
			buf = afile.read()
			hasher.update(buf)

		return hasher.hexdigest()
	
	def check_sd_path(self, sd_card_path : Optional[str] = None) -> bool:
		"""
		Ensure the given path is a valid SD card path.

		Args:
			sd_card_path (str): The path to the SD card to check.

		Returns:
			bool: True if the path is valid, False otherwise.
		"""
		if not sd_card_path:
			sd_card_path = self.get_media_dir()

		# Ensure the path exists
		if not os.path.exists(sd_card_path):
			logger.error(f'The SD card path does not exist: {sd_card_path}')
			return False
		
		# Ensure the path is a directory
		if not os.path.isdir(sd_card_path):
			logger.error(f'The SD card path is not a directory: {sd_card_path}')
			return False
		
		return True
	
	def copy_sd_card(self, sd_card_path: str, network_path: str, backup_network_path: str) -> bool:
		"""
		Use rsync to copy the SD card to 2 separate network locations, and verify checksums after copy.

		Args:
			sd_card_path (str): The path to the SD card to copy.
			network_path (str): The path to the network location to copy the SD card to.
			backup_network_path (str): The path to the backup network location to copy the SD card to.

		Returns:
			bool: True if the copy was successful, False otherwise.

		Examples:
			>>> copy_sd_card('/media/pi/SD_CARD', '/mnt/backup', '/mnt/backup2')
			True
		"""
		logger.info('Copying sd card...')

		# Check if paths are valid and writable
		if not all(map(self.is_path_valid, [sd_card_path, network_path, backup_network_path])):
			return False
		if not all(map(self.is_path_writable, [network_path, backup_network_path])):
			return False

		# Calculate checksums before rsync
		checksums_before = self.calculate_checksums(sd_card_path)

		for destination_path in [network_path, backup_network_path]:
			# Perform rsync
			if not self.perform_rsync(sd_card_path, destination_path):
				return False

			# Validate checksums after rsync
			if not self.validate_checksums(checksums_before, destination_path):
				return False

		return True

	def perform_rsync(self, source_path: str, destination_path: str) -> bool:
		"""
		Perform rsync from source to destination and handle retries.
		"""
		for _ in range(MAX_RETRIES):
			try:
				subprocess.check_call(['rsync', '-av', '--checksum', source_path, destination_path])
				return True  # Success
			except subprocess.CalledProcessError as e:
				logger.warning(f'rsync to {destination_path} failed with error code {e.returncode}, retrying...')
		logger.error(f'rsync to {destination_path} failed after {MAX_RETRIES} attempts')
		return False

	def validate_checksums(self, checksums_before: dict[str, str], destination_path: str) -> bool:
		"""
		Validate checksums after rsync and report any mismatches.
		"""
		checksums_after = self.calculate_checksums(destination_path)
		mismatches = 0

		with open(os.path.join(destination_path, 'checksum.txt'), 'w') as f:
			for file_path, checksum_before in checksums_before.items():
				checksum_after = checksums_after.get(file_path)
				if checksum_before == checksum_after:
					f.write(f'{file_path}: {checksum_before}\n')
				else:
					logger.error(f'Checksum mismatch for {file_path}: {checksum_before} != {checksum_after}')
					mismatches += 1

		if mismatches:
			logger.critical(f'Checksum mismatch for {mismatches} files')
			return False

		return True

def main():
    """
    Entry point for the application.
    """
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Copy the SD card to a network location.')
    parser.add_argument('--sd-card-path', type=str, help='The path to the SD card to copy.')
    parser.add_argument('--network-path', type=str, help='The path to the network location to copy the SD card to.')
    parser.add_argument('--backup-network-path', type=str, help='The path to the backup network location to copy the SD card to.')
    args = parser.parse_args()

    # Set up logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    # Copy the SD card
    copier = SDCards()
    result = copier.copy_sd_card(args.sd_card_path, args.network_path, args.backup_network_path)

    # Exit with the appropriate code
    if result:
        logger.info('SD card copy successful')
        sys.exit(0)

    logger.error('SD card copy failed')
    sys.exit(1)

if __name__ == '__main__':
	main()