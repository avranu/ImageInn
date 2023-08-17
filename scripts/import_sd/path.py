"""
	
	Metadata:
	
		File: photo.py
		Project: import_sd
		Created Date: 11 Aug 2023
		Author: Jess Mann
		Email: jess.a.mann@gmail.com
	
		-----
	
		Last Modified: Sun Aug 13 2023
		Modified By: Jess Mann
	
		-----
	
		Copyright (c) 2023 Jess Mann
"""
from __future__ import annotations
import datetime
from enum import Enum
import errno
import os
import re
import logging
from typing import Any, Dict, Optional, TypedDict
import exifread
import exifread.utils
import exifread.tags.exif
import exifread.classes
from .exif import ExifTag
from .validator import Validator

logger = logging.getLogger(__name__)


class FilePath(str):
	"""
	Allows us to interact with sd cards mounted to the server this code is running on.
	"""
	_path: str

	def __init__(self, path: list[str] | str):
		"""
		Args:
			*path (str): The path to the photo, which can be specified in path parts to be joined
		"""
		if isinstance(path, list):
			self.path = os.path.join(*path)
		else:
			self.path = path

	@property
	def path(self) -> str:
		"""
		The path to the photo.
		"""
		return self._path

	@path.setter
	def path(self, value: str):
		"""
		Set the path
		"""
		self._path = os.path.normpath(value)

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
	def exists(self) -> bool:
		"""
		Checks if the given file exists.

		Returns:
			bool: True if the file exists, False otherwise.

		Examples:
			>>> path = FilePath('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> path.exists
			True
		"""
		return os.path.exists(self.path)

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
		if not self.exists:
			return ''
		
		return Validator.calculate_checksum(self.path)

	def exists(self) -> bool:
		"""
		Checks if the given file exists.

		Returns:
			bool: True if the file exists, False otherwise.

		Examples:
			>>> path = FilePath('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> path.exists()
			True
		"""
		return os.path.exists(self.path)

	def matches(self, file : FilePath) -> bool:
		"""
		Compares the given photo to this photo.

		Args:
			file (FilePath): The photo to compare to.

		Returns:
			bool: True if the photo checksums are equal, False otherwise.

		Examples:
			>>> path = FilePath('/media/pi/SD_CARD/DCIM/100MSDCF/JAM_1234.arw')
			>>> file = FilePath('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.jpg')
			>>> path.matches(file)
			False
		"""
		# Both must exist
		if not self.exists() or not file.exists():
			return False

		return self.checksum == file.checksum

	def __str__(self):
		return self.path
	
	def __repr__(self):
		return self.path