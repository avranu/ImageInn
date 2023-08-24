"""

	Metadata:

		File: enfuse.py
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
import subprocess
import logging

from scripts.lib.path import FilePath, DirPath
from scripts.import_sd.providers.merge.base import HDRProvider
from scripts.import_sd.photo import Photo

logger = logging.getLogger(__name__)

class EnfuseProvider(HDRProvider):
	"""
	Combine photos into an HDR image using enfuse.
	"""
	def next(self, photos : list[Photo], output_path : FilePath) -> Photo | None:
		"""
		Use enfuse to create the HDR image.

		Args:
			photos (list[Photo]): The photos to combine.

		Returns:
			Photo: The HDR image.

		Raises:
			ValueError: If no photos are provided.
			FileNotFoundError: If the HDR image is not created.
			FileFoundError: If self.onconflict is set to "fail" and the HDR image already exists.
		"""
		if not photos or len(photos) < 2:
			raise ValueError(f'Not enough photos provided to create HDR at {output_path}')

		# Create the command
		command = ['enfuse', '-o', output_path.path, '-v']
		for photo in photos:
			command.append(photo.path)

		# Run the command
		try:
			self.subprocess(command)
		except subprocess.CalledProcessError as e:
			logger.error('Failed to create HDR image at %s -> %s', output_path, e)
			return None

		return Photo(output_path)