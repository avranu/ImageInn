import errno
import hashlib
import os
import sys
import shutil
import subprocess
import logging
from typing import Any, Optional, TypedDict

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

	def copy_sd_card(self, sd_card_path : str, network_path : str, backup_network_path : str):
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
		# Ensure the path exists
		logger.info('Copying sd card...')
		if not self.check_sd_path(sd_card_path):
			return False
		
		# Verify we can write to the network path
		if not os.access(network_path, os.W_OK):
			logger.error(f'Cannot write to network path: {network_path}')
			return False
		
		# Verify we can write to the backup network path
		if not os.access(backup_network_path, os.W_OK):
			logger.error(f'Cannot write to backup network path: {backup_network_path}')
			return False
		
		# Calculate checksums before rsync
		error_count = 0
		checksums_before = {}
		for root, dirs, files in os.walk(sd_card_path):
			for file in files:
				file_path = os.path.join(root, file)
				checksums_before[file_path] = self.calculate_checksum(file_path)

		for destination_path in [network_path, backup_network_path]:

			for _ in range(MAX_RETRIES):
				try:
					subprocess.check_call(['rsync', '-av', '--checksum', sd_card_path, destination_path])
					# Success
					break 
				except subprocess.CalledProcessError as e:
					# Attempting retry
					logger.warning(f'rsync to {destination_path} failed with error code {e.returncode}, retrying...')
			else:
				logger.error(f'rsync to {destination_path} failed after {MAX_RETRIES} attempts')
				return False
			
			# Calculate checksums after rsync
			checksums_after = {}
			for root, _dirs, files in os.walk(destination_path):
				for file in files:
					file_path = os.path.join(root, file)
					checksums_after[file_path] = self.calculate_checksum(file_path)
			
			# Compare checksums and write them to a file
			with open(os.path.join(destination_path, 'checksum.txt'), 'w') as f:
				for file_path, checksum_before in checksums_before.items():
					checksum_after = checksums_after.get(file_path)
					if checksum_before == checksum_after:
						f.write(f'{file_path}: {checksum_before}\n')
					else:
						logger.error(f'Checksum mismatch for {file_path}: {checksum_before} != {checksum_after}')
						error_count += 1
		
		if error_count > 0:
			logger.critical(f'Checksum mismatch for {error_count} files')
			return False
		
		return True

