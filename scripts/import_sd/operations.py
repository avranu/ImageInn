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