"""
	
	Metadata:
	
		File: queue.py
		Project: import_sd
		Created Date: 12 Aug 2023
		Author: Jess Mann
		Email: jess.a.mann@gmail.com
	
		-----
	
		Last Modified: Sun Aug 13 2023
		Modified By: Jess Mann
	
		-----
	
		Copyright (c) 2023 Jess Mann
"""
from __future__ import annotations
import os
from typing import Optional
from datetime import datetime
import logging

from .path import FilePath
from .photo import Photo
from .validator import Validator

logger = logging.getLogger(__name__)

class Queue:
	"""
	Represents a queue of files to be copied.

	Attributes:
		queue (dict[str, list[Photo]]): 
			The queue of files to be copied. 
			The key is the destination directory, and the value is a list of photos to be copied to that directory.
		skipped (list[Photo]): 
			The list of photos on the sd card that will be skipped. 
			They are already present in all destination directories with the same contents.
		mismatched (dict[Photo, Photo]):
			The list of photos that exist in the destination directory with different checksums.
			They will be copied and renamed, so both versions are preserved.
		checksums (dict[Photo, str]):
			The list of checksums for every photo in the sd card (regardless of whether it will be copied)
	"""
	_queue: dict[str, list[Photo]]
	_skipped: list[Photo]
	_mismatched: dict[Photo, FilePath]
	_checksums: dict[FilePath, str]

	def __init__(self):
		self._queue = {}
		self._skipped = []
		self._mismatched = {}
		self._checksums = {}
	
	def append(self, photo: Photo, destination: FilePath | str) -> bool:
		"""
		Adds a photo to the queue, if possible. 

		If the photo already exists at the destination, checksums are calculated. 
		If checksums match, the photo is skipped. If checksums do not match, the photo is flagged as mismatched and copied with a new name.

		Args:
			photo (Photo): The photo to be copied.
			destination (FilePath): The destination path (including filename) it will be copied to.

		Raises:
			ValueError: If the photo and destination have different extensions.

		Returns:
			bool: True if the photo was added to the queue, False if it was not.
		"""
		if not isinstance(destination, FilePath):
			destination = FilePath(destination)

		# Check that photo and destination have the same extension, otherwise throw an error
		if photo.extension != destination.extension:
			raise ValueError(f"Photo and destination have different extensions: {photo.extension} and {destination.extension}")
		
		# Calculate checksums for both files
		checksums = self.calculate_checksums([photo, destination])

		# Check if something already exists at the destination path
		if destination.exists():
			# If checksums are the same, do not append to queue
			if checksums[photo] == checksums[destination]:
				self.skip(photo)
				return False
			# If checksums are different, flag as mismatched and append to queue
			self.flag(photo, destination)
			logger.warning(f"Checksums do not match for {photo.path} and {destination.path}")

		# Get the destination directory
		destination_dir = os.path.dirname(destination.path)

		# Append it to the queue
		self._queue.setdefault(destination_dir, []).append(photo)

		return True
	
	def append_parts(self, photo : Photo, destination_parts : list[str] | str) -> bool:
		"""
		Adds a photo to the queue, if possible, where the destination path is constructed from a list of path parts.

		Args:
			photo (Photo): The photo to be copied.
			destination_parts (list[str] | str): The parts of the path to the destination photo (or a single complete path).

		Returns:
			bool: True if the photo was added to the queue, False if it was not.
		"""
		# Join the parts into a single path
		destination = FilePath(destination_parts)
		return self.append(photo, destination)
	
	def skip(self, photo: Photo) -> int:
		"""
		Adds a photo to the skipped list.

		Args:
			photo (Photo): The photo to be skipped.

		Returns:
			int: The number of photos in the skipped list.
		"""
		self._skipped.append(photo)
		return len(self._skipped)

	def flag(self, photo: Photo, existing: FilePath) -> int:
		"""
		Adds a photo to the mismatched list.

		Args:
			photo (Photo): The photo to be copied.
			existing (Photo): The photo that already exists in the destination directory.

		Returns:
			int: The number of photos in the mismatched list.
		"""
		self._mismatched[photo] = existing
		return len(self._mismatched)
	
	def calculate_checksum(self, photo : FilePath) -> str:
		"""
		Calculates a checksum for the photo and saves it to the checksums list.
		
		Args:
			photo (Photo): The photo to be copied.
			
		Returns:
			str: The checksum of the photo.
		"""
		checksum = photo.checksum
		self.append_checksum(photo, checksum)
		return checksum
	
	def calculate_checksums(self, photos : list[FilePath]) -> dict[str, str]:
		"""
		Calculates checksums for all photos and saves them to the checksums list.
		
		Args:
			photos (list[Photo]): The photos to be copied.

		Returns:
			dict[str, str]: The checksums of the photos.
		"""
		checksums = {}
		for photo in photos:
			try:
				result = self.calculate_checksum(photo)
				checksums[photo] = result
			except FileNotFoundError:
				logger.debug(f"File not found, cannot calculate checksum: {photo.path}")

		return checksums
	
	def append_checksum(self, photo: FilePath, checksum: str) -> None:
		"""
		Saves the checksum for a photo.

		Args:
			photo (Photo): The photo to be copied.
			checksum (str): The checksum of the photo.
		"""
		self._checksums[photo] = checksum

	def get(self, destination : str) -> list[Photo]:
		"""
		Returns the queue.

		Args:
			destination (str): The destination directory. 

		Returns:
			dict[str, list[Photo]]: The queue.
		"""
		if destination not in self._queue:
			return []
		return self._queue[destination]
	
	def get_queue(self) -> dict[str, list[Photo]]:
		"""
		Returns the queue.

		Returns:
			dict[str, list[Photo]]: The queue.
		"""
		return self._queue
	
	def get_skipped(self) -> list[Photo]:
		"""
		Returns the skipped list.

		Returns:
			list[Photo]: The skipped list.
		"""
		return self._skipped
	
	def get_mismatched(self) -> dict[Photo, FilePath]:
		"""
		Returns the mismatched list.

		Returns:
			dict[Photo, Photo]: The mismatched list.
		"""
		return self._mismatched
	
	def get_checksums(self) -> dict[FilePath, str]:
		"""
		Returns the checksums.

		Returns:
			dict[Photo, str]: The checksums.
		"""
		return self._checksums
	
	def get_checksum(self, photo: FilePath) -> str | None:
		"""
		Returns the checksum for a photo.

		Args:
			photo (Photo): The photo.

		Returns:
			str: The checksum for the photo.
		"""
		if photo not in self._checksums:
			return None
		return self._checksums[photo]
	
	def count(self, category : str = "queued") -> int:
		"""
		Returns the number of photos in the queue.

		Args:
			category (str, optional): The category of photos to count ("skipped", "mismatched", "queue", "checksums", "all"). Defaults to "queue".

		Returns:
			int: The number of photos in the queue.
		"""
		match category.lower():
			case "skipped":
				count = len(self._skipped)
			case "mismatched":
				count = len(self._mismatched)
			case "checksums":
				count = len(self._checksums)
			case "all":
				count = len(self._skipped) + len(self._mismatched) + len(self._checksums) + self.count("queue")
			case _:
				return sum(len(photos) for photos in self._queue.values())

		return count
	
	def write(self, destination_folder: str, output_path: Optional[str] = None) -> str:
		"""
		Save a portion of the queue to a file (for the given destination), one photo path per line.

		This is used for tools like teracopy.

		Args:
			desintation_folder (str): The path to the destination directory.
			output_path (str, optional): The path to save the queue to.
		
		Returns:
			str: The path the queue was saved to.
		"""
		if output_path is None:
			output_path = f"copy_queue_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"
		
		# If the file already exists, log a warning
		if os.path.exists(output_path) and not output_path.lower().endswith(".txt"):
				raise FileExistsError(f"Queue file already exists: {output_path}. Refusing to overwrite because it isn't a text file.")

		photos_to_copy = self._queue.get(destination_folder, [])
		with open(output_path, "w") as file:
			for photo in photos_to_copy:
				file.write(f"{photo.path}\n")
		
		return output_path
	
	def to_dict(self) -> dict:
		"""
		Returns a dictionary representation of the queue.

		Returns:
			dict: A dictionary representation of the queue.
		"""
		return {
			"queue": self._queue,
			"skipped": self._skipped,
			"mismatched": self._mismatched,
			"checksums": self._checksums
		}
	
	def __len__(self) -> int:
		"""
		Returns the number of photos in the queue.

		Returns:
			int: The number of photos in the queue.
		"""
		return self.count()
	
	def __str__(self) -> str:
		"""
		Returns a string representation of the queue.

		Returns:
			str: A string representation of the queue.
		"""
		return f"Queue: {self.count()} photos"