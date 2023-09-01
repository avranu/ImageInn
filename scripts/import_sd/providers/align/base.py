"""*****************************************************************************
 *                                                                             *
 * Metadata:                                                                   *
 *                                                                             *
 * 	File: base.py                                                              *
 * 	Project: imageinn                                                          *
 * 	Created: 23 Aug 2023                                                       *
 * 	Author: Jess Mann                                                          *
 * 	Email: jess.a.mann@gmail.com                                               *
 *                                                                             *
 * 	-----                                                                      *
 *                                                                             *
 * 	Last Modified: Fri Sep 01 2023                                             *
 * 	Modified By: Jess Mann                                                     *
 *                                                                             *
 * 	-----                                                                      *
 *                                                                             *
 * 	Copyright (c) 2023 Jess Mann                                               *
 ****************************************************************************"""

from __future__ import annotations
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import List, TypeVar
import logging

from tqdm import tqdm
import concurrent.futures
from scripts.lib.path import FilePath
from scripts.import_sd.providers.base import Provider
from scripts.import_sd.photo import Photo

logger = logging.getLogger(__name__)

# Generic type that can be list[Photo] or Photo. This allows us to enforce the return type of a method matches its parameter
BracketOrPhoto = TypeVar('BracketOrPhoto', List[Photo], Photo)
MAX_THREADS = 4

class AlignmentProvider(Provider, ABC):
	"""
	This service provider Aligns a bracket of photos.
	"""

	def run(self, brackets: list[BracketOrPhoto]) -> list[BracketOrPhoto]:
		"""
		Align the images in each bracket with the other images in the same bracket, using multiple threads.

		Args:
			photos (list[Photo] | list[list[Photo]]): The photos to align.

		Returns:
			list[Photo] | list[list[Photo]]:
				The aligned photos.
				If any of the photos cannot be aligned within a braket, an empty list will be returned for that bracket.
		"""
		if len(brackets) < 1:
			logger.debug('No brackets to align.')
			return []
		
		# Handle just one bracket and return a list of photos
		if isinstance(brackets[0], Photo):
			return self._next_bracket(brackets)
		
		with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
			futures = [executor.submit(self._next_bracket, bracket) for bracket in brackets]
			results = []
			for future in tqdm(concurrent.futures.as_completed(futures), desc="Aligning multiple brackets...", total=len(brackets), ncols=100):
				try:
					aligned_bracket = future.result(timeout=300)
					if aligned_bracket:
						results.append(aligned_bracket)
				except concurrent.futures.TimeoutError:
					logger.error("Timeout while aligning photos.")

			return results
	
	def _next_bracket_list(self, brackets : list[list[Photo]]) -> list[list[Photo]]:
		"""
		Align a list of brackets of photos.

		Args:
			brackets (list[list[Photo]]): The brackets of photos to align.

		Returns:
			list[list[Photo]]: The aligned brackets.
		"""
		# Align each bracket of photos
		aligned_brackets = []
		for bracket in brackets:
			aligned_bracket = self.next(bracket)
			aligned_brackets.append(list(aligned_bracket.values()))

		return aligned_brackets
	
	def _next_bracket(self, bracket : list[Photo]) -> list[Photo]:
		"""
		Align a single bracket of photos.

		Args:
			bracket (list[Photo]): The photos to align.

		Returns:
			list[Photo]: The aligned photos.
		"""
		aligned_bracket = self.next(bracket)
		return list(aligned_bracket.values())

	@abstractmethod
	def next(self, photos: list[Photo]) -> dict[Photo, Photo]:
		"""
		Align a single bracket of photos

		Args:
			photo (list[Photo]): The photos to align.

		Returns:
			dict[Photo, Photo]: A dictionary of the original photos and their aligned counterparts.
		"""
		raise NotImplementedError("AlignmentProvider.next() must be implemented in a subclass.")
