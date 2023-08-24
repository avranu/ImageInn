"""

	Metadata:

		File: operations.py
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
from enum import Enum
import logging

logger = logging.getLogger(__name__)

# An enum of copy operations (rsync, teracopy, etc)
class CopyOperation(str, Enum):
	"""
	An enum of copy operations (rsync, teracopy, etc)
	"""
	RSYNC = 'rsync'
	TERACOPY = 'teracopy'