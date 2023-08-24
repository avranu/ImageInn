"""

	Metadata:

		File: photo.py
		Project: imageinn
		Created Date: 11 Aug 2023
		Author: Jess Mann
		Email: jess.a.mann@gmail.com

		-----

		Last Modified: Thu Aug 24 2023
		Modified By: Jess Mann

		-----

		Copyright (c) 2023 Jess Mann
"""
from __future__ import annotations
from abc import ABC, abstractmethod
import errno
import os
import re
import logging
from typing import Optional, Self
from scripts.import_sd.validator import Validator

logger = logging.getLogger(__name__)

class Path(str, ABC):
	"""
	Allows us to interact with sd cards mounted to the server this code is running on.
	"""
	_path: str

	def __init__(self, absolute_path: str | list[str]):
		"""
		Args:
			*path (str): The path, which can be specified in path parts to be joined
		"""
		if not absolute_path:
			raise ValueError("The path cannot be empty")

		self.path = absolute_path

	@property
	def path(self) -> str:
		"""
		The path to the photo.
		"""
		return self._path

	@path.setter
	def path(self, value: str | list[str]):
		"""
		Set the path
		"""
		if isinstance(value, (Path, str)):
			# Cast to string to convert Path objects to string
			joined_path = str(value)
		elif isinstance(value, list):
			joined_path = os.path.join(*[str(part) for part in value])
		else:
			raise ValueError("The path must be a string or a list of strings")

		# Eliminate double slashes
		self._path = os.path.normpath(joined_path)

		self.validate()

	@property
	def name(self) -> str:
		"""
		The name of the file or directory.
		"""
		return os.path.basename(self.path)

	@property
	def directory(self) -> DirPath:
		"""
		The directory of the file.
		"""
		return DirPath(os.path.dirname(self.path))

	@abstractmethod
	def validate(self) -> bool:
		"""
		Used by sublasses to ensure that the type of path is valid.

		Returns:
			bool: True if the path is valid, False otherwise.
		"""
		raise NotImplementedError("Validation must be implemented by child classes")

	@property
	@abstractmethod
	def checksum(self) -> str:
		raise NotImplementedError("Checksumming must be implemented by child classes")

	def exists(self) -> bool:
		"""
		Checks if the given file exists.

		Returns:
			bool: True if the file exists, False otherwise.

		Examples:
			>>> path = Path('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> path.exists()
			True
		"""
		return os.path.exists(self.path)


	def matches(self, filepath : Path) -> bool:
		"""
		Compares the given photo to this photo.

		Args:
			file (Path): The photo to compare to.

		Returns:
			bool: True if the photo checksums are equal, False otherwise.

		Examples:
			>>> path = Path('/media/pi/SD_CARD/DCIM/100MSDCF/JAM_1234.arw')
			>>> file = Path('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.jpg')
			>>> path.matches(file)
			False
		"""
		# Both must exist
		if not self.exists() or not filepath.exists():
			return False

		return self.checksum == filepath.checksum

	def append_suffix(self, suffix: str) -> Self:
		"""
		Appends the given suffix from the path.

		NOTE: This does not change this object. It creates a new Path object to return.

		Args:
			suffix (str): The suffix to append.

		Returns:
			Path: The new path with the suffix appended.

		Examples:
			>>> path = Path('/media/pi/SD_CARD/DCIM/100MSDCF/')
			>>> path.append_suffix('_1')
			Path('/media/pi/SD_CARD/DCIM/100MSDCF_1/')
		"""
		# return a new object that is the same type as this object, even if we are dealing with a child
		return self.__class__(self.path + suffix)

	def remove_suffix(self, suffix: str) -> Self:
		"""
		Removes the given suffix from the path.

		NOTE: This does not change this object. It creates a new Path object to return.

		Args:
			suffix (str): The suffix to remove.

		Returns:
			Path: The new path with the suffix removed.

		Examples:
			>>> path = Path('/media/pi/SD_CARD/DCIM/100MSDCF_1/')
			>>> path.remove_suffix('_1')
			Path('/media/pi/SD_CARD/DCIM/100MSDCF/')
		"""
		return self.__class__(re.sub(suffix + '$', '', self.path))

	def is_file(self) -> bool:
		"""
		Checks if the given file is a file.

		Returns:
			bool: True if the file is a file, False otherwise.

		Examples:
			>>> photo = FilePath('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.jpg')
			>>> photo.is_file()
			True
		"""
		return os.path.isfile(self.path)

	def is_dir(self) -> bool:
		"""
		Checks if the given file is a directory.

		Returns:
			bool: True if the file is a directory, False otherwise.

		Examples:
			>>> photo = FilePath('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.jpg')
			>>> photo.is_dir()
			False
		"""
		return os.path.isdir(self.path)

	def __str__(self) -> str:
		return self.path

	def __repr__(self) -> str:
		return self.path

class FilePath(Path):
	"""
	Represents a path to a file.

	NOTE: This file does not need to exist yet. os.path.exists() should not be assumed to be true.
	"""
	@property
	def filename(self):
		"""
		The filename of the file. Same as (self.name)
		"""
		return self.name

	@property
	def extension(self) -> str:
		"""
		Get the file extension from the given file.

		Returns:
			str: The file extension.

		Examples:
			>>> path = FilePath('/media/pi/SD_CARD/DCIM/100MSDCF/JAM_1234.arw')
			>>> path.extension
			'arw'
		"""
		# If there is no decimal, then there is no extension
		if '.' not in self.path:
			return ""

		return self.path.lower().split('.')[-1]

	@property
	def filename_stem(self) -> str:
		"""
		Get the file name without the extension.

		Returns:
			str: The file name without the extension.

		Examples:
			>>> path = FilePath('/media/pi/SD_CARD/DCIM/100MSDCF/JAM_1234.arw')
			>>> path.filename_stem
			'JAM_1234'
		"""
		return os.path.splitext(self.filename)[0]

	@property
	def checksum(self) -> str:
		"""
		Get the checksum of this file.

		Returns:
			str: The checksum, or an empty string if the file does not exist.

		Examples:
			>>> path = FilePath('/media/pi/SD_CARD/DCIM/100MSDCF/JAM_1234.arw')
			>>> path.checksum
			'8f3d1d8a'
		"""
		if not self.exists():
			return ''

		return Validator.calculate_checksum(self.path)

	def append_suffix(self, suffix: str) -> FilePath:
		"""
		Appends the given suffix to the filename.

		NOTE: This does not change this object. It creates a new FilePath object to return.

		Args:
			suffix (str): The suffix to append.

		Returns:
			FilePath: The new path with the suffix appended.

		Examples:
			>>> path = FilePath('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> path.append_suffix('_1')
			FilePath('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234_1.arw')
		"""
		# If there is no decimal, then there is no extension
		if '.' not in self.path:
			return FilePath(self.path + suffix)

		# Split the path into the name and extension
		path_and_name, extension = self.path.rsplit('.', 1)

		return FilePath(path_and_name + suffix + '.' + extension)

	def remove_suffix(self, suffix: str) -> FilePath:
		"""
		Removes the given suffix from the filename.

		NOTE: This does not change this object. It creates a new FilePath object to return.

		Args:
			suffix (str): The suffix to remove.

		Returns:
			FilePath: The new path with the suffix removed.

		Examples:
			>>> path = FilePath('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234_1.arw')
			>>> path.remove_suffix('_1')
			FilePath('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
		"""
		# If there is no decimal, then there is no extension. Remove this suffix ONLY from the end of the path.
		if '.' not in self.path:
			cleaned_path = re.sub(suffix + '$', '', self.path)
			return FilePath(cleaned_path)

		# Split the path into the name and extension
		path_and_name, extension = self.path.rsplit('.', 1)

		# Remove the suffix from the name
		cleaned_path_and_name = re.sub(suffix + '$', '', path_and_name)

		return FilePath(cleaned_path_and_name + '.' + extension)

	def change_extension(self, extension: str, suffix : Optional[str] = None) -> FilePath:
		"""
		Changes the extension of the file.

		NOTE: This does not change this object. It creates a new FilePath object to return.

		Args:
			extension (str): The new extension.
			suffix (str, optional): The suffix to append to the filename before the extension. Defaults to None.

		Returns:
			FilePath: The new path with the extension changed.

		Examples:
			>>> path = FilePath('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> path.change_extension('jpg')
			FilePath('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.jpg')
			>>> path.change_extension('jpg', '_copy')
			FilePath('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234_copy.jpg')
		"""
		name_suffix = extension if suffix is None else suffix + '.' + extension

		# If there is no decimal, then there is no extension
		if '.' not in self.path:
			path_and_name = self.path
		else:
			# Split the path into the name and extension
			path_and_name, _old_extension = self.path.rsplit('.', 1)

		return FilePath(path_and_name + name_suffix)

	def validate(self) -> bool:
		# IF the path exists, check that it is a file
		if self.exists() and not self.is_file():
			raise ValueError(f"The path {self.path} is not a file")

		return True

	def delete(self, require_success : bool = False) -> bool:
		"""
		Delete the file.

		Returns:
			bool: True if the file was deleted, False otherwise.
		"""
		# If the file doesnt exist, return True
		if not self.exists():
			return True

		try:
			os.remove(self.path)
			return True
		except Exception as e:
			logger.error("Could not delete file %s -> %s", self.path, e)
			if require_success:
				raise e from e

		if require_success and self.exists():
			raise FileExistsError(f'Could not delete file at {self.path}')

		return False

	def rename(self, value : str) -> Self:
		"""
		Rename the file.

		Args:
			value (str): The new name of the file.

		Returns:
			FilePath: The new path to the file.
		"""
		# If the file doesnt exist, return True
		if not self.exists():
			raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), self.path)

		absolute_path = os.path.join(self.directory.path, value)
		
		try:
			os.rename(self.path, absolute_path)
		except Exception as e:
			logger.error("Could not rename file %s -> %s: %s", self.path, absolute_path, e)
			raise e from e

		return self.__class__(absolute_path)

class DirPath(Path):
	"""
	Represents a path to a directory.

	NOTE: This directory does not need to exist yet. os.path.exists() should not be assumed to be true.
	"""
	@property
	def path(self) -> str:
		"""
		The path to the photo.
		"""
		return self._path

	@path.setter
	def path(self, value: str | list[str]):
		"""
		Set the path
		"""
		if not value:
			raise ValueError("The path cannot be empty")

		if isinstance(value, (Path, str)):
			# Cast to string to convert Path objects to string
			joined_path = str(value)
		elif isinstance(value, list):
			joined_path = os.path.join(*[str(part) for part in value])
		else:
			raise ValueError("The path must be a string or a list of strings")

		# Ensure no double-slashes, and exactly 1 final slash
		self._path = os.path.join(os.path.normpath(joined_path), '')

		self.validate()

	@property
	def name(self) -> str:
		"""
		The name of the directory.
		"""
		return os.path.basename(self.path)

	@property
	def checksum(self) -> str:
		"""
		We have not yet implemented directory checksumming.
		"""
		raise NotImplementedError("A directory does not have a checksum")

	def validate(self) -> bool:
		"""
		Ensures this path to a file is valid.

		Returns:
			bool: True if the path is valid, False otherwise.
		"""
		# IF it exists, ensure it is a directory
		if self.exists() and not self.is_dir():
			raise ValueError(f"The path {self.path} is not a directory")

		return True
	
	def ensure_exists(self) -> None:
		"""
		Ensure that this directory exists. Create it if it does not.
		"""
		if not self.exists():
			os.makedirs(self.path, exist_ok=True)

	def get_contents(self, sort : bool = True) -> list[Path]:
		"""
		Get the contents of this directory.

		Args:
			sort (bool, optional): Whether or not to sort the contents. Defaults to True.

		Returns:
			list[Path]: The contents of this directory.
		"""
		contents = []

		if self.exists():
			for filename in os.listdir(self.path):
				childpath = os.path.join(self.path, filename)

				if os.path.isfile(childpath):
					contents.append(FilePath(childpath))
				elif os.path.isdir(childpath):
					contents.append(DirPath(childpath))
				else:
					logger.warning("Unknown file type for %s", childpath)

			if sort:
				contents.sort()

		return contents

	def get_files(self, sort : bool = True) -> list[FilePath]:
		"""
		Get the files in this directory.

		Args:
			sort (bool, optional): Whether or not to sort the files. Defaults to True.

		Returns:
			list[FilePath]: The files in this directory.
		"""
		return [file for file in self.get_contents(sort) if isinstance(file, FilePath)]

	def get_subdirectories(self, sort : bool = True) -> list[DirPath]:
		"""
		Get the subdirectories of this directory.

		Args:
			sort (bool, optional): Whether or not to sort the subdirectories. Defaults to True.

		Returns:
			list[DirPath]: The subdirectories of this directory.
		"""
		return [dir for dir in self.get_contents(sort) if isinstance(dir, DirPath)]

	def child(self, dir_name : str) -> DirPath:
		"""
		Get the child directory of this directory.

		Args:
			dir_name (str): The name of the child directory.

		Returns:
			DirPath: The child directory of this directory.
		"""
		return DirPath([self.path, dir_name])

	def file(self, filename : str) -> FilePath:
		"""
		Get a path to a file within this directory. NOTE: The file does not need to exist.

		Args:
			filename (str): The name of the file.

		Returns:
			FilePath: The path to the file.
		"""
		return FilePath([self.path, filename])

if __name__ == "__main__":
	# Testing code, can be deleted
	path = DirPath(['/mnt/Photography/Recent/Lightroom/2023/2023-08-05/hdr/', 'aligned'])
	file = FilePath([path, 'IMG_1234.jpg'])
	print(file)