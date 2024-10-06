from __future__ import annotations
from abc import ABC
import os
import re
import sys

# Add the root directory of the project to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from typing import Any, Iterable, Iterator
from enum import Enum
from pathlib import Path
from pydantic import BaseModel, Field, PrivateAttr, field_validator
import threading
from scripts import setup_logging

logger = setup_logging()

DEFAULT_PATTERNS = [ re.compile('.*') ]

class FileTemplate(BaseModel, ABC):
    """
    Class to manage the status file data, handle locking, and provide iteration over statuses.
    """
    name : str = Field(default='Generic', description='The name of the file template.')
    patterns : list[re.Pattern] = Field(default_factory=lambda: DEFAULT_PATTERNS.copy())

    @field_validator('patterns', mode="before")
    def validate_patterns(cls, v) -> re.Pattern:
        if isinstance(v, re.Pattern):
            return [v]
        if isinstance(v, str):
            return [re.compile(v)]
        if isinstance(v, Iterable):
            return [re.compile(pattern) for pattern in v]
        raise ValueError("pattern must be a string, a compiled regex pattern, or an iterable of strings/patterns.")

    def match(self, filename : str | Path) -> bool:
        if isinstance(filename, Path):
            filename = filename.name
        return any(pattern.match(filename) for pattern in self.patterns)

    def __str__(self):
        return f'{self.name.capitalize()} File Template'

PixelFiles = FileTemplate(name='Pixel', patterns=[re.compile(r'PXL_\d{8}_.*\.jpg')])