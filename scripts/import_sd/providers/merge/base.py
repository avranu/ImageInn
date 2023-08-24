"""

	Metadata:

		File: base.py
		Project: imageinn
		Created Date: 23 Aug 2023
		Author: Jess Mann
		Email: jess.a.mann@gmail.com

		-----

		Last Modified: Thu Aug 24 2023
		Modified By: Jess Mann

		-----

		Copyright (c) 2023 Jess Mann
"""
from __future__ import annotations
from abc import ABC
from typing import List, TypeVar
import logging
from scripts.lib.path import FilePath
from scripts.import_sd.providers.base import Provider
from scripts.import_sd.photo import Photo

logger = logging.getLogger(__name__)

class HDRProvider(Provider, ABC):
	"""
	This service provider merges a bracket of photos into an HDR image.
	"""
	def run(self, brackets: list[Photo], output_path : FilePath | None) -> Photo:
		"""
		Merge the images in a bracket into a single HDR.

		Args:
			photos (list[Photo]): The photos to merge

		Returns:
			Photo:
				The HDR Photo.
		"""
		if len(brackets) < 2:
			logger.debug('Insufficient photos to merge.')
			return []

		# Handle just one bracket and return a list of photos
		return self.next(brackets, output_path)