"""

	Metadata:

		File: stack.py
		Project: import_sd
		Created Date: 18 Aug 2023
		Author: Jess Mann
		Email: jess.a.mann@gmail.com

		-----

		Last Modified: Sat Aug 19 2023
		Modified By: Jess Mann

		-----

		Copyright (c) 2023 Jess Mann
"""
from __future__ import annotations
import datetime
from math import fabs as abs
from typing import Dict, Optional, Tuple
import logging
from decimal import Decimal
from scripts.import_sd.photo import Photo

logger = logging.getLogger(__name__)

TIME_DIFF_THRESHOLD = 5

class PhotoStack:
	"""
	Represents a stack of photos.

	Internally, this is represented as a dict.
	"""
	_photos : Dict[str, Photo]
	_bias_gap : Decimal | None = None
	_value_gap : Decimal | None = None

	def __init__(self):
		self._photos = {}

	@property
	def bias_gap(self):
		return self._bias_gap

	@property
	def value_gap(self):
		return self._value_gap

	def get_gap(self) -> tuple[Decimal, Decimal]:
		"""
		Get the gap between the last photo and the current photo.

		Returns:
			tuple[Decimal, Decimal]: The gap between the last photo and the current photo, as a tuple of (bias, exposure).
		"""
		return self._bias_gap, self._value_gap

	def add_photo(self, photo : Photo) -> bool:
		"""
		Add a photo to the stack, if it belongs there.

		Args:
			photo (Photo): The photo to add.

		Returns:
			bool: True if the photo was added, False otherwise.
		"""
		if self.belongs(photo):
			# Calculate a new gap
			self._bias_gap, self._value_gap = self.calculate_gap(photo)
			self._photos[photo.number] = photo
			logger.debug('Added photo %s to stack. Stack size is now %s', photo.number, len(self._photos))
			return True
		return False

	def get_photos(self) -> list[Photo]:
		"""
		Get the photos in the stack.

		Returns:
			list[Photo]: The photos in the stack.
		"""
		return list(self._photos.values())

	def calculate_gap(self, photo: Photo) -> Tuple[Optional[Decimal], Optional[Decimal]]:
		"""
		Calculates the gap between the provided photo and the last photo in the stack.

		Args:
			photo (Photo): The photo to calculate the gap for.

		Returns:
			(Decimal, Decimal): The gap between the photos, as a tuple of (bias, exposure).
		"""
		photos = self.get_photos()
		if len(photos) <= 0:
			return None, None

		bias, exposure = None, None

		last = photos[-1]
		if last.exposure_bias is not None and photo.exposure_bias is not None:
			bias = abs(last.exposure_bias - photo.exposure_bias)

		if last.exposure_value is not None and photo.exposure_value is not None:
			exposure = abs(last.exposure_value - photo.exposure_value)

		return bias, exposure

	def _attribute_matches(self, photo : Photo, comparison : Photo, attribute : str) -> bool:
		attr1 = getattr(photo, attribute)
		attr2 = getattr(comparison, attribute)
		if attr1 != attr2:
			logger.debug(f"Photo {photo.number}:{attribute}. {attr1} does not match {attr2} of photo {comparison.number}")
			return False
		return True


	def belongs(self, photo : Photo) -> bool:
		"""
		Determines if a photo belongs in the current stack

		Args:
			photo (Photo): The photo to check.

		Returns:
			bool: True if the photo matches the gap, False otherwise.
		"""
		# For no photos, the photo is considered matching
		if len(self._photos) <= 0:
			logger.debug("No photos in stack, photo %s matches", photo.number)
			return True

		photos = self.get_photos()
		last = photos[-1]

		if not all([
			self._attribute_matches(photo, last, 'lens'),
			self._attribute_matches(photo, last, 'camera'),
		]):
			return False

		# The exposure_value OR exposure_bias must be different than the current photo (unless they are none)
		if all([photo.exposure_value == last.exposure_value, photo.exposure_bias == last.exposure_bias]) and \
		   any([photo.exposure_value is not None, photo.exposure_bias is not None]):
			logger.debug("Photo %s exposure value and bias matches (B%s/%s, V%s/%s), so not added", photo.number, photo.exposure_bias, photos[-1].exposure_bias, photo.exposure_value, photos[-1].exposure_value)
			return False

		# Photo was taken within 5 seconds of the last photo (after accounting for shutter speed TODO)
		diff : datetime.timedelta = photo.date - last.date
		if diff.total_seconds() > TIME_DIFF_THRESHOLD + photo.ss + last.ss:
			logger.debug("Photo %s date %s does not match %s", photo.number, photo.date, photos[-1].date)
			return False

		if len(self._photos) == 1:
			logger.debug("Photo %s matches %s", photo.number, last.number)
			# If all the above conditions are met, we can add a 2nd photo to a 1 photo stack.
			return True

		current_bias_gap, current_ev_gap = self.get_gap()
		new_bias_gap, new_ev_gap = self.calculate_gap(photo)

		# For bigger stacks, we have a gap to compare to.
		if current_bias_gap != new_bias_gap and current_ev_gap != new_ev_gap:
			logger.debug("Photo %s does not match %s", photo.number, photos[-1].number)
			logger.debug("Bias: %s, %s. Value: %s, %s", current_bias_gap, new_bias_gap, current_ev_gap, new_ev_gap)
			return False

		logger.debug("Photo %s matches %s", photo.number, photos[-1].number)
		return True

	def __len__(self):
		return len(self._photos)

	def __iter__(self):
		return iter(self.get_photos())

	def __getitem__(self, key):
		return self.get_photos()[key]

	def __contains__(self, key):
		return key in self.get_photos()

	def __str__(self):
		return str(self.get_photos())

	def __repr__(self):
		return repr(self.get_photos())

	def __eq__(self, other):
		if isinstance(other, list):
			return self.get_photos() == other
		if isinstance(other, dict):
			return self._photos == other
		if not isinstance(other, PhotoStack):
			return False
		return self._photos == other._photos

	def __ne__(self, other):
		return not self.__eq__(other)

	def __hash__(self):
		return hash(self.get_photos())