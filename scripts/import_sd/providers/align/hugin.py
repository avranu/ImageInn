"""
	
	Metadata:
	
		File: hugin.py
		Project: align
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
import os
import subprocess
from typing import List, Dict, Any, Union, Optional
import logging
import re
import tqdm

from scripts.lib.path import FilePath, DirPath
from scripts.import_sd.providers.align.base import AlignmentProvider
from scripts.import_sd.photo import Photo

logger = logging.getLogger(__name__)

class HuginProvider(AlignmentProvider):
	aligned_path : DirPath

	def __init__(self, aligned_path : DirPath) -> None:
		super().__init__()
		self.aligned_path = aligned_path

	def next(self, photos: list[Photo]) -> list[Photo]:
		"""
		Align a single bracket of photos

		Args:
			photo (list[Photo]): The photos to align.

		Returns:
			list[Photo]:
				The aligned photos.
				If ANY of the photos cannot be aligned, an empty list will be returned.
		"""
		aligned_photos : list[Photo] = []
		
		try:
			# TODO conflicts
			# Create the command
			command = ['align_image_stack', '-a', os.path.join(self.aligned_path, 'aligned_tmp_'), '-m', '-v', '-C', '-c', '100', '-g', '5', '-p', 'hugin.out', '-t', '0.3']
			for photo in photos:
				command.append(photo.path)
			output, error = self.subprocess(command)

			# Create the photos
			idx : int
			photo : Photo
			for idx, photo in tqdm(enumerate(photos), desc="Aligning Images...", ncols=100):
				# Create the path.
				output_path = FilePath([self.aligned_path, f'aligned_tmp_{idx:04}.tif'])

				# Copy EXIF data using ExifTool
				logger.debug('Copying exif data from %s to %s', photo.path, output_path)
				self.subprocess(['exiftool', '-TagsFromFile', photo.path, '-all', output_path])

				# Create a new file named {photo.filename}_aligned.{ext}
				filename = re.sub(rf'\.{photo.extension}$', '_aligned.tif', photo.filename)
				aligned_path = output_path.rename(filename)

				# Add the photo to the list
				aligned_photo = Photo(aligned_path)
				aligned_photos.append(aligned_photo)

		except subprocess.CalledProcessError as e:
			logger.error('Could not align images -> %s', e)
			# Clean up aligned photos we created
			for aligned_photo in aligned_photos:
				aligned_photo.delete()
			return []
		
		return aligned_photos