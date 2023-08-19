"""
	
	Metadata:
	
		File: workflow.py
		Project: workflows
		Created Date: 11 Aug 2023
		Author: Jess Mann
		Email: jess.a.mann@gmail.com
	
		-----
	
		Last Modified: Fri Aug 18 2023
		Modified By: Jess Mann
	
		-----
	
		Copyright (c) 2023 Jess Mann
"""
from __future__ import annotations
import argparse
import datetime
from enum import Enum
import errno
import os
import re
import sys
import subprocess
import logging
import time
from typing import Any, Dict, Optional, TypedDict
import exifread, exifread.utils, exifread.tags.exif, exifread.classes

from scripts.import_sd.config import MAX_RETRIES
from scripts.import_sd.operations import CopyOperation
from scripts.import_sd.validator import Validator
from scripts.import_sd.path import FilePath
from scripts.import_sd.photo import Photo
from scripts.import_sd.queue import Queue
from scripts.import_sd.sd import SDCard
from scripts.import_sd.workflow import Workflow

logger = logging.getLogger(__name__)

class CopyWorkflow(Workflow):
	"""
	Allows us to interact with sd cards mounted to the server this code is running on.
	"""
	_base_path: str
	_jpg_path: str
	_backup_path: str
	_sd_card : SDCard = None
	_bucket_path : str = None
	raw_extension : str
	dry_run : bool = False

	def __init__(self, base_path : str, jpg_path : str, backup_path : str, raw_extension : str = 'arw', sd_card : Optional[str | SDCard] = None, dry_run : bool = False):
		"""
		Args:
			base_path (str): 
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
			dry_run (bool):
				Whether or not to actually copy files. Defaults to False.
		"""
		self.base_path = base_path
		self.jpg_path = jpg_path
		self.backup_path = backup_path
		self.raw_extension = raw_extension
		self.dry_run = dry_run

		# If no sd_path is provided, try to find it
		if sd_card is not None:
			self.sd_card = sd_card
		else:
			self.sd_card = SDCard.get_media_dir()

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
	def base_path(self) -> str:
		"""
		The path to the network location to copy raw files from the SD Card to.
		"""
		return self._base_path
	
	@base_path.setter
	def base_path(self, base_path: str) -> None:
		"""
		Set the path to the network location to copy raw files from the SD Card to.

		Args:
			base_path (str): The path to the network location to copy raw files from the SD Card to.
		"""
		if not Validator.is_dir(base_path):
			raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), base_path)
		self._base_path = self._normalize_path(base_path)

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
		self._jpg_path = self._normalize_path(jpg_path)

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
		self._backup_path = self._normalize_path(backup_path)

	@property
	def bucket_path(self) -> str:
		"""
		The path to the temporary directory to copy the SD card to.
		"""
		if not self._bucket_path:
			# Create an "Import Bucket" folder in the base_path
			self._bucket_path = os.path.join(self.base_path, 'Import Bucket')
			if not Validator.is_dir(self._bucket_path):
				os.makedirs(self._bucket_path, exist_ok=True)

			if not Validator.is_writeable(self._bucket_path):
				logger.error(f'Unable to write to temporary storage location: {self._bucket_path}')
				raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), self._bucket_path)

		return self._bucket_path
		
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
		if not all(map(Validator.is_dir, [self.sd_card.path, self.base_path, self.jpg_path, self.backup_path])):
			logger.error('One or more paths are invalid')
			return False
		if not all(map(Validator.is_writeable, [self.base_path, self.jpg_path, self.backup_path])):
			logger.error('One or more paths are not writable')
			return False

		# Create a list of files that need to be copied
		queue = self.queue_files()

		# Copy files to each destination path
		for destination, files in queue.get_queue():
			# Write the queue to a file, so we have a path to pass teracopy
			list_path = queue.write(destination)

			# Begin copying
			result = self.copy_from_list(list_path, destination, queue.get_checksums(), operation)

			if not result:
				errors.append(f'Copy operation failed to {destination}')

		# Organize files in the base_path
		results = self.organize_files(self.bucket_path)
		if not results:
			logger.error('Failed to organize files, cannot continue')
			logger.critical('The system state may be inconsistent or unexpected. Please verify all files are in their correct locations.')
			return False

		# Map the temp_paths in results to the original sd_card paths
		files = {}
		for temp_file, network_file in results.items():
			filename = os.path.basename(temp_file)
			filepath = os.path.join(self.sd_card.path, filename)
			files[filepath] = network_file
		
		# Validate checksums after teracopy
		if not Validator.validate_checksum_list(queue.get_checksums(), files):
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
		if self.dry_run:
			raise NotImplementedError('Dry run is not yet implemented for file lists')
		
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

		for root, _, filenames in os.walk(self.sd_card.path):
			for filename in filenames:
				filepath = os.path.join(root, filename)
				folder = self.sd_card.determine_subpath(filepath)
				photo = Photo(filepath)
			
				# Add RAW extensions to the base_path, jpg extensions to the jpg_path, and all files to the backup_path
				if photo.extension == self.raw_extension:
					# Only append the RAW file if it doesn't exist (or mismatches) the FINAL location it will end up in, after it is organized.
					final_path = self.generate_path(photo)
					if not os.path.exists(final_path) or not photo.matches(final_path):
						files.append_parts(photo, [self.bucket_path, folder, filename])
				elif photo.is_jpg():
					files.append_parts(photo, [self.jpg_path, folder, filename])
				else:
					logger.warning(f'Unknown file type {filename}')
					continue

				# Add ALL files to the backup path
				files.append_parts(photo, [self.backup_path, folder, filename])

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
		if not all([os.path.exists(path) for path in [self.bucket_path, self.base_path]]):
			logger.info('One or more of the paths provided does not exist: "%s", "%s"', self.bucket_path, self.base_path)
			raise FileNotFoundError('One or more of the paths provided does not exist.')

		# Find all files in the source_path, including all subdirectories
		files = []
		for root, _, filenames in os.walk(self.bucket_path):
			for filename in filenames:
				files.append(os.path.join(root, filename))

		# Organize files into folders by date, and rename them based on their attributes
		for file_path in files:
			# Generate the new file path
			new_file_path = self.generate_path(file_path)

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
			if not self.dry_run:
				os.rename(file_path, new_file_path)
			else:
				logger.info(f'Would rename {file_path} ----> {new_file_path}')
			results[file_path] = new_file_path

		return results

def main():
	"""
	Entry point for the application.
	"""
	# Parse command line arguments
	parser = argparse.ArgumentParser(
		description='Copy the SD card to a network location.',
		prog=f'{os.path.basename(sys.argv[0])} {sys.argv[1]}'
	)
	# Ignore the first argument, which is the script name
	parser.add_argument('ignored', nargs='?', help=argparse.SUPPRESS)
	parser.add_argument('--sd-path', '-s', default=None, type=str, help='The path to the SD card to copy.')
	parser.add_argument('--base-path', '-r', default="R:/", type=str, help='The path to the network location to copy RAWs from the SD card to.')
	parser.add_argument('--jpg-path', '-j', default="P:/jpgs/", type=str, help='The path to the network location to copy JPGs from the SD card to.')
	parser.add_argument('--extension', '-e', default="arw", type=str, help='The extension to use for RAW files.')
	parser.add_argument('--backup-path', '-b', default="S:/SD Backup/", type=str, help='The path to the backup network location to copy the SD card to.')
	parser.add_argument('--dry-run', action='store_true', help='Whether to do a dry run, where no files are actually changed.')
	args = parser.parse_args()

	# Set up logging
	logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler()])
	logger.setLevel(logging.INFO)

	# Copy the SD card
	workflow = CopyWorkflow(args.base_path, args.jpg_path, args.backup_path, args.extension, args.sd_path, args.dry_run)
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