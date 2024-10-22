"""*********************************************************************************************************************
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    METADATA:                                                                                                         *
*                                                                                                                      *
*        File:    file_manager.py                                                                                      *
*        Project: imageinn                                                                                             *
*        Version: 1.0.0                                                                                                *
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
import asyncio
import os
import re
import sys
import threading
from typing import Iterator, Literal

# Add the root directory of the project to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import logging
from collections import defaultdict
from pathlib import Path
from functools import lru_cache
import hashlib
import xxhash
import shutil
from cachetools import LRUCache
from threading import Lock
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator
from scripts import setup_logging
from scripts.exceptions import ShouldTerminateException
from scripts.lib.script import Script

logger = logging.getLogger(__name__)

type StrPattern = str | re.Pattern | None

class FileManager(Script):
    directory: Path = Field(default=Path('.'))
    dry_run: bool = False
    glob_pattern: str = '*'
    filename_pattern : re.Pattern = Field(default=None, validate_default=True)

    _stats : dict[str, int] = PrivateAttr(default_factory=lambda: defaultdict(int))
    _stats_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)
    _hash_cache: LRUCache = PrivateAttr(default_factory=lambda: LRUCache(maxsize=10000))
    _cache_lock: Lock = PrivateAttr(default_factory=Lock)

    @field_validator('glob_pattern', mode='before')
    def validate_glob_pattern(cls, v):
        return v or cls.get_default_glob_pattern()

    @field_validator('directory', mode='before')
    def validate_directory(cls, v):
        return Path(v)

    @field_validator('filename_pattern', mode='before')
    def validate_filename_pattern(cls, v) -> re.Pattern:
        # None or empty results in None
        if not v:
            v = cls.get_default_filename_pattern()

        # Already a pattern
        if isinstance(v, re.Pattern):
            return v

        # Compile a string into a pattern, so it is cached for repeated use
        return re.compile(str(v), re.IGNORECASE)

    @property
    def stats_lock(self) -> threading.Lock:
        return self._stats_lock

    @property
    def files_moved(self) -> int:
        return self.get_stat('files_moved')

    @property
    def files_copied(self) -> int:
        return self.get_stat('files_copied')

    @property
    def files_deleted(self) -> int:
        return self.get_stat('files_deleted')

    @property
    def files_skipped(self) -> int:
        return self.get_stat('files_skipped')

    @property
    def directories_created(self) -> int:
        return self.get_stat('directories_created')

    @property
    def directories_deleted(self) -> int:
        return self.get_stat('directories_deleted')

    @property
    def errors(self) -> int:
        return self.get_stat('errors')

    @classmethod
    def get_default_glob_pattern(cls) -> str:
        # A temporary hack to inject a class attribute into a pydantic model.
        return '*'

    def get_stats(self) -> dict[str, int]:
        return self._stats.copy()

    def get_stat(self, key: str) -> int:
        with self._stats_lock:
            return self._stats[key]

    def record_stat(self, key: str, value: int = 1) -> None:
        with self._stats_lock:
            self._stats[key] += value

    def record_error(self, count : int = 1) -> None:
        self.record_stat('errors', count)

    def record_move_file(self, count : int = 1) -> None:
        self.record_stat('files_moved', count)

    def record_copy_file(self, count : int = 1) -> None:
        self.record_stat('files_copied', count)

    def record_delete_file(self, count : int = 1) -> None:
        self.record_stat('files_deleted', count)

    def record_skip_file(self, count : int = 1) -> None:
        self.record_stat('files_skipped', count)

    def record_move_directory(self, count : int = 1) -> None:
        self.record_stat('directories_created', count)

    def record_delete_directory(self, count : int = 1) -> None:
        self.record_stat('directories_deleted', count)

    def record_create_directory(self, count : int = 1) -> None:
        self.record_stat('directories_created', count)

    @classmethod
    def get_default_filename_pattern(cls) -> StrPattern:
        # A temporary hack to inject a class attribute into a pydantic model.
        return '.*'

    def get_hasher(self, hasher : str = 'md5') -> hashlib._Hash:
        """
        Get a hasher object for a given algorithm.

        Args:
            hasher: The name of the hashing algorithm.

        Returns:
            A hasher object.

        Raises:
            ValueError: If the hasher is not supported.
        """
        match hasher.lower():
            case 'md5':
                return hashlib.md5()
            case 'sha1':
                return hashlib.sha1()
            case 'sha256':
                return hashlib.sha256()
            case 'xxhash':
                return xxhash.xxh64()
            case _:
                return hashlib.new(hasher)

    def filename_match(self, filename: str | Path) -> re.Match[str] | Literal[False]:
        """
        Check if a filename matches the expected pattern.
        """
        if isinstance(filename, Path):
            filename = filename.name

        if (matches := self.filename_pattern.match(filename)):
            return matches

        return False

    def hash_file(self, filename: str | Path, partial: bool = False, hashing_algorithm : str = 'xxhash') -> str:
        """
        Calculate the hash of a file. Optionally perform partial hashing.

        Args:
            filename: The path to the file to hash.
            partial: If True, only hash the first and last 1MB of the file.
            hashing_algorithm: The hashing algorithm to use. Use xxhash for faster hashing.

        Returns:
            The hash of the file.
        """
        filename = Path(filename).resolve()
        cache_key = (filename, partial)

        with self._cache_lock:
            if cache_key in self._hash_cache:
                return self._hash_cache[cache_key]

        filename = Path(filename)
        if not filename.is_absolute():
            filename = self.directory / filename

        if not filename.exists():
            raise FileNotFoundError(f"File not found: {filename}")

        hasher = self.get_hasher(hashing_algorithm)

        file_size = filename.stat().st_size

        # Define the size of the chunks to read
        chunk_size = 1024 * 1024  # 1MB

        with open(filename, "rb") as f:
            if partial and file_size > 2 * chunk_size:
                # Read the first chunk_size bytes
                hasher.update(f.read(chunk_size))
                # Seek to the last chunk_size bytes
                f.seek(-chunk_size, os.SEEK_END)
                hasher.update(f.read(chunk_size))
            else:
                # File is small, read the whole file
                for chunk in iter(lambda: f.read(4096), b""):
                    hasher.update(chunk)

        result = hasher.hexdigest()

        with self._cache_lock:
            self._hash_cache[cache_key] = result

        return result

    def yield_directories(self, directory: Path, *, recursive: bool = True, allow_hidden : bool = False) -> Iterator[Path]:
        """
        Yield directories

        Args:
            directory (Path): The directory to search.
            recursive (bool): Whether to search recursively.
            allow_hidden (bool): Whether to include hidden directories.

        Yields:

        """
        if not recursive:
            if allow_hidden or not directory.name.startswith('.'):
                if directory.name != '.trash':
                    yield directory
            return

        logger.debug('Searching %s for directories.', directory.absolute())

        for dirpath, dirnames, _ in os.walk(directory):
            dirpath_obj = Path(dirpath)

            if dirpath_obj.name == '.trash':
                continue

            # Skip hidden directories if not allowed
            if not allow_hidden:
                # Remove hidden directories from dirnames so os.walk doesn't traverse into them
                dirnames[:] = [d for d in dirnames if not d.startswith('.')]

                # Skip the current directory if it's hidden
                if dirpath_obj.name.startswith('.'):
                    continue

            yield dirpath_obj

    def get_all_directories(self, directory: Path, *, recursive: bool = True, allow_hidden : bool = False) -> list[Path]:
        """
        Get a list of directories

        Args:
            directory (Path): The directory to search.
            recursive (bool): Whether to search recursively.
            allow_hidden (bool): Whether to include hidden directories.

        Returns:
            list[Path]: A list of directories
        """
        return list(self.yield_directories(directory, recursive=recursive, allow_hidden=allow_hidden))

    async def count_directories(self, directory: Path, *, recursive: bool = True) -> int:
        """
        Asynchronously count the number of directories.

        Args:
            directory (Path): The root directory to start counting from.
            recursive (bool): Whether to count directories recursively.

        Returns:
            int: The total number of directories.
        """
        # Avoid using a list comprehension to avoid loading all directories into memory
        count = 0
        for _ in self.yield_directories(directory, recursive=recursive):
            count += 1
            await asyncio.sleep(0)  # Yield control to the event loop
        return count

    def yield_files(self, directory : Path | None = None, *, recursive : bool = True) -> Iterator[Path]:
        """
        Yield files in a directory.

        Args:
            directory: The directory to search. Defaults to self.directory.

        Yields:
            The next file in the directory.
        """
        directory = directory or self.directory
            
        if recursive:
            files = directory.rglob(self.glob_pattern)
        else:
            files = directory.glob(self.glob_pattern)

        count = 0
        for f in files:
            if self.should_include_file(f):
                count += 1
                if count % 100 == 0:
                    logger.info('Yielded %d files in %s...', count, directory)
                yield f

    def get_all_files(self, directory : Path | None = None, *, recursive : bool = True) -> list[Path]:
        """
        Get a list of files in a directory.

        Args:
            directory: The directory to search. Defaults to self.directory.

        Returns:
            A list of files in the directory which match the glob pattern.
        """
        return list(self.yield_files(directory, recursive))

    def should_include_file(self, item: Path) -> bool:
        """
        Check if a file should be included.

        Args:
            item: The file to check.

        Returns:
            True if the file should be included, False otherwise.
        """
        if not item.is_file():
            return False

        if not self.filename_match(item.name):
            logger.debug('Skipping file due to its name: %s', item)
            return False

        return True

    async def count_files(self, directory: Path, recursive: bool = True) -> int:
        """
        Asynchronously count the number of files.

        Args:
            directory (Path): The root directory to start counting from.
            recursive (bool): Whether to count files recursively.

        Returns:
            int: The total number of files.
        """
        # Avoid using a list comprehension to avoid loading all files into memory
        count = 0
        for _ in self.yield_files(directory):
            count += 1
            await asyncio.sleep(0)  # Yield control to the event loop
            if count % 100 == 0:
                logger.info('Counted %d files...', count)
        logger.critical('Finished counting files!!!')
        return count

    def file_sizes_match(self, source_path: Path, destination_path: Path) -> bool:
        """
        Check if the sizes of two files match.

        Args:
            source_path: The source file.
            destination_path: The target file.

        Returns:
            True if the file sizes match, False otherwise.
        """
        return self.file_stat(source_path).st_size == self.file_stat(destination_path).st_size

    def file_times_match(self, source_path: Path, destination_path: Path) -> bool:
        """
        Check if the modification times of two files match.

        Args:
            source_path: The source file.
            destination_path: The target file.

        Returns:
            True if the file modification times match, False otherwise.
        """
        return self.file_stat(source_path).st_mtime == self.file_stat(destination_path).st_mtime

    @lru_cache(maxsize=1024)
    def file_stat(self, file_path: Path) -> os.stat_result:
        """
        Get the stat information for a file.

        This function is cached to avoid repeated stat calls for the same file.

        Args:
            file_path: The file to get the stat information for.

        Returns:
            The stat information for the file.
        """
        return file_path.stat()

    def file_hashes_match(self, source_path: Path, destination_path: Path) -> bool:
        """
        Check if the hashes of two files match.

        Args:
            source_path: The source file.
            destination_path: The target file.

        Returns:
            True if the file hashes match, False otherwise.
        """
        # Perform partial hashing
        source_hash = self.hash_file(source_path, partial=True)
        destination_hash = self.hash_file(destination_path, partial=True)

        if source_hash != destination_hash:
            return False

        # As a final check, if partial hashes match, perform full hash
        source_full_hash = self.hash_file(source_path, partial=False)
        destination_full_hash = self.hash_file(destination_path, partial=False)

        return source_full_hash == destination_full_hash

    def files_match(self, source_path: Path, destination_path: Path, skip_hash: bool = False) -> bool:
        """
        Check if two files match by comparing size, modification time, and hashes.

        Args:
            source_path: The source file.
            destination_path: The target file.
            skip_hash: If True, only compare the file sizes.

        Returns:
            True if the files match, False otherwise.
        """
        if not destination_path.exists():
            return False

        # Compare file sizes
        if not self.file_sizes_match(source_path, destination_path):
            return False

        # Compare modification times
        if not self.file_times_match(source_path, destination_path):
            return False

        if skip_hash:
            return True

        return self.file_hashes_match(source_path, destination_path)

    def exists(self, file_path: Path) -> bool:
        """
        Checks if a file or directory exists. Catches OSErrors if a mounting point is not found.

        Args:
            file_path: The file or directory to check.

        Returns:
            True if the file or directory exists, False otherwise
        """
        try:
            if not file_path.is_absolute():
                file_path = self.directory / file_path
            return file_path.exists()
        except (OSError, Exception) as e:
            logger.debug(f"Error checking if file exists: {e}")
        return False

    def mkdir(self, directory: Path, *, parents: bool = True, exist_ok : bool = True) -> Path:
        """
        Create a directory if it does not exist.

        Args:
            directory: The directory to create.

        Returns:
            The directory path.
        """
        if not self.check_dry_run(f'creating directory {directory}'):
            directory.mkdir(parents=parents, exist_ok=exist_ok)

        self.record_create_directory()

        return directory

    def delete_file(self, file_path: Path, use_trash : bool = True) -> bool:
        """
        Delete a file.

        Args:
            file_path: The file to delete.
            message: An optional message to log.

        Returns:
            True if the file was deleted, False otherwise.

        Raises:
            OneFileException: If an error occurs while deleting the file.
        """
        if use_trash:
            trash_file_path = self._find_trash_name(file_path)
            trash_dir = trash_file_path.parent

            if not self.check_dry_run(f'moving {file_path} to trash {trash_dir}'):
                file_path.rename(trash_file_path)
        else:
            if not self.check_dry_run(f'deleting file {file_path}'):
                file_path.unlink()

        if not file_path.exists():
            self.record_delete_file()
            return True

        return False

    def delete_empty_directories(self, directory: Path | None = None) -> None:
        """
        Delete empty directories.
        """
        directory = directory or self.directory

        count = 0
        for dirpath in self.yield_directories(directory, recursive=True):
            if self.delete_directory_if_empty(dirpath):
                count += 1

        logger.info('Cleaned up %d empty directories.', count)

    def delete_directory_if_empty(self, directory: Path, recursive : bool = True, cleanup : bool = True) -> bool:
        """
        Delete an empty directory, or return False.

        Args:
            directory: The directory to delete.
            recursive: Whether to delete recursively.
            cleanup: Whether to remove files that stall the process.
        """
        junk_files = []
        for f in directory.iterdir():
            if f.is_dir():
                if not recursive:
                    # A directory exists and we can't remove it...
                    return False

                if self.delete_directory_if_empty(f):
                    # subdir is now deleted, so it doesnt count
                    continue

                return False

            if cleanup:
                # Remove files we don't care about that stall this process.
                if f.name in ['.picasa.ini', 'Thumbs.db', '.upload_status.txt', 'upload_status.txt']:
                    # Don't remove junk files unless the rest of the dir is empty
                    junk_files.append(f)
                    continue

            # something was found, so it's not empty
            logger.debug('NOT EMPTY: Found file="%s" in dir="%s".', f, directory.absolute())
            return False

        # Nothing found except junk files... time to remove them.
        for junk in junk_files:
            logger.debug('Deleting file="%s" in directory="%s"', junk, directory)
            if not self.delete_file(junk, use_trash=False):
                logger.error('Unable to delete junk file: %s', junk)
                return False

        # Nothing was found
        if not self.check_dry_run(f'deleting empty directory {directory}'):
            directory.rmdir()
            self.record_delete_directory()
        return True

    def _find_trash_name(self, file_path: Path) -> Path:
        """
        Find a unique name for a file in the trash directory.

        Args:
            file_path: The file to move to the trash.

        Returns:
            The path to the file in the trash directory.
        """
        trash_dir = self.directory / '.trash'
        trash_dir.mkdir(exist_ok=True)

        trash_file_path = trash_dir / file_path.name
        number = 1
        while trash_file_path.exists():
            trash_file_path = trash_dir / f"{file_path.stem}_{number}{file_path.suffix}"

        return trash_file_path

    def move_file(self, source_path: Path, destination_path: Path, verify : bool = True) -> Path:
        """
        Move a file to a new location.

        Args:
            source: The source file to move.
            destination: The destination path.

        Returns:
            The destination path.
        """
        # Destination must be absolute for Path.rename to be consistent
        if not destination_path.is_absolute():
            logger.debug(f"Making destination path absolute: {destination_path}")
            destination_path = self.directory / destination_path

        # Convert dirs into file paths
        if destination_path.is_dir():
            destination_path = destination_path / source_path.name

        if destination_path.exists():
            raise FileExistsError(f"Move Destination file already exists: {destination_path}")

        if verify:
            source_hash = self.hash_file(source_path)

        destination_dir = destination_path.parent
        if not self.check_dry_run(f'moving {source_path} to {destination_dir}'):
            source_path.rename(destination_path)
            self.record_move_file()

            if verify:
                destination_hash = self.hash_file(destination_path)
                if source_hash != destination_hash:
                    logger.critical(f"Checksum mismatch after moving {source_path} to {destination_dir}")
                    raise ShouldTerminateException(f'Checksum mismatch after moving {source_path} to {destination_dir}')

        return destination_path

    def copy_file(self, source_path : Path, destination_path : Path, verify : bool = True) -> Path:
        """
        Copy a file to a new location.

        Args:
            source: The source file to copy.
            destination: The destination path.

        Returns:
            The destination path.
        """
        # Destination must be absolute for Path.rename to be consistent
        if not destination_path.is_absolute():
            logger.debug(f"Making destination path absolute: {destination_path}")
            destination_path = self.directory / destination_path

        # Convert dirs into file paths
        if destination_path.is_dir():
            destination_path = destination_path / source_path.name

        if destination_path.exists():
            raise FileExistsError(f"Copy Destination file already exists: {destination_path}")

        if verify:
            source_hash = self.hash_file(source_path)

        if not self.check_dry_run(f'copying {source_path} to {destination_path}'):
            shutil.copy2(source_path, destination_path)

            if verify:
                destination_hash = self.hash_file(destination_path)
                if source_hash != destination_hash:
                    logger.critical(f"Checksum mismatch after copying {source_path} to {destination_path}")
                    raise ShouldTerminateException(f'Checksum mismatch after copying {source_path} to {destination_path}')

        self.record_copy_file()
        return destination_path

    def check_dry_run(self, message : str | None = None) -> bool:
        """
        Check if the script is running in dry-run mode.

        Args:
            message: An optional message to log.

        Returns:
            True if running in dry-run mode, False otherwise.
        """
        if self.dry_run:
            logger.info('DRY RUN: Skipped %s', message or 'Operation skipped')
            return True

        if message:
            logger.debug('RUN -> %s', message)
        return False

    def __hash__(self) -> int:
        return hash(self.directory)