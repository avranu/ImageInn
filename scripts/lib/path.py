"""

	Metadata:

		File: photo.py
		Project: lib
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
from abc import ABC, abstractmethod
import datetime
from enum import Enum
import errno
import os
import re
import logging
from typing import Any, Dict, Optional, Self, TypedDict
import exifread
import exifread.utils
import exifread.tags.exif
import exifread.classes
from scripts.import_sd.exif import ExifTag
from scripts.import_sd.validator import Validator

logger = logging.getLogger(__name__)

class Path(str, ABC):
	"""
	Allows us to interact with sd cards mounted to the server this code is running on.
	"""
	_path: str

	def __init__(self, path: list[str] | str):
		"""
		Args:
			*path (str): The path, which can be specified in path parts to be joined
		"""
		self.path = path

	@property
	def path(self) -> str:
		"""
		The path to the photo.
		"""
		return self._path

	@path.setter
	def path(self, value: list[str] | str):
		"""
		Set the path
		"""
		if isinstance(value, str):
			# Cast to string to convert Path() to string
			joined_path = str(value)
		else:
			joined_path = os.path.join(*value)

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
	

	def matches(self, file : Path) -> bool:
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
		if not self.exists() or not file.exists():
			return False

		return self.checksum == file.checksum
	
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

	def __str__(self) -> str:
		return self.path

	def __repr__(self) -> str:
		return self.path

class FilePath(Path):
	"""
	Represents a path to a file. 
	
	NOTE: This file does not need to exist yet. os.path.exists() should not be assumed to be true.
	"""
	def validate(self) -> bool:
		# IF the path exists, check that it is a file
		if self.exists() and not os.path.isfile(self.path):
			raise ValueError("The path %s is not a file", self.path)
		
		return super().validate()
	
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
			path = re.sub(suffix + '$', '', self.path)
			return FilePath(path)

		# Split the path into the name and extension
		path_and_name, extension = self.path.rsplit('.', 1)

		# Remove the suffix from the name
		cleaned_path_and_name = re.sub(suffix + '$', '', path_and_name)

		return FilePath(cleaned_path_and_name + '.' + extension)

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
	def path(self, value: list[str] | str):
		"""
		Set the path
		"""
		if isinstance(value, str):
			# Cast to string to convert Path() to string
			joined_path = str(value)
		else:
			joined_path = os.path.join(*value)

		self._path = os.path.normpath(joined_path) + '/'

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
		if self.exists() and not os.path.isdir(self.path):
			raise ValueError("The path %s is not a directory", self.path)
		
		return super().validate()