"""

	Metadata:

		File: validator.py
		Project: imageinn
		Created Date: 11 Aug 2023
		Author: Jess Mann
		Email: jess.a.mann@gmail.com

		-----

		Last Modified: Wed Aug 23 2023
		Modified By: Jess Mann

		-----

		Copyright (c) 2023 Jess Mann
"""
from __future__ import annotations
import errno
import hashlib
import os
import logging

logger = logging.getLogger(__name__)


class Validator:
	"""
	Provides methods for validating files and directories.

	Probably depreecated.
	"""

	@classmethod
	def is_dir(cls, path: str) -> bool:
		"""
		Check if the given path exists and is a directory.
		"""
		return os.path.isdir(path)

	@classmethod
	def is_file(cls, path: str) -> bool:
		"""
		Check if the given path exists and is a file.
		"""
		return os.path.isfile(path)

	@classmethod
	def is_writeable(cls, path: str) -> bool:
		"""
		Check if the given path is writable.
		"""
		return os.access(path, os.W_OK)

	@classmethod
	def ensure_dir(cls, path: str) -> bool:
		"""
		Ensure that the given path exists and is a directory. If it does not exist, create a new directory.

		Args:
			path (str): The path to ensure is a directory.

		Returns:
			bool: True if the path exists and is a directory, False otherwise.
		"""
		if not os.path.exists(path):
			logger.info(f'Creating directory: {path}')
			os.makedirs(path, exist_ok=True)

		return cls.is_dir(path)

	@classmethod
	def calculate_checksums(cls, base_path: str) -> dict[str, str]:
		"""
		Calculate checksums for all files under the given base_path.

		Args:
			base_path (str): The base path to calculate checksums for.

		Returns:
			dict[str, str]: A dictionary of file paths to checksums.

		Raises:
			FileNotFoundError: If the base_path does not exist.

		Examples:
			>>> SDCards.calculate_checksums('/media/SD_CARD')
			{
				'/media/SD_CARD/DCIM/100CANON/IMG_0001.JPG': 'a1b2c3d4e5f6...',
				'/media/SD_CARD/DCIM/100CANON/IMG_0002.JPG': 'dbb2s3dbe5d2...',
			}
		"""
		if not cls.is_dir(base_path):
			raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), base_path)

		checksums = {}
		for root, _dirs, files in os.walk(base_path):
			for file in files:
				file_path = os.path.join(root, file)
				if cls.is_file(file_path) and os.access(file_path, os.R_OK):
					checksums[file_path] = cls.calculate_checksum(file_path)
				else:
					logger.error(f'File not accessible: {file_path}')

		return checksums

	@classmethod
	def calculate_checksum(cls, file_path: str) -> str:
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
		if not cls.is_file(file_path) or not os.access(file_path, os.R_OK):
			logger.error(f'File not accessible: {file_path}')
			raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), file_path)

		# We use sha256 because rsync uses MD5, and we want to do both
		hasher = hashlib.sha256()

		with open(file_path, 'rb') as afile:
			buf = afile.read()
			hasher.update(buf)

		result = hasher.hexdigest()

		if not result:
			logger.error('Failed to calculate checksum for file: {file_path}')
			raise ValueError(f'Failed to calculate checksum for file: {file_path}')

		return result

	@classmethod
	def compare_checksums(cls, source_file: str, destination_file: str) -> bool:
		"""
		Compare the checksums of two files.

		Args:
			source_file (str): The path to the source file to compare.
			destination_file (str): The path to the destination file to compare.

		Returns:
			bool: True if the checksums match, False otherwise.
		"""
		source_checksum = cls.calculate_checksum(source_file)
		destination_checksum = cls.calculate_checksum(destination_file)
		return source_checksum == destination_checksum

	@classmethod
	def validate_checksums(cls, checksums_before: dict[str, str], destination_path: str) -> bool:
		"""
		Validate checksums after rsync and report any mismatches.

		Args:
			checksums_before (dict[str, str]): A dictionary of file paths to checksums before rsync.
			destination_path (str): The path to the destination directory to validate checksums for.

		Returns:
			bool: True if the checksums were valid, False otherwise.
		"""
		checksums_after = cls.calculate_checksums(destination_path)
		mismatches = 0

		with open(os.path.join(destination_path, 'checksum.txt'), 'w', encoding='utf-8') as f:
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

	@classmethod
	def validate_checksum_list(cls, checksums_before: dict[str, str], files: dict[str, str]) -> bool:
		"""
		Vaidate checksums after copying files and report any mismatches.

		Args:
			checksums_before (dict[str, str]): A dictionary of source file paths to checksums before copying.
			files (dict[str, str]): A dictionary of source file paths to destination file paths that were copied.

		Returns:
			bool: True if the checksums were valid, False otherwise.
		"""
		mismatches = 0

		# Loop over each file that was copied
		for source_file_path, destination_file_path in files.items():
			# Get the checksum before copying
			checksum_before = checksums_before.get(source_file_path)
			if checksum_before is None or checksum_before != cls.calculate_checksum(destination_file_path):
				logger.critical(f'Checksum not found, or mismatched, for {source_file_path}')
				mismatches += 1
				continue

			logger.debug(f'Checksum match for {source_file_path}')

		if mismatches:
			logger.critical(f'Checksum list mismatch for {mismatches} files')
			return False

		return True
