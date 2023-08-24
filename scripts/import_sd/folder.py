"""

	Metadata:

		File: folder.py
		Project: imageinn
		Created Date: 11 Aug 2023
		Author: Jess Mann
		Email: jess.a.mann@gmail.com

		-----

		Last Modified: Wed Aug 23 2023
		Modified By: Jess Mann

		-----

		Copyright (c) 2023 Jess Mann
"""
from __future__ import annotations
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class SDFolder:
	"""
	Represents a directory on an SD card.
	"""
	path: str
	total: int | None
	used: int | None
	free: int | None
	num_files: int | None
	num_dirs: int | None

	def __init__(self, path: str, total: Optional[int] = None, used: Optional[int] = None, free: Optional[int] = None, num_files: Optional[int] = None, num_dirs: Optional[int] = None):
		self.path = path
		self.total = total
		self.used = used
		self.free = free
		self.num_files = num_files
		self.num_dirs = num_dirs