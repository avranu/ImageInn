"""
	
	Metadata:
	
		File: base.py
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
from abc import ABC, abstractmethod
from typing import List, Dict, Any, TypeVar, Union, Optional
import logging
from scripts.lib.path import FilePath
from scripts.import_sd.providers.base import Provider
from scripts.import_sd.photo import Photo
from scripts.import_sd.photostack import PhotoStack

logger = logging.getLogger(__name__)

# Generic type that can be list[Photo] or Photo. This allows us to enforce the return type of a method matches its parameter
BracketOrPhoto = TypeVar('BracketOrPhoto', List[Photo], Photo)

class AlignmentProvider(Provider, ABC):

	def run(self, brackets: list[BracketOrPhoto]) -> list[BracketOrPhoto]:
		"""
		Align the images in each bracket with the other images in the same bracket.

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
			return self.next(brackets)

		# Handle a group of brackets and return a list of lists of photos
		results = []
		for bracket in brackets:
			aligned_bracket = self.next(bracket)
			results.append(aligned_bracket)

		return results

	@abstractmethod
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
		raise NotImplementedError("AlignmentProvider.next() must be implemented in a subclass.")
