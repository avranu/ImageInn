"""
	
	Metadata:
	
		File: darktable.py
		Project: tiff
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
from typing import List, Dict, Any, Union, Optional
import logging
import re
from scripts.lib.path import FilePath
from scripts.import_sd.providers.tiff.base import TiffProvider
from scripts.import_sd.photo import Photo

logger = logging.getLogger(__name__)

class DarktableProvider(TiffProvider):
	command : str = 'darktable-cli'

	def next(self, photo : Photo, tiff_path : FilePath) -> Photo | None:
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
		logger.debug('Creating tiff file %s from %s using darktable-cli', tiff_path, photo.path)
		output, error = self.subprocess([self.command, photo.path, tiff_path.path], check=False)

		# DB still locked from last darktable process
		if re.search(r'the database lock file', error, re.IGNORECASE):
			logger.info('Database lock file detected for Darktable.')
			return None

		return Photo(tiff_path)