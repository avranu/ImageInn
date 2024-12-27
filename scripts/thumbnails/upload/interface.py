"""*********************************************************************************************************************
*                                                                                                                      *
*                                                                                                                      *
*    Upload files to Immich.
*
*    This script is used because the immich app isn't reliable for uploading files, and I don't want to
*    manually upload files via the web interface (and leave that interface open in Chrome).
*
*    Instead, this cli script can be run as a periodic cronjob.
*
*    See also the organize.py script for organizing files into directories prior to this script being
*    executed.
*
*    This script is referenced in bash_aliases (but not in the github copy of it).
*
*    Example:
*        >>> python upload.py
*        >>> python upload.py -d /mnt/i/Phone
*        # bash_aliases defines `upload` to run this script for the current dir
*        >>> upload
*                                                                                                                      *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    METADATA:                                                                                                         *
*                                                                                                                      *
*        File:    interface.py                                                                                         *
*        Project: imageinn                                                                                             *
*        Version: 0.1.0                                                                                                *
*        Created: 2024-09-25                                                                                           *
*        Author:  Jess Mann                                                                                            *
*        Email:   jess.a.mann@gmail.com                                                                                *
*        Copyright (c) 2024 Jess Mann                                                                                  *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    LAST MODIFIED:                                                                                                    *
*                                                                                                                      *
*        2024-10-20     By Jess Mann                                                                                   *
*                                                                                                                      *
*********************************************************************************************************************"""
from __future__ import annotations
import os
import sys
import threading
import time

# Add the root directory of the project to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

import subprocess
from pathlib import Path
from pydantic import Field, PrivateAttr, field_validator
from typing import Iterable
from abc import ABC, abstractmethod
from scripts import setup_logging
from scripts.lib.file_manager import FileManager
from scripts.lib.db import ImagesDatabase
from scripts.thumbnails.upload.meta import ALLOWED_EXTENSIONS, DEFAULT_DB_PATH, IGNORE_DIRS
from scripts.thumbnails.upload.exceptions import AuthenticationError, ConfigurationError
from scripts.thumbnails.upload.status import FileStatus
from scripts.thumbnails.upload.template import FileTemplate

logger = setup_logging()

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
    templates : list[FileTemplate] = Field(default_factory=list)
    use_db : bool = False
    db_path : Path | None = DEFAULT_DB_PATH
    album : str | None = None
    skip : bool = False
    move_after_upload : Path | None = None

    _authenticated: bool = PrivateAttr(default=False)
    _db : ImagesDatabase | None = PrivateAttr(default=None)
    _start_ns : int = PrivateAttr(default=0)
    _bytes_lock : threading.Lock = PrivateAttr(default_factory=lambda: threading.Lock())
    _bytes_uploaded : int = PrivateAttr(default=0)

    @field_validator('directory', mode="before")
    def validate_directory(cls, v):
        if not v:
            raise ValueError("directory must be set.")

        # Allow str and list[str]
        v = Path(v)

        # v.exists() will raise an OSError if mounting points are not available
        try:
            exists = v.exists()
        except (OSError, Exception):
            exists = False

        if not exists:
            logger.error("Directory %s does not exist.", v)
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
        raise ConfigurationError("Invalid ignore_extensions value.")

    @field_validator('ignore_paths', mode="before")
    def validate_ignore_paths(cls, v):
        if not v:
            return []
        if isinstance(v, (str, Path)):
            return [str(v)]
        if isinstance(v, Iterable):
            return [str(path) for path in v]
        raise ConfigurationError("Invalid ignore_paths value.")

    @field_validator('backup_directories', mode="before")
    def validate_backup_directories(cls, v):
        if not v:
            return []
        if isinstance(v, (str, Path)):
            return [Path(v)]
        if isinstance(v, Iterable):
            return [Path(path) for path in v]
        raise ConfigurationError("Invalid backup_directories value.")

    @field_validator('db_path', mode="before")
    def validate_db_path(cls, v):
        if not v:
            return None
        db_path = Path(v)
        if not db_path.exists():
            raise FileNotFoundError(f"Database file {db_path} does not exist.")
        return db_path


    @field_validator('move_after_upload', mode="before")
    def validate_move_after_upload(cls, v):
        if not v:
            return None
        move_after_upload = Path(v)
        return move_after_upload

    @property
    def db(self) -> ImagesDatabase | None:
        # Cache it
        if not self._db:
            if not self.use_db or not self.db_path:
                return None
            
            self._db = ImagesDatabase(self.db_path)

        return self._db

    @property
    def bytes_uploaded(self) -> int:
        with self._bytes_lock:
            return self._bytes_uploaded

    @classmethod
    def get_default_extensions(cls) -> list[str]:
        # A temporary hack to inject a class attribute into a pydantic model.
        return ALLOWED_EXTENSIONS.copy()

    def record_bytes_uploaded(self, bytes_uploaded: int):
        """
        Record the number of bytes uploaded.

        Args:
            bytes_uploaded (int): The number of bytes uploaded.
        """
        with self._bytes_lock:
            self._bytes_uploaded += bytes_uploaded

    def authenticate(self):
        """
        Authenticate with Immich using the API key.

        Raises:
            AuthenticationError: If authentication fails
        """
        if self._authenticated:
            return

        logger.debug("Authenticating with Immich at %s", self.url)
        
        try:
            self.subprocess(["immich", "login-key", self.url, self.api_key])
            self._authenticated = True
            logger.debug("Authenticated successfully.")
        except subprocess.CalledProcessError as e:
            logger.error("Authentication failed: %s", e)
            raise AuthenticationError("Authentication failed.") from e

    @abstractmethod
    def upload(self, directory: Path | None = None, recursive: bool = True):
        """
        Abstract method to upload files.

        Args:
            directory (Path): The directory to upload.
            recursive (bool): Whether to upload recursively
        """
        raise NotImplementedError("upload method must be implemented in a subclass.")

    def should_ignore_file(self, image_path: Path, *, allow_hidden : bool = True, **kwargs) -> bool:
        """
        Check if a file should be ignored based on the extension, size, and status.

        Args:
            file (Path): The file to check.
            allow_hidden (bool): Whether to include hidden files.
            **kwargs: Additional arguments that subclasses may implement.

        Returns:
            bool: True if the file should be ignored, False otherwise
        """
        if not image_path.is_file():
            return True

        # Run super() first for optimization
        if super().should_ignore_file(image_path, allow_hidden=allow_hidden):
            return True

        suffix = image_path.suffix.lstrip('.').lower()

        # Ignore non-image extensions
        if suffix not in self.extensions:
            logger.debug("Ignoring non-media file due to extension: %s", image_path)
            return True

        if suffix in self.ignore_extensions:
            logger.debug("Ignoring file due to extension per user request: %s", image_path)
            return True

        if str(image_path) in self.ignore_paths:
            logger.debug("Ignoring file due to path: %s", image_path)
            return True

        for template in self.templates:
            if not template.match(image_path):
                logger.debug(f"Ignoring file {image_path} due to template {template}")
                return True

        if self.skip:
            if FileStatus.was_successful(image_path):
                logger.debug("Skipping already uploaded file %s", image_path)
                return True

        if self.large_file_size and self.file_size(image_path) > self.large_file_size:
            logger.debug(f"File {image_path} is larger than {self.large_file_size} bytes and will be skipped.")
            return True

        # No rules broken, so don't ignore
        return False

    def should_ignore_directory(self, directory: Path | str, *, allow_hidden : bool = False) -> bool:
        """
        Check if a directory should be ignored based on the name.

        Args:
            directory (Path): The directory to check.
            allow_hidden (bool): Whether to include hidden directories.

        Returns:
            bool: True if the directory should be ignored, False otherwise
        """
        directory = Path(directory)

        # Whitelist special dirs that would be excluded by rules below
        if directory.name in ['.thumbnails']:
            return False

        # Everything else works via a blacklist
        if directory.name in IGNORE_DIRS:
            logger.debug("Ignoring directory: %s", directory)
            return True

        # super handles hidden directories and double underscore prefixed
        return super().should_ignore_directory(directory, allow_hidden=allow_hidden)

    def create_backup_subdirs(self, image_path: Path) -> list[Path]:
        """
        Create subdirectories in each backup directory based on the current date.

        Args:
            file (Path): The file to create subdirectories for.

        Returns:
            list[Path]: A list of subdirectories created.
        """
        subdirs = []
        for backup_dir in self.backup_directories:
            subdir = self.create_subdir(image_path, backup_dir)
            subdirs.append(subdir)
        return subdirs

    def backup_file(self, file_path : Path, delete : bool = False) -> list[Path]:
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
        for backup_dir in self.create_backup_subdirs(file_path):
            if result := self.copy_file(file_path, backup_dir):
                results.append(result)
            else:
                errors.append(backup_dir)

        if delete and results and not errors:
            self.delete_file(file_path)
            logger.debug("Deleted original file %s", file_path)
        return results

    def get_upload_speed(self, decimal_places : int | None = 2) -> float:
        """
        Calculate the upload speed in MB/s.

        Returns:
            float: The upload speed in MB/s
        """
        if not self._start_ns:
            return 0
        
        time_now = time.time_ns()
        elapsed = (time_now - self._start_ns) / 1e9
        speed = self._bytes_uploaded / 1024 / 1024 / elapsed
        if decimal_places is not None:
            speed = round(speed, decimal_places)
        return speed