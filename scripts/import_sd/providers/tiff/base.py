"""

	Metadata:

		File: base.py
		Project: imageinn
		Created Date: 23 Aug 2023
		Author: Jess Mann
		Email: jess.a.mann@gmail.com

		-----

		Last Modified: Wed Aug 23 2023
		Modified By: Jess Mann

		-----

		Copyright (c) 2023 Jess Mann
"""
from __future__ import annotations
from abc import ABC, abstractmethod
import os
import logging
import time
from scripts.lib.path import FilePath
from scripts.import_sd.config import MAX_RETRIES
from scripts.import_sd.providers.base import Provider
from scripts.import_sd.photo import Photo

logger = logging.getLogger(__name__)

class TiffProvider(Provider, ABC):
	"""
	Convert raw photos to TIFF files.
	"""
	def run(self, files : dict[Photo, FilePath]) -> dict[Photo, Photo]:
		"""
		Convert a list of raw photos to TIFF files.

		Args:
			files (dict[Photo, FilePath]): A dictionary of raw photos and the paths to the TIFF files to create.

		Returns:
			dict[Photo, Photo]: A dictionary of raw photos and the converted TIFF files.
		"""
		results = {}

		for photo, tiff_path in files.items():
			for i in range(MAX_RETRIES):
				# Add _tmp to the end of the file name until we get a successful conversion
				tmp_path = tiff_path.append_suffix('_tmp')

				tiff = self.next(photo, tmp_path)

				if not tiff:
					# Wait a few seconds, then try again.
					# Sleep a little longer each time, up to a maximum time.
					sleep_time = min(60, 5 * (i+1))
					logger.info('Waiting %d seconds and trying again. (%d/%d)', sleep_time, i+1, MAX_RETRIES)
					time.sleep(sleep_time)
					continue

				# Ensure the TIFF file exists
				if not tiff.exists():
					logger.error('Tiff file %s does not exist after conversion.', tiff.path)
					continue

				# Copy EXIF data using ExifTool
				logger.debug('Copying exif data from %s to %s', photo.path, tiff.path)
				self.subprocess(['exiftool', '-TagsFromFile', photo.path, '-all', tiff.path])

				# Rename the file to remove the _tmp suffix
				self.rename(tiff, tiff_path)
				results[photo] = Photo(tiff_path)

				# Done! No need to loop more
				break

			if not tiff:
				logger.error('Maximum retries exceeded for %s', photo.path)
				continue

		return results

	@abstractmethod
	def next(self, photo: Photo, tiff_path: FilePath) -> Photo | None:
		"""
		Convert a single raw photo to a TIFF file using darktable.

		On expected errors that can be retried, this method will return None. On unexpected or unrecoverable errors,
		this method will raise an exception.

		Args:
			photo (Photo): The photo to convert.
			tif_path (FilePath): The path to the TIFF file to create.

		Returns:
			Photo: The converted photo.	Returns None if an expected error occurred that we can retry.
		"""
		raise NotImplementedError("TiffProvider.run() must be implemented in a subclass.")

	def rename(self, path: FilePath, destination: FilePath) -> bool:
		"""
		Rename a file, if it doesn't already exist.

		Args:
			path (FilePath): The source path.
			destination (FilePath): The destination path.

		Returns:
			bool: True if the file was renamed, False if it already exists.
		"""
		if not destination.exists():
			os.rename(path.path, destination.path)
			return True
		return False
