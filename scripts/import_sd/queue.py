from __future__ import annotations
import os
from typing import Optional
from datetime import datetime
from scripts.import_sd.photo import Photo
import logging

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
	_mismatched: dict[Photo, Photo]
	_checksums: dict[Photo, str]

	def __init__(self):
		self._queue = {}
		self._skipped = []
		self._mismatched = {}
		self._checksums = {}
	
	def append(self, destination: str, photo: Photo) -> int:
		"""
		Adds a photo to the queue.

		Args:
			destination (str): The destination directory.
			photo (Photo): The photo to be copied.

		Returns:
			int: The number of photos in the queue for the destination directory.
		"""
		if destination not in self._queue:
			self._queue[destination] = []
		self._queue[destination].append(photo)

		return len(self._queue[destination])
	
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

	def flag(self, photo: Photo, existing: Photo) -> int:
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
	
	def save_checksum(self, photo: Photo, checksum: str) -> None:
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
	
	def get_mismatched(self) -> dict[Photo, Photo]:
		"""
		Returns the mismatched list.

		Returns:
			dict[Photo, Photo]: The mismatched list.
		"""
		return self._mismatched
	
	def get_checksums(self) -> dict[Photo, str]:
		"""
		Returns the checksums.

		Returns:
			dict[Photo, str]: The checksums.
		"""
		return self._checksums
	
	def get_checksum(self, photo: Photo) -> str | None:
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
				count = len(self._mismatched.keys())
			case "checksums":
				count = len(self._checksums.keys())
			case "all":
				count = len(self._skipped) + len(self._mismatched.keys()) + len(self._checksums.keys()) + self.count("queue")
			case _:
				count = 0
				for destination in self._queue:
					count += len(self._queue[destination])

		return count
	
	def write(self, destination_folder : str, output_path : Optional[str] = None) -> str:
		"""
		Save a portion of the queue to a file (for the given destination), one photo path per line.
		
		This is used for tools like teracopy.
		
		Args:
			desintation_folder (str): The path to the destination directory. Only photos destined to be copied to that directory will be saved.
			output_path (str, optional): The path to save the queue to. Defaults to a file in the current directory named "copy_queue_{date}.txt"
		
		Returns:
			str: The path the queue was saved to.
		"""
		if output_path is None:
			output_path = f"copy_queue_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"
		
		# If the file already exists, log a warning
		if os.path.exists(output_path):
			# If the output_path doesn't end in txt, refuse to overwrite it
			if not output_path.endswith(".txt"):
				raise FileExistsError(f"Queue file already exists: {output_path}. Refusing to overwrite because it isn't a text file.")
			
			logger.warning(f"Queue file already exists: {output_path}. Overwriting...")

		with open(output_path, "w") as file:
			for photo in self._queue[destination_folder]:
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