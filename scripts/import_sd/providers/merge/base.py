"""
	
	Metadata:
	
		File: base.py
		Project: merge
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
from typing import List, Dict, Any, Union, Optional
from scripts.lib.path import FilePath
from scripts.import_sd.providers.base import Provider
from scripts.import_sd.photo import Photo

class HDRProvider(Provider, ABC):

	@abstractmethod
	def run(self, photos: list[Photo]) -> Photo | None:
		"""
		Merge a single bracket into an HDR image.

		On expected errors that can be retried, this method will return None. On unexpected or unrecoverable errors, 
		this method will raise an exception.
		
		Args:
			photos (list[Photo]): The photos to merge.

		Returns:
			Photo: The converted photo.	Returns None if an expected error occurred that we can retry.
		"""
		raise NotImplementedError("HDRProvider.run() must be implemented in a subclass.")