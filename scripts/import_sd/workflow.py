from __future__ import annotations
import argparse
import datetime
from enum import Enum
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

from scripts.import_sd.config import MAX_RETRIES
from scripts.import_sd.operations import CopyOperation
from scripts.import_sd.validator import Validator
from scripts.import_sd.photo import Photo
from scripts.import_sd.queue import Queue
from scripts.import_sd.sd import SDCard

logger = logging.getLogger(__name__)

class Workflow:
	"""
	Allows us to interact with sd cards mounted to the server this code is running on.
	"""
	_raw_path: str
	_jpg_path: str
	_backup_path: str
	_sd_card : SDCard = None
	_temp_path : str = None
	raw_extension : str

	def __init__(self, raw_path : str, jpg_path : str, backup_path : str, raw_extension : str = 'arw', sd_card : Optional[str | SDCard] = None):
		"""
		Args:
			raw_path (str): 
				The path to the network location to copy raw files from the SD Card to. 
				NOTE: This destination should be a "Photography" directory, where the files will be organized and renamed.
			jpg_path (str):
				The path to the network location to copy jpg files from the SD Card to.
			backup_path (str): 
				The path to the backup network location to copy the SD card to.
				This destination should be a "backup" directory, where the SD card will be copied exactly as-is.
			raw_extension (str):
				The file extension of the raw files to copy. Defaults to 'arw'.
			sd_card (str | None): 
				The SDCard (or a path to an SD card) to copy. Defaults to attempting to find the SD card automatically.
		"""
		self.raw_path = raw_path
		self.jpg_path = jpg_path
		self.backup_path = backup_path
		self.raw_extension = raw_extension

		# If no sd_path is provided, try to find it
		if sd_card is None:
			self.sd_path = SDCard.get_media_dir()
		else:
			self.sd_card = sd_card

	@property
	def sd_card(self) -> SDCard:
		"""
		The SDCard to copy.
		"""
		if self._sd_card is None:
			media_dir = SDCard.get_media_dir()
			if media_dir is None:
				raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), 'SD Card not found')
			return SDCard(media_dir)
		return self._sd_card
	
	@sd_card.setter
	def sd_card(self, sd_card: SDCard | str) -> None:
		"""
		Set the SDCard to copy.

		Args:
			sd_card (SDCard | str): The SDCard (or a path to an SD card) to copy.
		"""
		if isinstance(sd_card, SDCard):
			self._sd_card = sd_card
		else:
			self._sd_card = SDCard(sd_card)

	@property
	def raw_path(self) -> str:
		"""
		The path to the network location to copy raw files from the SD Card to.
		"""
		return self._raw_path
	
	@raw_path.setter
	def raw_path(self, raw_path: str) -> None:
		"""
		Set the path to the network location to copy raw files from the SD Card to.

		Args:
			raw_path (str): The path to the network location to copy raw files from the SD Card to.
		"""
		if not Validator.is_dir(raw_path):
			raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), raw_path)
		# Ensure trailing slash
		self._raw_path = os.path.join(raw_path, '')

	@property
	def jpg_path(self) -> str:
		"""
		The path to the network location to copy jpg files from the SD Card to.
		"""
		return self._jpg_path
	
	@jpg_path.setter
	def jpg_path(self, jpg_path: str) -> None:
		"""
		Set the path to the network location to copy jpg files from the SD Card to.
		
		Args:
			jpg_path (str): The path to the network location to copy jpg files from the SD Card to.
		"""
		if not Validator.is_dir(jpg_path):
			raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), jpg_path)
		# Ensure trailing slash
		self._jpg_path = os.path.join(jpg_path, '')

	@property
	def backup_path(self) -> str:
		"""
		The path to the backup network location to copy the SD card to.
		"""
		return self._backup_path
	
	@backup_path.setter
	def backup_path(self, backup_path: str) -> None:
		"""
		Set the path to the backup network location to copy the SD card to.
		
		Args:
			backup_path (str): The path to the backup network location to copy the SD card to.
		"""
		if not Validator.is_dir(backup_path):
			raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), backup_path)
		# Ensure trailing slash
		self._backup_path = os.path.join(backup_path, '')

	@property
	def temp_path(self) -> str:
		"""
		The path to the temporary directory to copy the SD card to.
		"""
		if not self._temp_path:
			# Create an "Import Bucket" folder in the raw_path
			self._temp_path = os.path.join(self.raw_path, 'Import Bucket')
			if not Validator.is_dir(self._temp_path):
				os.makedirs(self._temp_path, exist_ok=True)

			if not Validator.is_writeable(self._temp_path):
				logger.error(f'Unable to write to temporary storage location: {self._temp_path}')
				raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), self._temp_path)

		return self._temp_path

	def run(self, operation : CopyOperation = CopyOperation.TERACOPY) -> bool:
		"""
		Copy the SD card to several different network locations, and verify checksums after copy.

		Args:
			operation (CopyOperation):
				The copy operation to use. Defaults to Teracopy.

		Returns:
			bool: True if the copy was successful, False otherwise.

		Examples:
			>>> workflow = Workflow('/media/pi/SD', '/media/pi/Network', '/media/pi/Backup')
			>>> workflow.run()
			True
		"""
		logger.info('Copying sd card...')
		errors : list[str] = []

		# Check if paths are valid and writable
		if not all(map(Validator.is_dir, [self.sd_path, self.raw_path, self.jpg_path, self.backup_path])):
			logger.error('One or more paths are invalid')
			return False
		if not all(map(Validator.is_writeable, [self.raw_path, self.jpg_path, self.backup_path])):
			logger.error('One or more paths are not writable')
			return False

		# Calculate checksums before transferring anything
		checksums_before = Validator.calculate_checksums(self.sd_path)

		# Create a list of files that need to be copied
		queue = self.queue_files()
		# HEREE I left off here for the day.
		(list_path, files_to_copy, skipped, mismatched) = self.create_filelist()

		if files_to_copy:
			# Perform the backup first
			if not self.copy_from_list(list_path, checksums_before, operation):
				errors.append(f'Copy operation failed to {self.backup_path}')
			
			# Perform the copy to the photography directory
			if not self.copy_from_list(list_path, self.temp_path, checksums_before, operation):
				errors.append(f'Copy operation failed to {self.temp_path}')
				
			# Organize the files that were created
			results = self.organize_files(self.temp_path)
			if not results:
				logger.error('Failed to organize files, cannot continue')
				logger.critical('The system state may be inconsistent or unexpected. Please verify all files are in the correct location.')
				return False

			# Map the temp_paths in results to the original sd_card paths
			files = {}
			for temp_file, network_file in results.items():
				filename = os.path.basename(temp_file)
				filepath = os.path.join(self.sd_path, filename)
				files[filepath] = network_file
			
			# Validate checksums after teracopy
			if not Validator.validate_checksum_list(checksums_before, files):
				logger.critical('Checksum validation failed on operation %s', operation)
				errors.append('Checksum validation failed on operation %s' % operation)

		if len(errors) > 0:
			logger.critical('Copy failed due to previous errors.')
			return False

		return True
	
	def copy_from_list(self, list_path : str, destination_path: str, checksums_before : dict[str, str], operation : CopyOperation = CopyOperation.TERACOPY) -> bool:
		"""
		Perform a copy from a list of files to a destination using an arbitrary method, and verify checksums.
		
		This method exists to allow us to swap out different copy methods without changing the main logic.
		
		Args:
			list_path (str): The path to the list of files to copy.
			destination_path (str): The path to the destination directory to copy to.
			checksums_before (dict[str, str]): The checksums of the files before the copy.
			operation (CopyOperation): The copy operation to use. Defaults to Teracopy.
			
		Raises:
			KeyboardInterrupt: If errors occur during copy and the user chooses to abort.
			FileNotFoundError: If either path does not exist.
			ValueError: If an invalid copy operation is specified.

		Returns:
			bool: True if the copy was successful without any errors, False otherwise.
		"""
		success = True

		# Figure out which copy operation to use
		if operation == CopyOperation.TERACOPY:
			perform_copy = self.teracopy_from_list
		elif operation == CopyOperation.RSYNC:
			raise NotImplementedError('Rsync is not yet implemented for file lists')
		else:
			raise ValueError('Invalid copy operation specified')

		# Perform the backup first
		if not perform_copy(list_path, destination_path):
			logger.critical('Perform copy failed for %s', destination_path)
			# Ask user if they want to continue
			self.ask_user_continue('Copy failed')
			success = False

		# Validate checksums after copy
		if not Validator.validate_checksums(checksums_before, destination_path):
			logger.critical('Checksum validation failed for %s', destination_path)
			# Ask user if they want to continue
			self.ask_user_continue('Checksum validation failed')
			success = False

		return success

	@classmethod
	def rsync(cls, source_path: str, destination_path: str) -> bool:
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
	
	@classmethod
	def teracopy(cls, source_path : str, destination_path: str) -> bool:
		"""
		Use teracopy to copy the source files to the destination directory and verify checksums.

		Args:
			source_path (str): The path to the source directory to copy.
			destination_path (str): The path to the destination directory to copy to.

		Returns:
			bool: True if the copy was successful, False otherwise.
		"""
		try:
			subprocess.check_call(['teracopy.exe', 'Copy', source_path, destination_path, '/NoClose', '/RenameAll'])
		except subprocess.CalledProcessError as e:
			logger.error(f'Teracopy to {destination_path} failed with error code {e.returncode}')
			return False

		return True
	
	@classmethod
	def teracopy_from_list(cls, list_path : str, destination_path: str) -> bool:
		"""
		Use teracopy to copy files using a list of file paths to the destination directory and verify checksums.

		Args:
			list_path (str): The path to the list of files to copy.
			destination_path (str): The path to the destination directory to copy to.

		Returns:
			bool: True if the copy was successful, False otherwise.
		"""
		if not os.path.exists(list_path):
			raise FileNotFoundError(f'File list {list_path} does not exist')
		
		try:
			subprocess.check_call(['teracopy.exe', 'Copy', f'*"{list_path}"', destination_path, '/NoClose', '/SkipAll'])
		except subprocess.CalledProcessError as e:
			logger.error(f'Teracopy to {destination_path} failed with error code {e.returncode}')
			return False

		return True
	
	def queue_files(self) -> Queue:
		"""
		Figure out which files need to be copied and return a map that can be iterated over.

		NOTE: No files are actually copied in this method.
		
		Returns:
			Queue: A mapping of destination paths to a list of source paths that will be copied there, along with metadata.

		Examples:
			>>> workflow = Workflow('P:/', 'P:/Thumbnails/', 'S:/SD Backup/', 'ARW', 'I:/')
			>>> workflow.queue_files().to_dict()
			{
				'queue': {
					'S:/SD Backup/139523': [
						'I:/DCIM/139523/IMG_001.ARW',
						'I:/DCIM/139523/IMG_001.jpg',
						'I:/DCIM/139523/IMG_002.ARW',
						'I:/DCIM/139523/IMG_002.jpg',
					],
					'P:/Import Bucket/139523/': [
						'I:/DCIM/139523/IMG_001.ARW',
						'I:/DCIM/139523/IMG_002.ARW',
					],
					'P:/Thumbnails/139523/': [
						'I:/DCIM/139523/IMG_001.jpg',
						'I:/DCIM/139523/IMG_002.jpg',
					]
				},
				'skipped': [
					'I:/DCIM/139523/IMG_003.ARW',
				],
				'mismatched': {
					'P:/Import Bucket/139523/IMG_004.ARW': 'I:/DCIM/139523/IMG_004.ARW',
				},
				'checksums': {
					'I:/DCIM/139523/IMG_001.ARW': 'a1b2c3d4...',
					'I:/DCIM/139523/IMG_002.ARW': 'e5f6g7h8...',
				}
			}
		"""
		# Get a list of files that need to be copied
		files = Queue()

		for root, _, filenames in os.walk(self.sd_path):
			for filename in filenames:
				filepath = os.path.join(root, filename)
				folder = SDCard.determine_subpath(filepath)
				backup_path = os.path.join(self.backup_path, folder)
				photo = Photo(filepath)
				skip_count = 0
			
				# Add RAW extensions to the raw_path, jpg extensions to the jpg_path, and all files to the backup_path
				if photo.extension == self.raw_extension:
					full_path = Photo(os.path.join(self.raw_path, folder))
				elif photo.is_jpg():
					full_path = Photo(os.path.join(self.jpg_path, folder))
				else:
					logger.warning(f'Unknown file type {filename}')
					continue

				# Check if the file already exists in the destination
				if full_path.exists():
					if photo.matches(full_path):
						logger.debug(f'{filepath} already exists in {full_path}')
						skip_count += 1
					else:
						files.append(full_path, photo)
						files.flag(photo, full_path)
				else:
					files.append(full_path, photo)

				# Check if the file already exists in the backup
				backup_file = Photo(os.path.join(backup_path, filename))
				if backup_file.exists():
					if photo.matches(backup_file):
						logger.debug(f'{photo.path} already exists in {backup_file.path}')
						skip_count += 1
					else:
						files.append(backup_file, photo)
						files.flag(photo, backup_file)
				else:
					files.append(backup_file, photo)

				# If the file is in all destinations, skip it
				if skip_count >= 2:
					files.skip(photo)

		logger.info('Queueing %d files to copy', files.count())
		return files
	
	def create_filelist(self, destination_path : str, list_path : Optional[str] = None) -> tuple[str, list[str], list[str], dict[str, str]]:
		"""
		Generates a list of files to copy to a given folder.

		This is used for tools like teracopy. 
		
		When files are present in the destination path, checksums are verified to ensure they are identical.

		NOTE: It is assumed that files in the destination_path are named and organized via generate_name and generate_path.

		Args:
			destination_path (str): The path to the destination directory to copy to.
			list_path (str): A path to the list file we wish to write. It will be created if it does not exist.

		Raises:
			KeyboardInterrupt: If the conflicting files exist and the user chooses to abort the program.
			FileNotFoundError: If one of the paths provided does not exist.
			
		Returns:
			tuple[str, list[str], list[str], dict[str, str]]: A tuple containing the list_path, a list of files to copy, a list of files skipped, and a dictionary of mismatched files.
		"""
		queue = self.queue_files()
		queue.write(destination_path, list_path)

		# TODO: These stats refer to the entire queue, not just the destination_path
		to_copy = queue.count('queue')
		to_skip = queue.count('skipped')
		mismatch_count = queue.count('mismatched')
		logger.info(f'List created. ({to_copy} to copy, {to_skip} to skip, {mismatch_count} mismatches)')
		'''
		if len(mismatches) > 0:
			logger.critical('Checksum mismatches were found %s', message)
			errors = [f'{source_file} -> {destination_file}' for source_file, destination_file in mismatches.items()]
			self.ask_user_continue(f'WARNING: Checksum mismatches were found {message}:', errors)
		'''

		return (list_path, queue, to_skip, mismatch_count)
		
	def organize_files(self) -> dict[str, str]:
		"""
		Organize files into folders by date, and rename them based on their attributes.
		See self.generate_path and self.generate_name for more details.

		Returns:
			dict[str, str]: A dictionary of the original file paths to the new file paths.
		"""
		results = {}

		# Verify the paths exist
		if not all([os.path.exists(path) for path in [self.temp_path, self.raw_path]]):
			logger.info('One or more of the paths provided does not exist: "%s", "%s"', self.temp_path, self.raw_path)
			raise FileNotFoundError('One or more of the paths provided does not exist.')

		# Find all files in the source_path, including all subdirectories
		files = []
		for root, _, filenames in os.walk(self.temp_path):
			for filename in filenames:
				files.append(os.path.join(root, filename))

		# Organize files into folders by date, and rename them based on their attributes
		for file_path in files:
			# Generate the new file path
			new_file_path = self.generate_path(file_path, self.raw_path)

			# Create the directory if it doesn't exist
			os.makedirs(os.path.dirname(new_file_path), exist_ok=True)

			# Do not clobber existing files
			if os.path.exists(new_file_path):
				# Compare checksums
				if Validator.compare_checksums(file_path, new_file_path):
					logger.debug('File already exists with the same content, skipping...')
					results[file_path] = new_file_path
					continue

				# If checksums don't match, we want to keep both copies. Try appending to the name until we have a unique name.
				logger.warning('File already exists, but checksums mismatch. Keeping both files.')
				mismatched_file_path = new_file_path
				for i in range(1, 1000):
					new_file_path = f'{mismatched_file_path} ({i})'
					if not os.path.exists(new_file_path):
						break
				
				# If we couldn't find a unique name, skip the file
				if os.path.exists(new_file_path):
					logger.critical(f'Could not find a unique name for {file_path}')
					self.ask_user_continue(f'Checksums mismatch for {file_path}, and cannot create a unique name for it.')
					results[file_path] = None
					continue

			# Rename the file
			os.rename(file_path, new_file_path)
			results[file_path] = new_file_path

		return results
	
	def generate_name(self, photo : Photo | str, short : bool = False) -> str:
		"""
		Generate a name for the photo we are copying. 
		
		The name is in the format:
		{YYYYmmdd}_{camera model}_{filename number suffix}_{exposure-bias}_{brightness value}_{ISO speed}_{shutter speed}_{Lens}.{extension}

		The filename number suffix comes from the last 4 digits of the filename (e.g. JAM_1234.jpg -> 1234).

		Args:
			photo (Photo | str): The photo to generate a name for. If a str, it is assumed to be the file path.

		Returns:
			str: The generated name.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/JAM_1234.arw')
			>>> generate_name(photo)
			'20230805_a7r4-1234_-2 7_10EV_8.27B_800ISO_SAMYANG AF 12mm F2.0.arw'
			>>> generate_name('/media/pi/SD_CARD/DCIM/100MSDCF/JAM_1234.arw', short=True)
			'1234_-2 7_10EV_8.27B.arw'
		"""
		if isinstance(photo, str):
			photo = Photo(photo)

		if short is True:
			# Generate the name
			name = f'{photo.number}_{photo.exposure_bias}EV_{photo.brightness}B_{photo.iso}ISO_{photo.ss}SS'
		else:
			# Generate the name
			name = f'{photo.date:%Y%m%d}_{photo.camera}_{photo.number}_{photo.exposure_bias}EV_{photo.brightness}B_{photo.iso}ISO_{photo.ss}SS_{photo.lens}'
	
		# Convert any decimal points to spaces
		name = name.replace('.', ' ')

		return f'{name}.{photo.extension}'
	
	def generate_path(self, photo : Photo | str) -> str:
		"""
		Figure out an appropriate path to copy the file, given its creation date. 
		
		The path is in the format:
		{network_path}/{YYYY}/{YYYY-mm-dd}/{filename}

		NOTE: generate_name is used to generate the filename, so the resulting file will be renamed.
		
		Args:
			photo (Photo | str): The photo to generate a path for. If a str, it is assumed to be the file path.

		Returns:
			str: The generated path.

		Examples:
			>>> generate_path('/media/pi/SD_CARD/DCIM/100MSDCF/JAM_1234.arw')
			'/media/pi/NETWORK/2023/2023-08-05/20230805_a7r4-1234_-2 7_10EV_8.27B_800ISO_SAMYANG AF 12mm F2.0.arw'
		"""
		if isinstance(photo, str):
			photo = Photo(photo)

		# Get the new filename
		filename = self.generate_name(photo)

		#        MAX   Path                 Extension           ---.  Date (2023/2023-01-05/)
		buffer = 254 - len(self.raw_path) - len(photo.extension) - 4 - 16
		if buffer < 1:
			# No room for even a truncated filename
			raise ValueError(f'Path is too long: {self.raw_path}')
		elif buffer < len(filename):
			# First, try re-generating a name without the camera model or lens, and a shortened date.
			filename = self.generate_name(photo, short=True)

			if buffer < len(filename):
				# No dice! Truncate the filename
				filename = f'{filename[:buffer]}---.{photo.extension}'

		# Generate the path again
		path = f'{self.raw_path}/{photo.date:%Y}/{photo.date:%Y-%m-%d}/{filename}'

		return path
	
	@classmethod
	def ask_user_continue(cls, message : str = f"Errors were found:", errors : Optional[list] = None, continue_message : str = "Continue to the next step? [y/n]", throw_error : bool = True) -> bool:
		"""
		Ask the user if they want to continue copying the SD card, given the errors that occurred, using the CLI.
		
		Args:
			message (str, optional): The message to print to the user. Defaults to f"Errors were found:".
			errors (list): The errors that occurred.
			continue_message (str, optional): The message to print to the user to ask if they want to continue. Defaults to "Continue to the next step? [y/n]".
			throw_error (bool, optional): Whether to throw an error if the user decides to abort. Defaults to True. If false, the function will return a bool.
			
		Returns:
			bool: Whether the user wants to continue copying the SD card.
		"""
		if errors is None:
			errors = []

		# Print the errors
		print(message + ' ')
		for error in errors:
			print(error)

		# Ask the user if they want to continue
		choice = input(continue_message + ' ')
		if choice.lower() == 'y':
			logger.info('User decided to continue.')
			return True
		else:
			logger.info('User decided to abort.')
			if throw_error:
				raise KeyboardInterrupt('User decided to abort. Prompt was "%s"', message)
			return False

def main():
	"""
	Entry point for the application.
	"""
	# Parse command line arguments
	parser = argparse.ArgumentParser(description='Copy the SD card to a network location.')
	parser.add_argument('--sd-path', '-s', type=str, help='The path to the SD card to copy.')
	parser.add_argument('--raw-path', '-r', default="P:/", type=str, help='The path to the network location to copy RAWs from the SD card to.')
	parser.add_argument('--jpg-path', '-j', default="P:/jpgs/", type=str, help='The path to the network location to copy JPGs from the SD card to.')
	parser.add_argument('--extension', '-e', default="arw", type=str, help='The extension to use for RAW files.')
	parser.add_argument('--backup-path', '-b', default="S:/SD Backup/", type=str, help='The path to the backup network location to copy the SD card to.')
	args = parser.parse_args()

	# Set up logging
	logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler()])

	# Copy the SD card
	workflow = Workflow(args.raw_path, args.jpg_path, args.backup_path, args.extension, args.sd_path)
	result = workflow.run()

	# Exit with the appropriate code
	if result:
		logger.info('SD card copy successful')
		sys.exit(0)

	logger.error('SD card copy failed')
	sys.exit(1)

if __name__ == '__main__':
	# Keep terminal open until script finishes and user presses enter
	try:
		main()
	except KeyboardInterrupt:
		pass

	input('Press Enter to exit...')