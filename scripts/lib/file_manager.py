from __future__ import annotations
import os
import re
import sys

# Add the root directory of the project to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from pathlib import Path
from functools import lru_cache
import hashlib
import xxhash
import shutil
from concurrent.futures import ThreadPoolExecutor
from cachetools import LRUCache
from threading import Lock
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator
from scripts import setup_logging
from scripts.exceptions import ShouldTerminateException

logger = setup_logging()

class FileManager(BaseModel):
    directory: Path = Field(default=Path('.'))
    file_prefix: str = 'PXL_20'
    dry_run: bool = False
    
    _files_moved: list[Path] = PrivateAttr(default_factory=list)
    _files_copied : list[Path] = PrivateAttr(default_factory=list)
    _files_deleted: list[Path] = PrivateAttr(default_factory=list)
    _files_skipped: list[Path] = PrivateAttr(default_factory=list)
    _hash_cache: LRUCache = PrivateAttr(default_factory=lambda: LRUCache(maxsize=10000))
    _cache_lock: Lock = PrivateAttr(default_factory=Lock)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @field_validator('directory', mode='before')
    def validate_directory(cls, v):
        return Path(v)

    @property
    def files_moved(self) -> list[Path]:
        return self._files_moved

    @property
    def files_deleted(self) -> list[Path]:
        return self._files_deleted

    @property
    def files_skipped(self) -> list[Path]:
        return self._files_skipped

    @property
    def files_copied(self) -> list[Path]:
        return self._files_copied

    @property
    def filename_pattern(self) -> re.Pattern:
        if not self._filename_pattern:
            self._filename_pattern = re.compile(rf'^{re.escape(self.file_prefix)}(20\d{{6}})_')
        return self._filename_pattern

    def append_moved_file(self, file_path: Path) -> None:
        """
        Add a file to the list of moved files.
        """
        self._files_moved.append(file_path)

    def append_copied_file(self, file_path: Path) -> None:
        """
        Add a file to the list of copied files.
        """
        self._files_copied.append(file_path)
        
    def append_deleted_file(self, file_path: Path) -> None:
        """
        Add a file to the list of deleted files. 
        """
        self._files_deleted.append(file_path)

    def append_skipped_file(self, file_path: Path) -> None:
        """
        Add a file to the list of skipped files.
        """
        self._files_skipped.append(file_path)

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

    def get_files(self, directory : Path | None = None) -> list[Path]:
        """
        Get a list of files in a directory.

        Args:
            directory: The directory to search. Defaults to self.directory.

        Returns:
            A list of files in the directory which match the file prefix.
        """
        directory = directory or self.directory
        return directory.glob(f'{self.file_prefix}*.jpg')

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

    def find_subdir(self, filename: str | Path) -> str:
        """
        Find the subdirectory for a file based on its filename.

        Args:
            filename: The filename to extract the date from.

        Returns:
            The name of the proposed subdirectory.

        Raises:
            ValueError: If the filename does not match the expected format.
        """
        if isinstance(filename, Path):
            filename = filename.name

        if not (match := self.filename_pattern.match(str(filename))):
            raise ValueError(f"Invalid filename format: {filename}")

        # Subdir name
        date_part = match.group(1)
        year = date_part[:4]
        month = date_part[4:6]
        dir_name = f"{year}-{month}"

        return dir_name

    def create_subdir(self, filename : str | Path, parent_directory : Path | None = None) -> Path:
        """
        Create a subdirectory for a file based on its filename.

        Args:
            filename: The filename to extract the date from.
            parent_directory: The parent directory to create the subdirectory in, defaults to self.directory.

        Returns:
            The path to the subdirectory.
        """
        parent_directory = parent_directory or self.directory

        subdir = self.find_subdir(filename)

        return self.mkdir(parent_directory / subdir)

    def mkdir(self, directory: Path) -> Path:
        """
        Create a directory if it does not exist.

        Args:
            directory: The directory to create.

        Returns:
            The directory path.
        """
        if not self.check_dry_run(f'creating directory {directory}'):
            directory.mkdir(exist_ok=True)
            
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

            if not self.check_dry_run(f'moving {file_path} to trash {trash_file_path}'):
                file_path.rename(trash_file_path)
        else:
            if not self.check_dry_run(f'deleting file {file_path}'):
                file_path.unlink()

        if not file_path.exists():
            self.append_deleted_file(file_path)
            return True

        return False

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
            raise FileExistsError(f"Destination file already exists: {destination_path}")
        
        if verify:
            source_hash = self.hash_file(source_path)

        if not self.check_dry_run(f'moving {source_path} to {destination_path}'):
            source_path.rename(destination_path)
            self.append_moved_file(destination_path)

            if verify:
                destination_hash = self.hash_file(destination_path)
                if source_hash != destination_hash:
                    logger.critical(f"Checksum mismatch after moving {source_path} to {destination_path}")
                    raise ShouldTerminateException('Checksum mismatch after moving')

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
            raise FileExistsError(f"Destination file already exists: {destination_path}")

        if verify:
            source_hash = self.hash_file(source_path)

        if not self.check_dry_run(f'copying {source_path} to {destination_path}'):
            shutil.copy2(source_path, destination_path)

            if verify:
                destination_hash = self.hash_file(destination_path)
                if source_hash != destination_hash:
                    logger.critical(f"Checksum mismatch after copying {source_path} to {destination_path}")
                    raise ShouldTerminateException('Checksum mismatch after copying')
                
        self.append_copied_file(destination_path)
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
        return False

    def __hash__(self) -> int:
        return hash(self.directory)