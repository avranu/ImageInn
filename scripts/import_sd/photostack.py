"""
	
	Metadata:
	
		File: stack.py
		Project: import_sd
		Created Date: 18 Aug 2023
		Author: Jess Mann
		Email: jess.a.mann@gmail.com
	
		-----
	
		Last Modified: Fri Aug 18 2023
		Modified By: Jess Mann
	
		-----
	
		Copyright (c) 2023 Jess Mann
"""
from __future__ import annotations
from math import fabs as abs
from typing import Dict
from scripts.import_sd.photo import Photo

class PhotoStack:
	"""
	Represents a stack of photos.

	Internally, this is represented as a dict. 
	"""
	_photos : Dict[str, Photo]
	_bias_gap : float | None = None
	_value_gap : float | None = None

	def __init__(self):
		self._photos = {}

	@property
	def bias_gap(self):
		return self._bias_gap
	
	@property
	def value_gap(self):
		return self._value_gap
	
	def get_gap(self) -> tuple[float, float]:
		"""
		Get the gap between the last photo and the current photo.

		Returns:
			tuple[float, float]: The gap between the last photo and the current photo, as a tuple of (bias, exposure).
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
			self._photos[photo.number] = photo
			return True
		return False

	def get_photos(self) -> list[Photo]:
		"""
		Get the photos in the stack.

		Returns:
			list[Photo]: The photos in the stack.
		"""
		return self._photos.values()

	def calculate_gap(self, photo : Photo) -> tuple[float, float]:
		"""
		Calculates the gap between the provided photo and the last photo in the stack.

		Args:
			photo (Photo): The photo to calculate the gap for.

		Returns:
			(float, float): The gap between the photos, as a tuple of (bias, exposure).
		"""
		if len(self._photos) <= 0:
			return None, None
		
		bias, exposure = None, None
		
		if self._photos[-1].exposure_bias is not None and photo.exposure_bias is not None:
			bias = abs(self._photos[-1].exposure_bias - photo.exposure_bias)

		if self._photos[-1].exposure_value is not None and photo.exposure_value is not None:
			exposure = abs(self._photos[-1].exposure_value - photo.exposure_value)

		return bias, exposure

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
			return True
		
		current_bias, current_value = self.get_gap()
		new_bias, new_value = self.calculate_gap(photo)

		# Match attributes, such as camera model, lens, etc
		if photo.lens != self._photos[-1].lens:
			return False
		if photo.camera != self._photos[-1].camera:
			return False
		
		# Photo was taken within 1 second of the last photo (after accounting for shutter speed TODO)
		if photo.date - self._photos[-1].date > 1 + photo.ss + self._photos[-1].ss:
			return False
		
		# The photo.exposure_value must be different than the current photo
		if photo.exposure_value is not None and photo.exposure_value == self._photos[-1].exposure_value:
			return False
		if photo.exposure_bias is not None and photo.exposure_bias == self._photos[-1].exposure_bias:
			return False

		if len(self._photos) == 1:
			# If all the above conditions are met, we can add a 2nd photo to a 1 photo stack.
			return True

		# For bigger stacks, we have a gap to compare to.
		if current_bias == new_bias and current_value == new_value:
			return True
		
		return False
	
	def __len__(self):
		return len(self._photos)
	
	def __iter__(self):
		return iter(self._photos.values())
	
	def __getitem__(self, key):
		return self._photos[key]
	
	def __setitem__(self, key, value):
		self._photos[key] = value

	def __delitem__(self, key):
		del self._photos[key]

	def __contains__(self, key):
		return key in self._photos
	
	def __str__(self):
		return str(self._photos)
	
	def __repr__(self):
		return repr(self._photos)
	
	def __eq__(self, other):
		if not isinstance(other, PhotoStack):
			return False
		return self._photos == other._photos
	
	def __ne__(self, other):
		return not self.__eq__(other)
	
	def __hash__(self):
		return hash(self._photos)