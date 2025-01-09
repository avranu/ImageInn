"""*****************************************************************************
 *                                                                             *
 * Metadata:                                                                   *
 *                                                                             *
 * 	File: hugin.py                                                             *
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
import subprocess
import logging
from tqdm import tqdm

from scripts.lib.path import FilePath, DirPath
from scripts.import_sd.providers.align.base import AlignmentProvider
from scripts.import_sd.photo import Photo
from scripts.import_sd.photostack import PhotoStack

logger = logging.getLogger(__name__)


class HuginProvider(AlignmentProvider):
	"""
	Align images using Hugin's align_image_stack command.
	"""
	aligned_path: DirPath

	def __init__(self, aligned_path: DirPath) -> None:
		super().__init__()
		self.aligned_path = aligned_path

	def next(self, photos: list[Photo] | PhotoStack, allowed_errors: int = 2, minimum_size: int = 2) -> dict[Photo, Photo]:
		"""
		Align a single bracket of photos.

		If alignment fails, remove the beginning or end photo and try again, up until the minimum bracket size is reached.

		Args:
			photo (list[Photo]): The photos to align.

		Returns:
			dict[Photo, Photo]: A dictionary of the original photos and their aligned counterparts.
		"""
		if isinstance(photos, PhotoStack):
			photos = photos.get_photos()

		# Ensure aligned_path exists, and create it if not
		self.aligned_path.ensure_exists()
		logger.debug('Aligned path is %s -> exists: %s', self.aligned_path, self.aligned_path.exists())

		# Attempt to align the photos
		working_set = photos
		results = {}
		for i in range(min(1, allowed_errors)):
			results = self.attempt_alignment(working_set, max(0, allowed_errors - i), minimum_size)
			if results:
				break

			# We reached the minimum size, so stop trying
			if len(working_set) <= minimum_size:
				break

			# Remove the last photo and try again
			working_set = working_set[:-1]

		# If alignment failed, return an empty list
		if not results:
			logger.error('Could not align photos %s', photos)
			return {}

		# Add exif data to the aligned photos
		aligned_photos = {}
		for photo, aligned in tqdm(results.items(), desc="Copying exif data to aligned images...", ncols=100):
			# Copy EXIF data using ExifTool
			logger.debug('Copying exif data from %s to %s', photo, aligned)
			self.subprocess(['exiftool', '-TagsFromFile', photo.path, '-all', aligned.path])

			# Create a new file named {photo.filename}_aligned.{ext}
			final_path = photo.change_extension('tif', '_aligned')
			final_path = aligned.rename(final_path.filename)
			final_path = Photo(final_path)

			# Add the photo to the list
			aligned_photos[photo] = final_path

		return aligned_photos

	def attempt_alignment(self, photos: list[Photo], allowed_errors: int = 2, minimum_size: int = 2) -> dict[Photo, Photo] | None:
		"""
		Attempt to align a single bracket of photos without retrying.

		Args:
			photos (list[Photo]): The photos to align.

		Returns:
			dict[Photo, Photo]: A dictionary of the original photos and their aligned counterparts.
		"""
		aligned_photos: list[Photo] = []
		expected_photos: dict[Photo, FilePath] = {}
		idx: int
		photo: Photo
		for idx, photo in enumerate(photos):
			expected_photos[photo] = self.aligned_path.file(f'aligned_tmp_{idx:04}.tif')

		try:
			# TODO conflicts
			# Log named after first photo
			log_path = f'hugin_{photos[0].filename}.out'
			# Create the command
			command = ['align_image_stack', '-a', self.aligned_path.file('aligned_tmp_').path, '-m', '-v', '-C', '-c', '25', '-p', log_path, '-t', '1']
			for photo in photos:
				command.append(photo.path)
			_output, _error = self.subprocess(command)

			# Ensure the right number of photos were created
			missing: dict[int, FilePath] = {}
			for idx, (photo, output_photo) in enumerate(expected_photos.items()):
				if not output_photo.exists():
					missing[idx] = output_photo

			# Allow images at the beginning and end of the bracket to be missing
			if len(missing) > 0:
				found = len(photos) - len(missing)

				if len(missing) > allowed_errors:
					logger.error('Too many missing files after alignment. Found %d photos. Missing %d photos: %s', found, len(missing), missing)
					logger.error('OUTPUT: %s', _output)
					logger.error('ERROR: %s', _error)
					return None

				if found < minimum_size:
					logger.error('Could not find at least %d files after alignment. Found %d photos. Missing %d photos: %s', minimum_size, found, len(missing), missing)
					logger.error('OUTPUT: %s', _output)
					logger.error('ERROR: %s', _error)
					return None
				"""
				Check if the missing photos are at the beginning or end of the bracket.
				For example:
					it is okay if photo 1 and 2 are missing, but 3-6 are found.
					it is okay if photo 1 and 6 are missing, but 2-5 are found.
					It is NOT okay if photo 1 and 3 are missing, but 2 is found and 4 is found.
				"""
				# Get the missing photo indexes
				missing_idxs = list(missing.keys())
				# Get the found photo indexes
				photo_idxs = [i for i in range(len(photos)) if i not in missing_idxs]
				# Check that photo_idxs are sequential
				if photo_idxs != list(range(photo_idxs[0], photo_idxs[-1] + 1)):
					logger.error('Aligned photos are missing from the middle of the bracket. Found %d photos. Missing %d photos: %s', minimum_size, found, len(missing), missing)
					logger.error('OUTPUT: %s', _output)
					logger.error('ERROR: %s', _error)
					return {}

				# Remove the missing photos from the expected list
				for idx in missing:
					photo = photos[idx]
					del expected_photos[photo]

		except subprocess.CalledProcessError as e:
			logger.error('Could not align images -> %s', e)
			return {}

		return aligned_photos
