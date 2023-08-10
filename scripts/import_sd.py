import argparse
import datetime
import errno
import hashlib
import math
import os
import re
import sys
import shutil
import subprocess
import logging
import time
from typing import Any, Dict, Optional, TypedDict

import exifread, exifread.utils, exifread.tags.exif, exifread.classes

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
	
	def sd_contains_photos(self, sd_path: str, raise_errors : bool = True) -> bool:
		"""
		Determines if the SD card is structured in the way we expect to contain DSLR photos.
		
		We look for a DCIM folder in the root directory. If it exists, we assume this is a DSLR sd card.
		
		Args:
			sd_path (str): The path to the SD card.
			raise_errors (bool): Whether or not to raise errors if the SD card does not exist.
			
		Returns:
			bool: True if the SD card contains photos, False otherwise.
			
		Raises:
			FileNotFoundError: If the SD card does not exist and the raise_errors parameter is True.
			
		Examples:
			>>> sd_cards = SDCards()
			>>> sd_cards.sd_contains_photos('/media/SD_CARD')
			True
		"""
		if not self.is_path_valid(sd_path):
			if raise_errors:
				raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), sd_path)
			return False
		
		return self.is_path_valid(os.path.join(sd_path, 'DCIM'))
			
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

		Args:
			base_path (str): The base path to calculate checksums for.

		Returns:
			dict[str, str]: A dictionary of file paths to checksums.

		Raises:
			FileNotFoundError: If the base_path does not exist.

		Examples:
			>>> sd_cards = SDCards()
			>>> sd_cards.calculate_checksums('/media/SD_CARD')
			{
				'/media/SD_CARD/DCIM/100CANON/IMG_0001.JPG': 'a1b2c3d4e5f6...',
				'/media/SD_CARD/DCIM/100CANON/IMG_0002.JPG': 'dbb2s3dbe5d2...',
			}
		"""
		if not self.is_path_valid(base_path):
			raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), base_path)

		checksums = {}
		for root, _dirs, files in os.walk(base_path):
			for file in files:
				file_path = os.path.join(root, file)
				if os.path.isfile(file_path) and os.access(file_path, os.R_OK):
					checksums[file_path] = self.calculate_single_checksum(file_path)
				else:
					logger.error(f'File not accessible: {file_path}')

		return checksums
	
	def calculate_single_checksum(self, file_path: str) -> str:
		"""
		Calculate the checksum for a single file.
		
		Args:
			file_path (str): The path to the file.
			
		Returns:
			str: The checksum for the file.
			
		Raises:
			FileNotFoundError: If the file does not exist.
			
		Examples:
			>>> sd_cards = SDCards()
			>>> sd_cards.calculate_single_checksum('/media/SD_CARD/DCIM/100CANON/IMG_0001.JPG')
			'f3b4...
		"""
		with open(file_path, 'rb') as afile:
			hasher = hashlib.sha256()
			for buf in iter(lambda: afile.read(4096), b""):
				hasher.update(buf)
			return hasher.hexdigest()
			
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

		result = hasher.hexdigest()

		if result is None:
			logger.error('Failed to calculate checksum for file: {file_path}')
			raise ValueError(f'Failed to calculate checksum for file: {file_path}')
		
		return result
	
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
			sd_card_path (str): 
				The path to the SD card to copy.
			network_path (str): 
				The path to the network location to copy the SD card to. 
				NOTE: This destination should be a "Photography" directory, where the files will be organized and renamed.
			backup_network_path (str): 
				The path to the backup network location to copy the SD card to.
				This destination should be a "backup" directory, where the SD card will be copied exactly as-is.

		Returns:
			bool: True if the copy was successful, False otherwise.

		Examples:
			>>> copy_sd_card('/media/pi/SD_CARD', '/mnt/photography', '/mnt/backup')
			True
		"""
		logger.info('Copying sd card...')
		errors : list[str] = []

		# Ensure all paths have a trailing slash at the end
		sd_card_path = os.path.join(sd_card_path, '')
		network_path = os.path.join(network_path, '')
		backup_network_path = os.path.join(backup_network_path, '')

		# Check if paths are valid and writable
		if not all(map(self.is_path_valid, [sd_card_path, network_path, backup_network_path])):
			logger.critical('One or more paths are invalid')
			return False
		if not all(map(self.is_path_writable, [network_path, backup_network_path])):
			logger.critical('One or more paths are not writable')
			return False
		
		# Ensure a subdirectory exists for a temporary storage location
		temp_path = os.path.join(network_path, 'Import Bucket')
		if not os.path.exists(temp_path):
			os.makedirs(temp_path, exist_ok=True)
		if not self.is_path_writable(temp_path):
			logger.critical(f'Unable to write to temporary storage location: {temp_path}')
			return False

		# Calculate checksums before transferring anything
		checksums_before = self.calculate_checksums(sd_card_path)

		# Perform the backup first, using rsync.
		if not self.perform_rsync(sd_card_path, backup_network_path):
			logger.critical('Rsync Backup failed')
			errors.append('Rsync Backup failed')
			# Ask user if they want to continue
			if not self.ask_user_continue(errors):
				logger.critical('User chose to abort')
				return False

		# Validate checksums after rsync
		elif not self.validate_checksums(checksums_before, backup_network_path):
			logger.critical('Checksum validation failed on backup')
			errors.append('Checksum validation failed on backup')
			# Ask user if they want to continue
			if not self.ask_user_continue(errors):
				logger.critical('User chose to abort')
				return False
		
		# Perform the copy to the photography directory, using teracopy.
		if not self.perform_teracopy(sd_card_path, temp_path):
			logger.critical('TeraCopy failed')
			errors.append('TeraCopy failed')
			# Ask user if they want to continue
			if not self.ask_user_continue(errors):
				logger.critical('User chose to abort')
				return False
			
		# Organize the files that teracopy created
		results = self.organize_files(temp_path, network_path)

		# Map the temp_paths in results to the original sd_card paths
		files = {}
		for temp_file, network_file in results.items():
			filename = os.path.basename(temp_file)
			filepath = os.path.join(sd_card_path, filename)
			files[filepath] = network_file
		
		# Validate checksums after teracopy
		if not self.validate_checksum_list(checksums_before, files):
			logger.critical('Checksum validation failed on teracopy')
			errors.append('Checksum validation failed on teracopy')

		if len(errors) > 0:
			logger.critical('Copy failed due to previous errors.')
			return False

		return True

	def perform_rsync(self, source_path: str, destination_path: str) -> bool:
		"""
		Perform rsync from source to destination and handle retries.

		Args:
			source_path (str): The path to the source directory to copy.
			destination_path (str): The path to the destination directory to copy to.

		Returns:
			bool: True if the rsync was successful, False otherwise.
		"""
		for _ in range(MAX_RETRIES):
			try:
				subprocess.check_call(['rsync', '-av', '--checksum', source_path, destination_path])
				return True  
			except subprocess.CalledProcessError as e:
				logger.warning(f'rsync to {destination_path} failed with error code {e.returncode}, retrying...')
				time.sleep(1)
				
		logger.error(f'rsync to {destination_path} failed after {MAX_RETRIES} attempts')
		return False
	
	def perform_teracopy(self, source_path : str, destination_path: str) -> bool:
		"""
		Use teracopy to copy the source files to the destination directory and verify checksums.

		Args:
			source_path (str): The path to the source directory to copy.
			destination_path (str): The path to the destination directory to copy to.

		Returns:
			bool: True if the copy was successful, False otherwise.
		"""
		# Check if the teracopy.exe executable exists, otherwise default to rsync with a warning
		if not os.path.exists('teracopy.exe'):
			logger.warning('teracopy.exe not found, defaulting to rsync')
			return self.perform_rsync(source_path, destination_path)

		try:
			subprocess.check_call(['teracopy.exe', '/Copy', '/Verify', '/Close', '/SkipAll', '/NoConfirm', source_path, destination_path])
		except subprocess.CalledProcessError as e:
			logger.error(f'Copy to {destination_path} failed with error code {e.returncode}')
			return False

		return True
	
	def organize_files(self, source_path: str, destination_path: str) -> dict[str, str]:
		"""
		Organize files into folders by date, and rename them based on their attributes.
		See self.generate_path and self.generate_name for more details.

		Args:
			source_path (str): The path to the source directory to organize.
			destination_path (str): The path to the destination directory to organize to.

		Returns:
			dict[str, str]: A dictionary of the original file paths to the new file paths.
		"""
		results = {}

		# Find all files in the source_path, including all subdirectories
		files = []
		for root, _, filenames in os.walk(source_path):
			for filename in filenames:
				files.append(os.path.join(root, filename))

		# Organize files into folders by date, and rename them based on their attributes
		for file_path in files:
			# Generate the new file path
			new_file_path = self.generate_path(file_path, destination_path)

			# Create the directory if it doesn't exist
			os.makedirs(os.path.dirname(new_file_path), exist_ok=True)

			# Do not clobber existing files
			if os.path.exists(new_file_path):
				logger.error(f'File already exists: {new_file_path}')
				results[file_path] = None
				continue

			# Rename the file
			os.rename(file_path, new_file_path)
			results[file_path] = new_file_path

		return results

	def validate_checksums(self, checksums_before: dict[str, str], destination_path: str) -> bool:
		"""
		Validate checksums after rsync and report any mismatches.

		Args:
			checksums_before (dict[str, str]): A dictionary of file paths to checksums before rsync.
			destination_path (str): The path to the destination directory to validate checksums for.

		Returns:
			bool: True if the checksums were valid, False otherwise.
		"""
		checksums_after = self.calculate_checksums(destination_path)
		mismatches = 0

		with open(os.path.join(destination_path, 'checksum.txt'), 'w') as f:
			for file_path, checksum_before in checksums_before.items():
				# Get the destination path, based on the filename of the source
				filename = os.path.basename(file_path)
				copied_path = os.path.join(destination_path, filename)
				checksum_after = checksums_after.get(copied_path)
				if checksum_before == checksum_after:
					f.write(f'{file_path}: {checksum_before}\n')
				else:
					logger.critical(f'Checksum mismatch for {file_path}: {checksum_before} != {checksum_after}')
					mismatches += 1

		if mismatches:
			logger.critical(f'Checksum mismatch for {mismatches} files')
			return False

		return True
	
	def validate_checksum_list(self, checksums_before : dict[str, str], files : dict[str, str]) -> bool:
		"""
		Vaidate checksums after copying files and report any mismatches.

		Args:
			checksums_before (dict[str, str]): A dictionary of source file paths to checksums before copying.
			files (dict[str, str]): A dictionary of source file paths to destination file paths that were copied.

		Returns:
			bool: True if the checksums were valid, False otherwise.
		"""
		mismatches = 0
		logger.critical('Checksums before copying: %s', checksums_before)
		logger.critical('FILES: %s', files)

		# Loop over each file that was copied
		for source_file_path, destination_file_path in files.items():
			logger.critical('Searching for checksum for %s', source_file_path)
			# Get the checksum before copying
			checksum_before = checksums_before.get(source_file_path)
			if checksum_before is None:
				logger.critical(f'Checksum not found for {source_file_path}')
				mismatches += 1
				continue

			logger.critical('File 1: %s', source_file_path)
			logger.critical('File 2: %s', destination_file_path)

			# Get the checksum after copying
			checksum_after = self.calculate_checksum(destination_file_path)
			logger.critical('Checksum 1: %s', checksum_before)
			logger.critical('Checksum 2: %s', checksum_after)

			if checksum_before == checksum_after:
				logger.critical(f'Checksum match for {source_file_path}')
			else:
				logger.critical(f'Checksum mismatch for {source_file_path}: {checksum_before} != {checksum_after}')
				mismatches += 1

		if mismatches:
			logger.critical(f'Checksum list mismatch for {mismatches} files')
			return False

		return True
	
	def get_exif_data(self, file_path : str, key : str) -> str | float | int:
		"""
		Get the EXIF data from the given file.

		Args:
			file_path (str): The path to the file to get the EXIF data from.
			key (str): The key to get the EXIF data for.

		Returns:
			str | float | int: The EXIF data.

		Examples:
			>>> get_exif_data('/media/pi/SD_CARD/DCIM/100MSDCF/JAM_1234.arw', 'EXIF ExposureTime')
			{'EXIF ExposureTime': (1, 100)}
		"""
		with open(file_path, 'rb') as image_file:
			tags = exifread.process_file(image_file, details=False)

		# Convert from ASCII and Signed Ratio to string and float
		# address problems such as "AssertionError: (0x0110) ASCII=ILCE-7RM4 @ 340 != 'ILCE-7MR4'"
		value = tags[key]
		if isinstance(value, exifread.utils.Ratio):
			return value.decimal()
		if isinstance(value, exifread.classes.IfdTag):
			# If field type is an int, return an int
			if value.field_type in [3, 4, 8, 9]:
				return int(value.values[0])
			# If field type is a float, return a float
			if value.field_type in [11, 12]:
				return float(value.values[0])
			# If field type is a ratio or signed ratio, perform the division and reeturn a float
			if value.field_type in [5, 10]:
				return value.values[0].num / value.values[0].den
			return value.printable
		if isinstance(value, bytes):
			return value.decode('utf-8')
		if value is None:
			return None
    
		return exifread.utils.make_string(value)

	def get_camera_model(self, file_path : str) -> str:
		"""
		Get the camera model from the EXIF data of the given file.

		Args:
			file_path (str): The path to the file to get the camera model from.

		Returns:
			str: The camera model.

		Examples:
			>>> get_camera_model('/media/pi/SD_CARD/DCIM/100MSDCF/JAM_1234.arw')
			'a7r4'
		"""
		return self.get_exif_data(file_path, 'Image Model')
	
	def get_exposure_bias(self, file_path : str) -> float:
		"""
		Get the exposure bias from the EXIF data of the given file.

		Args:
			file_path (str): The path to the file to get the exposure bias from.

		Returns:
			str: The exposure bias.

		Examples:
			>>> get_exposure_bias('/media/pi/SD_CARD/DCIM/100MSDCF/JAM_1234.arw')
			'-2 7'
		"""
		result = self.get_exif_data(file_path, 'EXIF ExposureBiasValue')
		# Round up the 2nd decimal place, always
		return round(result, 2)
	
	def get_brightness_value(self, file_path : str) -> float:
		"""
		Get the brightness value from the EXIF data of the given file.

		Args:
			file_path (str): The path to the file to get the brightness value from.

		Returns:
			str: The brightness value.

		Examples:
			>>> get_brightness_value('/media/pi/SD_CARD/DCIM/100MSDCF/JAM_1234.arw')
			'-8.27'
		"""
		result = self.get_exif_data(file_path, 'EXIF BrightnessValue')

		# Round up the 2nd decimal place. Always round up, never down. 
		return round(result, 2)
	
	def get_iso_speed(self, file_path : str) -> str:
		"""
		Get the ISO speed from the EXIF data of the given file.

		Args:
			file_path (str): The path to the file to get the ISO speed from.

		Returns:
			str: The ISO speed.

		Examples:
			>>> get_iso_speed('/media/pi/SD_CARD/DCIM/100MSDCF/JAM_1234.arw')
			'800'
		"""
		return self.get_exif_data(file_path, 'EXIF ISOSpeedRatings')
	
	def get_lens(self, file_path : str) -> str:
		"""
		Get the lens from the EXIF data of the given file.

		Args:
			file_path (str): The path to the file to get the lens from.

		Returns:
			str: The lens.

		Examples:
			>>> get_lens('/media/pi/SD_CARD/DCIM/100MSDCF/JAM_1234.arw')
			'SAMYANG AF 12mm F2.0'
		"""
		return self.get_exif_data(file_path, 'EXIF LensModel')
	
	def get_filename_number_suffix(self, file_path : str) -> str:
		"""
		Get the filename number suffix from the given file. The number suffix is any number of digits at the end of the filename.

		Args:
			file_path (str): The path to the file to get the filename number suffix from.

		Returns:
			str: The filename number suffix.

		Examples:
			>>> get_filename_number_suffix('/media/pi/SD_CARD/DCIM/100MSDCF/JAM_1234.arw')
			'1234'
		"""
		matches = re.search(r'(\d+)(\.[a-zA-Z]{1,5})?$', file_path)
		if matches is None:
			return None
		return int(matches.group(1))
	
	def get_file_extension(self, file_path : str) -> str:
		"""
		Get the file extension from the given file.

		Args:
			file_path (str): The path to the file to get the file extension from.

		Returns:
			str: The file extension.

		Examples:
			>>> get_file_extension('/media/pi/SD_CARD/DCIM/100MSDCF/JAM_1234.arw')
			'arw'
		"""
		# If there is no decimal, then there is no extension
		if '.' not in file_path:
			return ""

		return file_path.split('.')[-1]
	
	def get_shutter_speed(self, file_path : str) -> float:
		"""
		Get the shutter speed from the EXIF data of the given file.

		Args:
			file_path (str): The path to the file to get the shutter speed from.

		Returns:
			float: The shutter speed (as a float, not a ratio)

		Examples:
			>>> get_shutter_speed('/media/pi/SD_CARD/DCIM/100MSDCF/JAM_1234.arw')
			'0.0125'
		"""
		result = self.get_exif_data(file_path, 'EXIF ExposureTime')
		# Round up the 10th decimal place, always
		return round(result, 10)
	
	def generate_name(self, file_path : str, short : bool = False) -> str:
		"""
		Generate a name for the photo we are copying. 
		
		The name is in the format:
		{YYYYmmdd}_{camera model}_{filename number suffix}_{exposure-bias}_{brightness value}_{ISO speed}_{shutter speed}_{Lens}.{extension}

		The filename number suffix comes from the last 4 digits of the filename (e.g. JAM_1234.jpg -> 1234).

		Args:
			file_path (str): The path to the file to generate a name for.
			short (bool, optional): Whether to generate a short name. Defaults to False.

		Returns:
			str: The generated name.

		Examples:
			>>> generate_name('/media/pi/SD_CARD/DCIM/100MSDCF/JAM_1234.arw')
			'20230805_a7r4-1234_-2 7_10EV_8.27B_800ISO_SAMYANG AF 12mm F2.0.arw'
			>>> generate_name('/media/pi/SD_CARD/DCIM/100MSDCF/JAM_1234.arw', short=True)
			'1234_-2 7_10EV_8.27B.arw'
		"""

		# Get the filename number suffix
		filename_number_suffix = self.get_filename_number_suffix(file_path)

		# Get the exposure bias
		exposure_bias = self.get_exposure_bias(file_path)

		# Get the brightness value
		brightness_value = self.get_brightness_value(file_path)

		# Get the ISO speed
		iso_speed = self.get_iso_speed(file_path)

		# Get the shutter speed
		shutter_speed = self.get_shutter_speed(file_path)

		# Get the extension
		extension = self.get_file_extension(file_path)

		if short is True:
			# Generate the name
			name = f'{filename_number_suffix}_{exposure_bias}EV_{brightness_value}B_{iso_speed}ISO_{shutter_speed}SS'
		else:
			# Get the current date and time
			now = datetime.datetime.now()
			# Get the lens
			lens = self.get_lens(file_path)
			# Get the camera model
			camera_model = self.get_camera_model(file_path)

			# Generate the name
			name = f'{now:%Y%m%d}_{camera_model}_{filename_number_suffix}_{exposure_bias}EV_{brightness_value}B_{iso_speed}ISO_{shutter_speed}SS_{lens}'
	
		# Convert any decimal points to spaces
		name = name.replace('.', ' ')

		return f'{name}.{extension}'
	
	def generate_path(self, file_path : str, network_path : str) -> str:
		"""
		Figure out an appropriate path to copy the file, given its creation date. 
		
		The path is in the format:
		{network_path}/{YYYY}/{YYYY-mm-dd}/{filename}

		NOTE: generate_name is used to generate the filename, so the resulting file will be renamed.
		
		Args:
			file_path (str): The path to the file to generate a path for.
			network_path (str): The path to the network location to copy the file to.

		Returns:
			str: The generated path.

		Examples:
			>>> generate_path('/media/pi/SD_CARD/DCIM/100MSDCF/JAM_1234.arw', '/media/pi/NETWORK')
			'/media/pi/NETWORK/2023/2023-08-05/20230805_a7r4-1234_-2 7_10EV_8.27B_800ISO_SAMYANG AF 12mm F2.0.arw'
		"""
		# Get the current date and time
		now = datetime.datetime.now()

		# Get the new filename
		filename = self.generate_name(file_path)

		# Check if the path will be longer than 255 characters
		extension = self.get_file_extension(filename)
		#        MAX   Path                Extension      ---.  Date (2023/2023-01-05/)
		buffer = 254 - len(network_path) - len(extension) - 4 - 16
		if buffer < 1:
			# No room for even a truncated filename
			raise ValueError(f'Path is too long: {network_path}')
		elif buffer < len(filename):
			# First, try re-generating a name without the camera model or lens, and a shortened date.
			filename = self.generate_name(file_path, short=True)

			if buffer < len(filename):
				# No dice! Truncate the filename
				filename = f'{filename[:buffer]}---.{extension}'

		# Generate the path again
		path = f'{network_path}/{now:%Y}/{now:%Y-%m-%d}/{filename}'

		return path
	
	def ask_user_continue(self, errors : list) -> bool:
		"""
		Ask the user if they want to continue copying the SD card, given the errors that occurred, using the CLI.
		
		Args:
			errors (list): The errors that occurred.
			
		Returns:
			bool: Whether the user wants to continue copying the SD card.
		"""
		# Print the errors
		print('Errors were found: ')
		for error in errors:
			print(error)

		# Ask the user if they want to continue
		choice = input('Continue to the next step? [y/n] ')
		if choice.lower() == 'y':
			return True
		else:
			return False

def main():
	"""
	Entry point for the application.
	"""
	# Parse command line arguments
	parser = argparse.ArgumentParser(description='Copy the SD card to a network location.')
	parser.add_argument('--sd-card-path', type=str, help='The path to the SD card to copy.')
	parser.add_argument('--network-path', default="P:/", type=str, help='The path to the network location to copy the SD card to.')
	parser.add_argument('--backup-network-path', default="S:/SD Backup/", type=str, help='The path to the backup network location to copy the SD card to.')
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