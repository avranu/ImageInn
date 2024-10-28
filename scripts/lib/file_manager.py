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
import asyncio
import os
import re
import subprocess
import sys
import threading
from typing import Iterator, Literal

from alive_progress import alive_bar

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

JUNK_FILENAMES = [
    '.picasa.ini', 
    'Thumbs.db', 
    '.upload_status.txt', 
    'upload_status.txt',
]

# SONY JUNK
SONY_JUNK_FILENAMES = [
    'INDEX.BDM',
    'MOVIEOBJ.BDM',
    'MEDIAPRO',
    'MEDIAPRO.XML',
    'STATUS.BIN',
    'CAMSET01.DAT',
    'SONYCARD.IND',
]

class FileManager(Script):
    directory: Path = Field(default=Path('.'))
    trash_directory : Path | None = None

    dry_run: bool = False
    glob_pattern: str = '*'
    filename_pattern : re.Pattern = Field(default=None, validate_default=True)
    skip_mtime_compare : bool = False

    _stats : dict[str, int] = PrivateAttr(default_factory=lambda: defaultdict(int))
    _stats_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)
    _hash_cache: LRUCache = PrivateAttr(default_factory=lambda: LRUCache(maxsize=10000))
    _cache_lock: Lock = PrivateAttr(default_factory=Lock)

    _sony_clip_pattern : re.Pattern | None = None

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

    @property
    def sony_clip_pattern(self) -> re.Pattern:
        if not self._sony_clip_pattern:
            self._sony_clip_pattern = re.compile(r'.*/M4ROOT/CLIP/\w+[.](xml|XML)$')
        return self._sony_clip_pattern

    @classmethod
    def get_default_glob_pattern(cls) -> str:
        # A temporary hack to inject a class attribute into a pydantic model.
        return '*'

    def get_trash_directory(self) -> Path:
        if not self.trash_directory:
            self.trash_directory = self.directory / '.trash'
        return self.trash_directory

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
            if directory.name.startswith('.'):
                if not allow_hidden or directory.name == '.trash':
                    return
                
            yield directory

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

        for f in files:
            if self.should_include_file(f):
                yield f
        return

    def get_all_files(self, directory : Path | None = None, *, recursive : bool = True) -> list[Path]:
        """
        Get a list of files in a directory.

        Args:
            directory: The directory to search. Defaults to self.directory.

        Returns:
            A list of files in the directory which match the glob pattern.
        """
        return list(self.yield_files(directory, recursive=recursive))

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
        for _ in self.yield_files(directory, recursive=recursive):
            count += 1
            await asyncio.sleep(0)  # Yield control to the event loop
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

        Raises:
            ValueError: If the source and destination files are the same.
        """
        if not destination_path.exists():
            return False

        # If the files refer to the same destination, 
        # ...we're doing something upstream that we don't think we're doing
        if source_path.samefile(destination_path):
            raise ValueError(f"Source and destination files are the same: {source_path}")

        # Compare file sizes
        if not self.file_sizes_match(source_path, destination_path):
            return False

        # Compare modification times 
        if not self.skip_mtime_compare and not self.file_times_match(source_path, destination_path):
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
            logger.debug("Error checking if file exists: %s", e)
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

        if not directory.exists():
            logger.warning('delete_empty_directories on directory that does not exist: %s', directory)
            return

        with alive_bar(title=f"Organizing {str(directory)[-25:]}/", unit='files', dual_line=True, unknown='waves') as self._progress_bar:
            count = 0
            skipped = 0
            for dirpath in self.yield_directories(directory, recursive=True):
                if self.delete_directory_if_empty(dirpath):
                    count += 1
                else:
                    skipped += 1
                self._progress_bar()
                self._progress_bar.text(f'Cleaning directories: {count} deleted, {skipped} skipped')

        logger.info('Cleaned up %d empty directories. %d remain.', count, skipped)

    def delete_directory_if_empty(self, directory: Path, recursive : bool = True, cleanup : bool = True) -> bool:
        """
        Delete an empty directory, or return False.

        Args:
            directory: The directory to delete.
            recursive: Whether to delete recursively.
            cleanup: Whether to remove files that stall the process.
        """
        if not directory.exists():
            return True
        
        junk_files = []
        for f in directory.iterdir():
            if f.is_dir():
                if recursive and self.delete_directory_if_empty(f):
                    # subdir is now deleted, so it doesnt count
                    continue

                # A directory exists and we can't remove it...
                return False

            if cleanup:
                # Remove files we don't care about that stall this process.
                if self.is_junk(f):
                    # Don't remove junk files unless the rest of the dir is empty
                    junk_files.append(f)
                    continue

            # something was found, so it's not empty
            logger.debug('Directory not empty: Found file="%s" in dir="%s".', f, directory.absolute())
            return False

        # Nothing found except junk files... time to remove them.
        for junk in junk_files:
            logger.debug('Deleting file="%s" in directory="%s"', junk, directory)
            if not self.delete_file(junk, use_trash=False):
                logger.error('Unable to delete junk file: %s', junk)
                return False

        # Nothing was found
        if not self.check_dry_run(f'deleting empty directory {directory}'):
            try:
                # use absolute to avoid Path('.').rmdir(), which generates an OSError
                directory.absolute().rmdir()
            except OSError as ose:
                logger.error('Unable to delete directory: %s -> %s', directory, ose)
                return False

        self.record_delete_directory()
        return True

    def is_junk(self, file_path : Path) -> bool:
        """
        Check if a file is junk.

        Args:
            file_path: The file to check.

        Returns:
            True if the file is junk, False otherwise.
        """
        # We may check this a few times, so cache it here
        name = file_path.name
        filesize = file_path.stat().st_size
        is_hidden = name.startswith('.')

        # Check known junk filenames
        if name in JUNK_FILENAMES:
            return True

        # Less than 10k
        if filesize < (1024 * 10):
            if name in SONY_JUNK_FILENAMES:
                return True

            # Check if path ends with M4ROOT/CLIP/\w+.xml
            if self.sony_clip_pattern.match(str(file_path)):
                return True

        # really EXTREMELY small (50 bytes)
        if filesize < 50:
            if is_hidden:
                return True

            if self.is_temporary_file(file_path):
                return True
            
        # completely empty
        if filesize == 0:
            if not file_path.suffix or file_path.suffix == '.txt':
                return True

        # No condition was met, so it's not junk
        return False

    def is_temporary_file(self, file_path : Path) -> bool:
        """
        Check if a file is temporary.

        Args:
            file_path: The file to check.

        Returns:
            True if the file is temporary, False otherwise.
        """
        if file_path.suffix == '.tmp':
            return True

        if file_path.name.startswith('~'):
            return True

        if not file_path.suffix:
            if file_path.name.startswith('tmp_') or file_path.name.startswith('temp_'):
                return True
            if file_path.name.endswith('_tmp') or file_path.name.endswith('_temp'):
                return True

        # Swap files
        if file_path.suffix == '.swp':
            return True        

        # No conditions met
        return False

    def _find_trash_name(self, file_path: Path) -> Path:
        """
        Find a unique name for a file in the trash directory.

        Args:
            file_path: The file to move to the trash.

        Returns:
            The path to the file in the trash directory.
        """
        trash_dir = self.get_trash_directory()
        trash_dir.mkdir(exist_ok=True)

        trash_file_path = trash_dir / file_path.name
        number = 1
        while trash_file_path.exists():
            trash_file_path = trash_dir / f"{file_path.stem}_{number}{file_path.suffix}"

        return trash_file_path

    def move_file(self, source_path: Path, destination_path: Path) -> Path:
        """
        Move a file to a new location.

        Args:
            source: 
                The source file to move.
            destination: 
                The destination path.
            verify: 
                Whether to verify the move by comparing checksums. 
                If None, verify will be set to True if the source and destination are on different drives.
                The rationale is that moving files to the same drive just modifies the pointer, and the file data should not change,
                however, moving files to a different drive will require a full copy, so the file data should be verified.

        Returns:
            The destination path.

        Raises:
            FileExistsError: If the destination file already exists.
        """
        # Destination must be absolute for Path.rename to be consistent
        if not destination_path.is_absolute():
            logger.debug("Making destination path absolute: %s", destination_path)
            destination_path = self.directory / destination_path

        # Convert dirs into file paths
        if destination_path.is_dir():
            destination_path = destination_path / source_path.name

        # Move XMP files alongside photos
        source_xmp_path : Path | None = source_path.with_suffix('.xmp')
        destination_xmp_path : Path | None = destination_path.with_suffix('.xmp')

        if destination_path.exists():
            raise FileExistsError(f"Move Destination file already exists: {destination_path}")

        destination_dir = destination_path.parent
        if not self.check_dry_run(f'moving {source_path} to {destination_dir}'):
            # This verifies the destination path and compares checksums
            self._move_file(source_path, destination_path)
            self.record_move_file()

            # Copy xmp files after verification, so errors don't interfere.
            # ... do not verify xmp files, as they are not critical
            try:
                if source_xmp_path.exists(follow_symlinks=False):
                    self._move_file(source_xmp_path, destination_xmp_path)
            except OSError as ose:
                logger.warning('Error moving XMP file: %s', ose)

        return destination_path

    def _move_file(self, source_path : Path, destination_path : Path) -> bool:
        """
        Move a file to a new location.

        Args:
            source: 
                The source file to move.
            destination: 
                The destination path.

        Returns:
            bool: True if the file was moved, False otherwise.

        Raises:
            subprocess.CalledProcessError: If an error occurs while moving the file.
            FileNotFoundError: If the file is not found after moving.
            ValueError: If the checksums do not match after moving.
        """
        # If the drive is the same, then simply rename it to avoid "actually" copying the file.
        # ... this is faster and eliminates corruption while copying the data.
        if source_path.resolve().drive == destination_path.resolve().drive:
            source_path.rename(destination_path)
            return destination_path.exists()
        
        # If the drives are different, try using rsync
        logger.debug('Drives are different, so moving file with rsync: %s -> %s', source_path, destination_path)
        # hashes are checked during this command. May raise ValueError
        result = self._copy_with_rsync(source_path, destination_path)

        # We know hashes match, so delete the source file
        if result:
            self.delete_file(source_path)

        return result

    def copy_file(self, source_path : Path, destination_path : Path) -> Path:
        """
        Copy a file to a new location.

        Args:
            source: 
                The source file to copy.
            destination: 
                The destination path.
            verify:
                Whether to verify the copy by comparing checksums. 
                If None, verify will be set to True if the source and destination are on different drives.
                The rationale is that copying files to the same drive just duplicates the file data, and the file data should not change,
                however, copying files to a different drive will require a full copy, so the file data should be verified.

        Returns:
            The destination path.
        """     
        # Destination must be absolute for Path.rename to be consistent
        if not destination_path.is_absolute():
            logger.debug("Making destination path absolute: %s", destination_path)
            destination_path = self.directory / destination_path

        # Convert dirs into file paths
        if destination_path.is_dir():
            destination_path = destination_path / source_path.name

        if destination_path.exists():
            raise FileExistsError(f"Copy Destination file already exists: {destination_path}")

        if not self.check_dry_run(f'copying {source_path} to {destination_path}'):
            try:
                # This verifies the file checksum after copy.
                self._copy_with_rsync(source_path, destination_path)
            except PermissionError as pe:
                if 'Operation not permitted' in str(pe) and destination_path.exists():
                    logger.warning('WARNING: Permission error (likely due to copying metadata). source_path="%s", destination_path="%s" -> %s', source_path.absolute(), destination_path.absolute(), pe)
                    raise ShouldTerminateException(f'Permission error copying file: {source_path} -> {destination_path}') from pe
                else:
                    raise
            except subprocess.TimeoutExpired as te:
                logger.error('Timeout error copying file: %s -> %s -> %s', source_path, destination_path, te)
                raise

        self.record_copy_file()
        return destination_path

    def _copy_with_shutil(self, source_path : Path, destination_path : Path) -> bool:
        """
        Copy a file to a new location using shutil.

        Args:
            source: 
                The source file to copy.
            destination: 
                The destination path.

        Returns:
            The destination path.

        Raises:
            FileNotFoundError: If the file is not found after copying.
            ValueError: If the checksums do not match after copying.
        """
        source_hash = self.hash_file(source_path)
        
        result = shutil.copy2(source_path, destination_path)

        if not result or not destination_path.exists():
            raise FileNotFoundError(f"Unable to find file after copy: {destination_path}")

        destination_hash = self.hash_file(destination_path)
        if source_hash != destination_hash:
            logger.critical(f"Checksum mismatch after copying with shutil {source_path} to {destination_path}")
            raise ValueError(f"Checksum mismatch after copying with shutil {source_path} to {destination_path}")

        return True

    def _copy_with_rsync(self, source_path : Path, destination_path : Path) -> bool:
        """
        Copy a file to a new location using rsync.

        Args:
            source: 
                The source file to copy.
            destination: 
                The destination path.

        Returns:
            The destination path.

        Raises:
            subprocess.CalledProcessError: If an error occurs while copying the file.
            FileNotFoundError: If the file is not found after copying.
            ValueError: If the checksums do not match after copying.
        """
        source_hash = self.hash_file(source_path)
        
        try:
            self.subprocess(['rsync', '-a', '--times', str(source_path), str(destination_path)])
        except subprocess.CalledProcessError as e:
            logger.error('Error copying file with rsync: %s', e)
            raise

        if not destination_path.exists():
            raise FileNotFoundError(f"Unable to find file after copy with rsync: {destination_path}")

        destination_hash = self.hash_file(destination_path)
        if source_hash != destination_hash:
            logger.critical(f"Checksum mismatch after copying with rsync {source_path} to {destination_path}")
            raise ValueError(f"Checksum mismatch after copying with rsync {source_path} to {destination_path}")

        return True

    def check_dry_run(self, message : str | None = None) -> bool:
        """
        Check if the script is running in dry-run mode.

        Args:
            message: An optional message to log.

        Returns:
            True if running in dry-run mode, False otherwise.
        """
        if self.dry_run:
            logger.info('DRY RUN: Skipped %s', message or 'Operation')
            return True

        if message:
            logger.debug('RUN -> %s', message)
        return False

    def _shortpath(self, fullpath : Path | str, max_size : int = 30) -> str:
        # Ensure it's a str
        fullpath = f'{str(fullpath)}/'

        if len(fullpath) <= max_size:
            return fullpath
        
        index_start = -1 * (max_size - 5)
        return f'... {fullpath[index_start:]}'

    def __hash__(self) -> int:
        return hash(self.directory)