"""

	Metadata:

		File: workflow.py
		Project: import_sd
		Created Date: 11 Aug 2023
		Author: Jess Mann
		Email: jess.a.mann@gmail.com

		-----

		Last Modified: Tue Aug 22 2023
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
import logging, logging.config
import subprocess
import sys
from typing import Any, Dict, Optional, TypedDict
import exifread, exifread.utils, exifread.tags.exif, exifread.classes

from scripts.import_sd.config import MAX_RETRIES
from scripts.import_sd.validator import Validator
from scripts.import_sd.path import FilePath
from scripts.import_sd.photo import Photo, FakePhoto
from scripts.import_sd.sd import SDCard

logger = logging.getLogger(__name__)

class Actions(Enum):
	"""
	Represents the different actions that can be performed as a workflow
	"""
	IMPORT = 'import'
	HDR = 'hdr'
	PANO = 'pano'
	RENAME = 'rename'
	STACK = 'stack'

class Workflow:
	"""
	Allows us to interact with sd cards mounted to the server this code is running on.
	"""
	_base_path: FilePath
	_jpg_path: FilePath
	_backup_path: FilePath
	_sd_card : SDCard = None
	_bucket_path : FilePath | None = None
	raw_extension : str
	dry_run : bool = False
	action : str

	@property
	def base_path(self) -> FilePath:
		"""
		The path to the network location to copy raw files from the SD Card to.
		"""
		return self._base_path

	@base_path.setter
	def base_path(self, base_path: str | list[str] | FilePath) -> None:
		"""
		Set the path to the network location to copy raw files from the SD Card to.

		Args:
			base_path (str): The path to the network location to copy raw files from the SD Card to.
		"""
		if isinstance(base_path, (str, list)):
			base_path = FilePath(base_path)

		if not Validator.is_dir(base_path):
			raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), base_path)
		
		self._base_path = self._normalize_path(base_path)

	def get_photos(self, directory : Optional[str] = None) -> list[Photo]:
		"""
		Get a list of photos from a given directory

		Args:
			directory (Optional[str], optional): The directory to get photos from. Defaults to None.

		Returns:
			list[Photo]: A list of photos from the directory
		"""
		if directory is None:
			directory = self.base_path

		# Get all files in the directory (but not subdirectories), and sort them by their filename
		files = os.listdir(directory)
		files.sort()

		photos = []
		for file in files:
			if self.raw_extension and file.lower().endswith(self.raw_extension):
				photos.append(Photo([directory, file]))

		return photos

	def _normalize_path(self, path: str) -> FilePath:
		"""
		Normalize a path for the system, and ensure that it ends with a trailing slash (which is important for rsync)

		Args:
			path (str): The path to normalize.

		Returns:
			str: The normalized path.
		"""
		return FilePath([os.path.normpath(path), ''])

	def _check_photo(self, photo: Photo, destinations: list[Photo]) -> tuple[bool, list[Photo]]:
		"""
		Checks if a photo exists in a list of destinations, and if so, whether its checksum matches.

		Args:
			photo (Photo): The photo to check.
			destinations (list[Photo]): The list of destinations to check.

		Returns:
			tuple[bool, list[Photo]]:
				(already_exists, mismatched_destinations)
				A tuple of whether the photo exists in all destinations, and a list of destinations where its checksum does not match.

		"""
		exists = True
		mismatched = []
		for path in destinations:
			if not path.exists():
				exists = False
				continue
			if not photo.matches(path):
				mismatched.append(path)

		return exists, mismatched


	def generate_name(self, photo : Photo | str, short : bool = False, properties : Optional[dict[str, Any]] = None) -> str:
		"""
		Generate a name for the photo we are copying.

		The name is in the format:
		{YYYYmmdd}_{camera model}_{filename number suffix}_{exposure-bias}_{brightness value}_{ISO speed}_{shutter speed}_{Lens}.{extension}

		The filename number suffix comes from the last 4 digits of the filename (e.g. JAM_1234.jpg -> 1234).

		Args:
			photo (Photo | str):
				The photo to generate a name for. If a str, it is assumed to be the file path.
			short (bool, optional):
				Whether to generate a short name. Defaults to False.
			properties (Optional[dict[str, Any]], optional):
				The properties of the photo. Defaults to None, where the properties are determined from the photo.

		Returns:
			str: The generated name.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/JAM_1234.arw')
			>>> generate_name(photo)
			'20230805_a7r4-1234_-2 7_10EV_8.27B_800ISO_SAMYANG AF 12mm F2.0.arw'
			>>> generate_name('/media/pi/SD_CARD/DCIM/100MSDCF/JAM_1234.arw', short=True)
			'1234_-2 7_10EV_8.27B.arw'
			>>> generate_name('/media/pi/SD_CARD/DCIM/100MSDCF/JAM_1234.arw', properties={'number': 5678})
			'20230805_a7r4-5678_-2 7_10EV_8.27B_800ISO_SAMYANG AF 12mm F2.0.arw'
			"""
		if isinstance(photo, str):
			# If properties['number'] is set, pass it to the constructor
			if properties is not None and 'number' in properties:
				photo = Photo(photo)
			else:
				photo = Photo(photo)

		# Merge properties from the param and the photo, prioritizing the param
		props = {
			'num': properties.get('number', photo.number),
			'eb': properties.get('exposure_bias', photo.exposure_bias),
			'ev': properties.get('exposure_value', photo.exposure_value),
			'b': properties.get('brightness', photo.brightness),
			'iso': properties.get('iso', photo.iso),
			'ss': properties.get('ss', photo.ss),
			'lens': properties.get('lens', photo.lens),
			'ext': properties.get('extension', photo.extension),
			'date': properties.get('date', photo.date),
			'camera': properties.get('camera', photo.camera)
		}

		if short is True:
			# Generate the name
			#name = f'{props['number']}_{photo.exposure_bias}EB_{photo.exposure_value}EV_{photo.brightness}B_{photo.iso}ISO_{photo.ss}SS'
			name = f'{props["num"]}_{props["eb"]}EB_{props["ev"]}EV_{props["b"]}B_{props["iso"]}ISO_{props["ss"]}SS'
		else:
			if not props['date']:
				date = '00000000'
			else:
				date = f"{props['date']:%Y%m%d}"
			# Generate the name
			#name = f'{date}_{photo.camera}_{photo.number}_{photo.exposure_bias}EB_{photo.exposure_value}EV_{photo.brightness}B_{photo.iso}ISO_{photo.ss}SS_{photo.lens}'
			name = f'{date}_{props["camera"]}_{props["num"]}_{props["eb"]}EB_{props["ev"]}EV_{props["b"]}B_{props["iso"]}ISO_{props["ss"]}SS_{props["lens"]}'

		# Replace whitespace in the name with a dash
		name = name.replace(' ', '-')

		return f"{name}.{props['ext']}"

	def generate_path(self, photo : Photo | str) -> FilePath:
		"""
		Figure out an appropriate path to copy the file, given its creation date.

		The path is in the format:
		{network_path}/{YYYY}/{YYYY-mm-dd}/{filename}

		NOTE: generate_name is used to generate the filename, so the resulting file will be renamed.

		Args:
			photo (Photo | str): The photo to generate a path for. If a str, it is assumed to be the file path.

		Raises:
			ValueError: If the path is too long to fit in the filesystem.

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

		#		MAX   Path				 Extension		   ---.  Date (2023/2023-01-05/)
		buffer = 254 - len(self.base_path) - len(photo.extension) - 4 - 16
		if buffer < 1:
			# No room for even a truncated filename
			raise ValueError(f'Path is too long: {self.base_path}')
		elif buffer < len(filename):
			# First, try re-generating a name without the camera model or lens, and a shortened date.
			filename = self.generate_name(photo, short=True)

			if buffer < len(filename):
				# No dice! Truncate the filename
				filename = f'{filename[:buffer]}---.{photo.extension}'

		# Generate the path again
		if photo.date is None:
			year = '0000'
			date = '0000-00-00'
		else:
			year = f'{photo.date:%Y}'
			date = f'{photo.date:%Y-%m-%d}'
		path = f'{self.base_path}/{year}/{date}/{filename}'

		return FilePath(path)

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

	def mkdir(self, path : FilePath, exist_ok : bool = True) -> None:
		"""
		Create a directory, if it doesn't already exist.

		Args:
			path (FilePath): The path to create.
		"""
		if not os.path.exists(path):
			if self.dry_run:
				logger.info('Would create directory "%s"', path)
			else:
				os.makedirs(path, exist_ok=exist_ok)

	def rename(self, path : FilePath, destination : FilePath) -> None:
		"""
		Rename a file, if it doesn't already exist.

		Args:
			path (FilePath): The source path.
			destination (FilePath): The destination path.
		"""
		if not destination.exists():
			if self.dry_run:
				logger.info('Would rename "%s" to "%s"', path, destination)
			else:
				os.rename(path, destination)

	def subprocess(self, command : str | list[str], cwd : FilePath = None, check : bool = True, timeout : Optional[float] = None) -> tuple[str, str]:
		"""
		Run a subprocess, printing the command and output to the user.

		Args:
			command (str):
				The command to run.
			cwd (FilePath, optional):
				The working directory to run the command in. Defaults to None.
			check (bool, optional):
				Whether to raise an exception if the command fails. Defaults to True.

		Returns:
			tuple[str, str]: The output of the command, and the error str from the command.

		Raises:
			subprocess.CalledProcessError:
				If the command fails, and check is True.
				Otherwise, the error is logged, and the error message is returned when an exception is encountered.
		"""
		if self.dry_run:
			logger.info('Would run command "%s"', command)
			return 'Dry run. Command skipped.', ''

		try:
			# Run the command
			output = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=check, timeout=timeout)
		except subprocess.CalledProcessError as e:
			logger.error('Command failed: %s', command)
			logger.error('Error message: %s', e.stderr)
			logger.error('Output: %s', e.stdout)

			if check:
				raise e from e
			else:
				return getattr(output, 'stdout', ''), e.stderr

		if output.stdout:
			logger.debug(output.stdout)

		if output.stderr:
			logger.debug(output.stderr)

			if output.returncode != 0:
				logger.error('Command failed: %s', command)
				logger.error('Error message: %s', output.stderr)
				logger.error('Output: %s', output.stdout)
				if check:
					raise subprocess.CalledProcessError(output.returncode, command, output.stderr)

		# Return the output
		return output.stdout, output.stderr

	def delete(self, path : FilePath) -> None:
		"""
		Delete a file.

		Args:
			path (FilePath): The path to delete.
		"""
		if self.dry_run:
			logger.info('Would delete "%s"', path)
		else:
			try:
				os.remove(path)
			except FileNotFoundError:
				logger.debug('File "%s" does not exist, so was not deleted.', path)

	def rmdir(self, path : FilePath) -> bool:
		"""
		Delete a directory.

		Args:
			path (FilePath): The path to delete.

		Returns:
			bool: Whether the directory was deleted.

		Raises:
			OSError: If the directory is not empty.
		"""
		# If it doesn't exist, we're good to go
		if not os.path.exists(path):
			return True

		if os.listdir(path):
			logger.info('Directory "%s" is not empty, so was not deleted.', path)
			return False

		if self.dry_run:
			logger.info('Would delete directory "%s"', path)
		else:
			os.rmdir(path)

		return True

	def get_photo(self, path : str) -> Photo:
		"""
		Turn a path into a Photo object.

		If dry_run, this will return a FakePhoto object instead.

		Args:
			path (str): The path to the photo.

		Returns:
			Photo: The photo.
		"""
		if self.dry_run:
			return FakePhoto(path)
		return Photo(path)

def main():
	"""
	Entry point for the application.
	"""
	# Logging config, which will eventually be migrated to a separate configfile
	config = {
		'version': 1,
		'formatters': {
			'basic': {'format': '%(asctime)s - %(levelname)s - %(message)s'}
		},
		'handlers': {
			'console': {'class': 'logging.StreamHandler', 'formatter': 'basic', 'level': logging.INFO},
			'file': {'class': 'logging.FileHandler', 'formatter': 'basic', 'level': logging.DEBUG, 'filename': 'log.txt'}
		},
		'root': {
			'handlers': ['console', 'file'],
			'level': logging.DEBUG,
		},
	}

	# Set up logging
	logging.config.dictConfig(config)
	logger.setLevel(logging.DEBUG)

	# Parse command line arguments
	parser = argparse.ArgumentParser(description='Begin a workflow for importing or processing photos.')
	# First argument is required
	parser.add_argument('action', type=str, help='The action to perform. Valid options are "import", "rename", and "stack".')
	# Allow arbitrary arguments after, which the next script may parse
	parser.add_argument('args', nargs=argparse.REMAINDER, help='Arguments to pass to the next script.')
	# If --help is specified with an action, ignore it. The next script will handle the help.
	if '--help' in sys.argv and sys.argv.index('--help') > 1:
		# Get the position of --help in sys.argv
		help_index = sys.argv.index('--help')
		args = parser.parse_args(sys.argv[1:help_index])
	else:
		args = parser.parse_args()

	match args.action.lower():
		case Actions.IMPORT.value:
			from scripts.import_sd.workflows.copy import main as subscript
		case Actions.RENAME.value:
			from scripts.import_sd.workflows.rename import main as subscript
		case Actions.STACK.value:
			from scripts.import_sd.workflows.stack import main as subscript
		case Actions.HDR.value:
			from scripts.import_sd.workflows.hdr import main as subscript
		case Actions.PANO.value:
			from scripts.import_sd.workflows.pano import main as subscript
		case _:
			raise ValueError(f'Invalid action: {args.action}')

	# Run the next script
	subscript()

if __name__ == '__main__':
	# Keep terminal open until script finishes and user presses enter
	try:
		main()
	except KeyboardInterrupt:
		pass

	input('Press Enter to exit...')