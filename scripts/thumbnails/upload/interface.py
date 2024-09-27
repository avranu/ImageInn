#!/usr/bin/env python3
"""
Upload files to Immich.

This script is used because the immich app isn't reliable for uploading files, and I don't want to
manually upload files via the web interface (and leave that interface open in Chrome).

Instead, this cli script can be run as a periodic cronjob.

See also the organize.py script for organizing files into directories prior to this script being 
executed.

This script is referenced in bash_aliases (but not in the github copy of it).

Version 1.0
Date: 2024-09-26
Status: Working

Example:
    >>> python upload.py
    >>> python upload.py -d /mnt/i/Phone
    # bash_aliases defines `upload` to run this script for the current dir
    >>> upload
"""
from __future__ import annotations
import os
import sys
import time

# Add the root directory of the project to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

import subprocess
from pathlib import Path
from pydantic import BaseModel, Field, PrivateAttr, field_validator
from typing import Iterable, List
import threading
from abc import ABC, abstractmethod
from scripts import setup_logging
from scripts.lib.file_manager import FileManager
from scripts.thumbnails.upload.meta import ALLOWED_EXTENSIONS, STATUS_FILE_NAME
from scripts.thumbnails.upload.exceptions import AuthenticationError
from scripts.thumbnails.upload.status import Status

logger = setup_logging()

ALLOWED_EXTENSIONS = [
    # Images
    'jpg', 'jpeg', 'png', 'gif', 'tiff', 'webp',
    # RAW
    'arw', 'dng', 'nef',
    # Videos
    'mp4', 'mov', 'm4a', 'wmv', 'avi', 'mkv', 'flv', 'webm',
    # Audio
    'mp3', 'wav', 'm4a', 'ogg',
    # Photo editing
    'psd', 'svg',
]

STATUS_FILE_NAME = 'upload_status.txt'

class ImmichInterface(FileManager, ABC):
    """
    Abstract class for uploading files to Immich. Subclasses include ImmichProgressiveUploader and ImmichDirectUploader.
    """
    url: str
    api_key: str
    ignore_extensions: list[str] = Field(default_factory=list)
    ignore_paths: list[str] = Field(default_factory=list)
    large_file_size: int = 1024 * 1024 * 100  # 100 MB
    backup_directories : list[Path] = Field(default_factory=list)

    _authenticated: bool = PrivateAttr(default=False)

    @field_validator('directory', mode="before")
    def validate_directory(cls, v):
        if not v:
            raise ValueError("directory must be set.")
        
        # Allow str and list[str]
        v = Path(v)
        if not v.exists():
            logger.error(f"Directory {v} does not exist.")
            raise FileNotFoundError(f"Directory {v} does not exist.")
        return v

    @field_validator('ignore_extensions', mode="before")
    def validate_ignore_extensions(cls, v):
        if not v:
            return []
        if isinstance(v, str):
            return [v]
        if isinstance(v, list):
            return v
        raise ValueError("Invalid ignore_extensions value.")

    @field_validator('ignore_paths', mode="before")
    def validate_ignore_paths(cls, v):
        if not v:
            return []
        if isinstance(v, (str, Path)):
            return [str(v)]
        if isinstance(v, Iterable):
            return [str(path) for path in v]
        raise ValueError("Invalid ignore_paths value.")

    @field_validator('backup_directories', mode="before")
    def validate_backup_directories(cls, v):
        if not v:
            return []
        if isinstance(v, (str, Path)):
            return [Path(v)]
        if isinstance(v, Iterable):
            return [Path(path) for path in v]
        raise ValueError("Invalid backup_directories value.")

    def authenticate(self):
        """
        Authenticate with Immich using the API key.

        Raises:
            AuthenticationError: If authentication fails
        """
        if self._authenticated:
            return
        try:
            subprocess.run(["immich", "login-key", self.url, self.api_key], check=True)
            self._authenticated = True
            logger.info("Authenticated successfully.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Authentication failed: {e}")
            raise AuthenticationError("Authentication failed.") from e

    @abstractmethod
    def upload(self, directory: Path | None = None, recursive: bool = True):
        """
        Abstract method to upload files.

        Args:
            directory (Path): The directory to upload.
            recursive (bool): Whether to upload recursively

        Raises:
            NotImplementedError: If the method is not implemented in a subclass
        """
        pass

    # Shared methods
    def should_ignore_file(self, file: Path, status: Status | None = None) -> bool:
        """
        Check if a file should be ignored based on the extension, size, and status.

        Args:
            file (Path): The file to check.
            status (dict[str, str]): A dictionary of file status.
            status_lock (threading.Lock): A lock to synchronize access to the status dictionary.

        Returns:
            bool: True if the file should be ignored, False otherwise
        """
        if not file.is_file():
            return True

        suffix = file.suffix.lstrip('.').lower()

        # Ignore non-image extensions
        if suffix not in ALLOWED_EXTENSIONS:
            logger.debug("Ignoring non-media file due to extension: %s", file)
            return True

        if suffix in self.ignore_extensions:
            logger.debug("Ignoring file due to extension per user request: %s", file)
            return True

        # Ignore hidden
        if file.name.startswith('.'):
            logger.debug("Ignoring hidden file: %s", file)
            return True

        if str(file) in self.ignore_paths:
            logger.debug("Ignoring file due to path: %s", file)
            return True

        if file.stat().st_size > self.large_file_size:
            logger.debug(f"File {file} is larger than {self.large_file_size} bytes and will be skipped.")
            return True

        if status:
            if status.was_successful(file):
                logger.debug(f"Skipping already uploaded file {file}")
                return True

        return False

    def create_backup_subdirs(self, file: Path) -> list[Path]:
        """
        Create subdirectories in each backup directory based on the current date.

        Args:
            file (Path): The file to create subdirectories for.

        Returns:
            list[Path]: A list of subdirectories created.
        """
        subdirs = []
        for backup_dir in self.backup_directories:
            subdir = self.create_subdir(file, backup_dir)
            subdirs.append(subdir)
        return subdirs

    def backup_file(self, file : Path, delete : bool = False) -> list[Path]:
        """
        Move a file to all of the backup directories, organized into a subdir based on the current date.

        Args:
            file (Path): The file to move.
            delete (bool): Whether to delete the original file after moving.
        """
        if not self.backup_directories:
            logger.warning("No backup directories specified. Skipping move.")
            return []

        results = []
        errors = []
        for backup_dir in self.create_backup_subdirs(file):
            if result := self.copy_file(file, backup_dir):
                results.append(result)
            else:
                errors.append(backup_dir)
                
        if delete and results and not errors:
            self.delete_file(file)
            logger.debug(f"Deleted original file {file}")

        return results

        