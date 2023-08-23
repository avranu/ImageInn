"""

	Metadata:

		File: sd.py
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

from scripts.import_sd.folder import SDFolder
from scripts.import_sd.validator import Validator

logger = logging.getLogger(__name__)

class SDCard:
	_path : str

	def __init__(self, path: str):
		self.path = path

	@property
	def path(self) -> str:
		return self._path

	@path.setter
	def path(self, value: str):
		# Ensure a trailing slash
		self._path = os.path.join(os.path.normpath(value), '')

	@classmethod
	def get_media_dir(cls) -> str:
		"""
		Get the media directory for the current operating system.

		Returns:
			str: The media directory for the current operating system.

		Raises:
			FileNotFoundError: If the media directory does not exist.

			Examples:
				>>> SDCards.get_media_dir()
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

	@classmethod
	def sd_contains_photos(cls, sd_path: str, raise_errors : bool = True) -> bool:
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
			>>> SDCards.sd_contains_photos('/media/SD_CARD')
			True
		"""
		if not Validator.is_dir(sd_path):
			if raise_errors:
				raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), sd_path)
			return False

		return Validator.is_dir(os.path.join(sd_path, 'DCIM'))

	@classmethod
	def get_list(cls, media_path : Optional[str] = None) -> list[SDFolder]:
		"""
		Get all SD cards mounted to the server this code is running on.

		Returns:
			list[SDFolder]: A list containing each SD card path

		Examples:
			>>> sd_cards = SDCards()
			>>> sd_cards.get_sd_cards()
			[
				SDFolder {
					'path': '/media/pi/SD',
				}
			]

		"""
		# Handle multiple operating systems
		if not media_path:
			media_path = cls.get_media_dir()

		# Ensure the path exists
		if not Validator.is_dir(media_path):
			return []

		sd_cards = []

		# Loop over all directories in the media_path, but not subdirectories
		for dir in os.listdir(media_path):
			sd_directory = SDFolder(os.path.join(media_path, dir))
			sd_cards.append(sd_directory)

		return sd_cards

	def get_info(self) -> SDFolder:
		"""
		Get info about the SD card at this card's path.

		This includes the total size, used space, and free space, number of files, etc.

		Returns:
			SDFolder: An object containing info about the SD card.

		Raises:
			FileNotFoundError: If the SD card does not exist.

		Examples:
			>>> card = SDCards()
			>>> card.get_sd_card('/media/pi/SD')
			SDFolder {
				'path': '/media/pi/SD',
				'total': 32000000000,
				'used': 10000000000,
				'free': 22000000000,
				'num_files': 100,
				'num_dirs': 10
			}
		"""
		return self.get_info_for(self.path)

	@classmethod
	def get_info_for(cls, sd_card_path : Optional[str] = None) -> SDFolder:
		"""
		Get info about the SD card at the given path.

		This includes the total size, used space, and free space, number of files, etc.

		Args:
			sd_card_path (str): The path to the SD card to get info about.

		Returns:
			SDFolder: An object containing info about the SD card.

		Raises:
			FileNotFoundError: If the SD card does not exist.

		Examples:
			>>> SDCards.get_sd_card('/media/pi/SD')
			SDFolder {
				'path': '/media/pi/SD',
				'total': 32000000000,
				'used': 10000000000,
				'free': 22000000000,
				'num_files': 100,
				'num_dirs': 10
			}
		"""
		if not sd_card_path:
			sd_card_path = cls.get_media_dir()

		# Ensure the path exists
		if not Validator.is_dir(sd_card_path):
			raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), sd_card_path)

		# Get the total size of the SD card
		total, used, free = shutil.disk_usage(sd_card_path)

		# Get the number of files and dirs on the SD card
		num_files = 0
		num_dirs = 0
		for _root, dirs, files in os.walk(sd_card_path):
			num_files += len(files)
			num_dirs += len(dirs)

		return SDFolder(
			path = sd_card_path,
			total = total,
			used = used,
			free = free,
			num_files = num_files,
			num_dirs = num_dirs
		)

	def determine_subpath(self, filepath : str) -> str:
		"""
		Takes a file path and turns it into just the subdirectories of the SD card (ignoring the root DCIM folder)

		Args:
			filepath (str): The file path to convert.

		Returns:
			str: The subdirectories of the SD card leading to the given file.

		Examples:
			>>> SDCards.determine_subpath('/media/pi/SD/DCIM/100CANON/IMG_0001.JPG')
			'100CANON'
		"""
		logger.critical('filepath: ' + str(filepath))
		logger.critical('selfpath: ' + str(self.path))
		# Remove "{self.path}/DCIM from the beginning, and {filename} from the end
		prefix = os.path.join(self.path, 'DCIM', '')
		result = re.sub(r'^' + prefix, '', os.path.dirname(filepath))

		# Ensure trailing slash
		return os.path.join(result, '')