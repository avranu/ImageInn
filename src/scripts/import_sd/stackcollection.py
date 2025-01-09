"""

	Metadata:

		File: stackcollection.py
		Project: imageinn
		Created Date: 18 Aug 2023
		Author: Jess Mann
		Email: jess.a.mann@gmail.com

		-----

		Last Modified: Wed Aug 23 2023
		Modified By: Jess Mann

		-----

		Copyright (c) 2023 Jess Mann
"""
from __future__ import annotations
import logging
from scripts.import_sd.photo import Photo
from scripts.import_sd.photostack import PhotoStack

logger = logging.getLogger(__name__)


class StackCollection:
	"""
	Represents a collection of stacks.
	"""

	def __init__(self):
		self.stacks = []
		self.photos = PhotoStack()

	def append(self, stack: PhotoStack):
		"""
		Add a stack to the collection.

		Args:
			stack (PhotoStack): The stack to add.
		"""
		self.stacks.append(stack)
		logger.debug(f'Added a stack: Now there are {len(self.stacks)}')

	def finish_stack(self) -> bool:
		"""
		Finishes the current stack and starts a new one.

		If the current stack has more than 2 photos, it is saved to the collection. Otherwise, it is discarded.

		Returns:
			bool: True if the previous stack was saved, False otherwise.
		"""
		logger.debug('Finishing stack')
		if len(self.photos) > 2:
			self.append(self.photos)
			self.photos = PhotoStack()
			logger.debug('Saved previous stack and started New Stack')
			return True

		logger.debug('Started New Stack without saving previous stack: Photos in previous stack were %d', len(self.photos))
		self.photos = PhotoStack()
		return False

	def add_photo(self, photo: Photo) -> None:
		"""
		Add a photo to the current stack.

		Args:
			photo (Photo): The photo to add.
		"""
		logger.debug(f'Adding a photo: {photo.number} to stack of size {len(self.photos)}')
		result = self.photos.add_photo(photo)

		if result:
			logger.debug(f'Photo was added to stack: Stack size is now {len(self.photos)}')
			return

		self.finish_stack()
		self.photos.add_photo(photo)

	def add_photos(self, photos: list[Photo]) -> None:
		"""
		Add a complete list of photos to the current stack.

		NOTE: This calls finishStack() at the end, which will discard any remaining photos that do not form a complete stack.
		Therefore, this should not be called piecewise, but rather with a complete list of photos.

		Args:
			photos (list[Photo]): The photos to add.
		"""
		for photo in photos:
			self.add_photo(photo)
		self.finish_stack()

	def get_stacks(self) -> list[PhotoStack]:
		"""
		Adds the current set to the finished stacks (if it is full) and returns them.

		NOTE: This does not actually call finishStack(), which would modify the list of "finished stacks".
		It is only intended to show the current state of this object.

		Returns:
			list[PhotoStack]: The stacks.
		"""
		if len(self.photos) > 2:
			return self.stacks + [self.photos]
		return self.stacks

	def __len__(self):
		return len(self.stacks)
