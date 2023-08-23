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
from typing import List, Dict, Any, Union, Optional
from scripts.lib.path import FilePath
from scripts.import_sd.providers.base import Provider
from scripts.import_sd.photo import Photo

class AlignmentProvider(Provider, ABC):

	@abstractmethod
	def run(self, photos : list[Photo]) -> list[Photo] | None:
		"""
		Align a single bracket so they can be merged into an HDR.

		On expected errors that can be retried, this method will return None. On unexpected or unrecoverable errors, 
		this method will raise an exception.
		
		Args:
			photo (Photo): The photo to convert.
			tif_path (FilePath): The path to the TIFF file to create.

		Returns:
			Photo: The aligned photos. Returns None if an expected error occurred that we can retry.
		"""
		raise NotImplementedError("AlignmentProvider.run() must be implemented in a subclass.")