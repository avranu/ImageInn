"""

	Metadata:

		File: rawpy.py
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
import rawpy
import imageio
from scripts.lib.path import FilePath
from scripts.import_sd.providers.tiff.base import TiffProvider
from scripts.import_sd.photo import Photo

class RawpyProvider(TiffProvider):
	"""
	Convert raw photos to TIFF files using rawpy.
	"""
	def next(self, photo: Photo, tiff_path: FilePath) -> Photo | None:
		"""
		Convert a single raw photo to a TIFF file using rawpy.

		On expected errors that can be retried, this method will return None. On unexpected or unrecoverable errors,
		this method will raise an exception.

		Args:
			photo (Photo): The photo to convert.
			tif_path (FilePath): The path to the TIFF file to create.

		Returns:
			Photo: The converted photo. Returns None if an expected error occurred that we can retry.
		"""
		with rawpy.imread(photo) as raw:
			rgb = raw.postprocess()
		imageio.imsave(tiff_path, rgb)

		return Photo(tiff_path)
