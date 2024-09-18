#!/usr/bin/env python3
"""
Version 1.0
Date: 2024-09-17
Working

Example:
    python -m scripts.monthly.organize -d /mnt/i/Phone/
"""
from __future__ import annotations
import sys
import os

# Add the root directory of the project to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import re
import hashlib
from pathlib import Path
import logging
import argparse
from functools import lru_cache
from typing import Literal
from tqdm import tqdm
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator
from scripts.monthly.exceptions import ShouldTerminateException, OneFileException, DuplicationHandledException

logger = logging.getLogger(__name__)


class FileOrganizer(BaseModel):
    """
    Organize files into monthly directories based on the filename.

    - Filenames are expected to start with 'PXL_' followed by an 8-digit date in the format 'YYYYMMDD'.
    - Files are moved to a directory named 'YYYY-MM' under the specified directory.
    - If a file with the same name already exists in the target directory, a unique filename is generated.
    """
    directory: Path = Field(default=Path('.'))
    file_prefix: str = 'PXL_'
    dry_run: bool = False
    batch_size: int = -1

    duplicates_found: int = 0
    directories_created: int = 0

    # Private attributes
    _files_moved: list[Path] = PrivateAttr(default_factory=list)
    _count_files_moved: int = PrivateAttr(default=0)
    _files_deleted: list[Path] = PrivateAttr(default_factory=list)
    _count_files_deleted: int = PrivateAttr(default=0)
    _files: list[Path] = PrivateAttr(default_factory=list)
    _count_files: int = PrivateAttr(default=0)
    _progress: tqdm | None = PrivateAttr(default=None)
    _filename_pattern : re.Pattern | None = PrivateAttr(default=None)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @field_validator('directory', mode='before')
    def validate_directory(cls, v):
        return Path(v)

    @property
    def files(self) -> list[Path]:
        # Cache it
        if not self._files:
        
            try:
                if self.batch_size > 0:
                    # Optimize in the case of a limited batch size, since glob is a generator
                    logger.debug(f"Limiting files to {self.batch_size}")
                    self._files = []
                    for f in self.directory.glob(f'{self.file_prefix}*'):
                        if f.is_file():
                            self.append_file(f)
                            if self.file_count >= self.batch_size:
                                break
                else:
                    # Grab everything
                    self._files = [f for f in self.directory.glob(f'{self.file_prefix}*') if f.is_file()]
                    self._count_files = len(self._files)
            except Exception as e:
                raise ShouldTerminateException(f"Error accessing directory {self.directory}") from e

        return self._files

    @property
    def filename_pattern(self) -> re.Pattern:
        if not self._filename_pattern:
            self._filename_pattern = re.compile(rf'^{re.escape(self.file_prefix)}(20\d{{6}})_')
        return self._filename_pattern

    @property
    def file_count(self) -> int:
        # Cache it
        if not self._count_files:
            self._count_files = len(self.files)

        return self._count_files

    @property
    def progress(self) -> tqdm:
        if self._progress is None:
            self._progress = tqdm(total=self.file_count, desc='Processing files', leave=False, unit='file', miniters=1000, mininterval=1)
            
        return self._progress

    @property
    def files_moved(self) -> list[Path]:
        return self._files_moved

    @property
    def count_files_moved(self) -> int:
        return self._count_files_moved

    @property
    def files_deleted(self) -> list[Path]:
        return self._files_deleted

    @property
    def count_files_deleted(self) -> int:
        return self._count_files_deleted

    def append_file(self, file: Path) -> None:
        self._files.append(file)
        self._count_files += 1

    def append_moved_file(self, file: Path) -> None:
        self._files_moved.append(file)
        self._count_files_moved += 1

    def append_deleted_file(self, file: Path) -> None:
        self._files_deleted.append(file)
        self._count_files_deleted += 1

    @lru_cache(maxsize=1024)
    def hash_file(self, filename: str | Path) -> str:
        """
        Calculate the MD5 hash of a file.

        Args:
            filename: The path to the file to hash.

        Returns:
            The MD5 hash of the file.

        Raises:
            OneFileException: If an error occurs while reading the file.
        """
        try:
            hash_md5 = hashlib.md5()
            with open(filename, "rb") as f:
                # Read the file in chunks to handle large files efficiently
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except IOError as e:
            raise OneFileException(f"Error reading file {filename}") from e

    def organize_files(self) -> None:
        """
        Organize files into subdirectories based on their date.

        Returns:
            The number of files moved into new subdirectories.
        """
        # Loop over all files matching the pattern
        logger.info('Organizing %s files', self.file_count)
        if self.dry_run:
            logger.info('Dry run mode enabled; no files will be moved')

        with tqdm(total=self.file_count, desc='Processing files', leave=False, unit='file', miniters=1000, mininterval=1) as self._progress:
            for file in self.files:
                try:
                    self.process_file(file)
                except DuplicationHandledException as e:
                    logger.debug(f"Duplicate file {file} handled")
                except OneFileException as e:
                    logger.error(f"Error processing file {file}: {e}")
                finally:
                    self._update_progress()
                    
        self.report('Finished organizing.')

    def _update_progress(self, increase_progress_bar : int = 1) -> None:
        description = f'Organizing... {self.count_files_moved} files moved'
        if self.count_files_deleted > 0:
            description = f'{description}, {self.count_files_deleted} deleted'
        """
        if self.duplicates_found > 0:
            description = f'{description}, {self.duplicates_found} duplicates'
        """
        if self.directories_created > 0:
            description = f'{description}, {self.directories_created} directories created'
        self.progress.set_description(description)

        if increase_progress_bar > 0:
            self.progress.update(increase_progress_bar)

    def process_file(self, file: Path) -> Path | None:
        """
        Process a single file.

        Args:
            file: The file to process.

        Returns:
            The new path of the file if it was moved, or None if it was deleted.
        """
        filename = file.name

        # Create the subdir
        target_dir = self.find_subdir(filename)

        # Handle potential filename collisions
        target_file = self.handle_collision(file, target_dir / filename)

        return self.move_file(file, target_file)

    def find_subdir(self, filename: str | Path) -> Path:
        """
        Find the subdirectory for a file based on its filename.

        Args:
            filename: The filename to extract the date from.

        Returns:
            The path to the subdirectory.

        Raises:
            OneFileException: If the filename does not match the expected format.
        """
        if isinstance(filename, Path):
            filename = filename.name

        if not (match := self.filename_pattern.match(str(filename))):
            raise OneFileException(f"Invalid filename format: {filename}")

        # Subdir name
        date_part = match.group(1)
        year = date_part[:4]
        month = date_part[4:6]
        dir_name = f"{year}-{month}"

        # Turn into path
        return self.mkdir(self.directory / dir_name) 

    def mkdir(self, directory: Path, message: str | None = "Created directory") -> Path:
        """
        Create a directory if it does not exist.

        Args:
            directory: The directory to create.
            message: An optional message to log.

        Returns:
            The directory path.

        Raises:
            ShouldTerminateException: If an error occurs while creating the directory.
        """
        try:
            if not directory.exists():

                if not self.dry_run:
                    directory.mkdir(exist_ok=True)
                    
                self.directories_created += 1
                if message:
                    self.debug(f"{message}: {directory.relative_to(self.directory)}")
        except Exception as e:
            raise ShouldTerminateException(f'Error creating directory: {directory}') from e

        return directory
        
    def delete_file(self, file: Path, message : str = "Deleted file", use_trash : bool = True) -> bool:
        """
        Delete a file.

        Args:
            file: The file to delete.
            message: An optional message to log.

        Returns:
            True if the file was deleted, False otherwise.

        Raises:
            OneFileException: If an error occurs while deleting the file.
        """
        try:
            if not self.dry_run:
                if use_trash:
                    trash = self.directory / '.trash'
                    trash.mkdir(exist_ok=True)
                    file.rename(trash / file.name)
                else:
                    file.unlink()
                
            self.debug(f"{message}: {file}")
            self.append_deleted_file(file)
        except Exception as e:
            raise OneFileException('Error deleting file') from e

        return not file.exists()

    def move_file(self, source: Path, destination: Path, message : str | None = "Moved file", verify : bool = False) -> Path:
        """
        Move a file to a new location.

        Args:
            source: The source file to move.
            destination: The destination path.
            message: An optional message to log.

        Returns:
            The destination path.

        Raises:
            OneFileException: If an error occurs while moving the file, or hashing either file.
            ShouldTerminateException: If the checksums do not match after moving the file.
        """
        # Destination must be absolute for Path.rename to be consistent
        if not destination.is_absolute():
            logger.debug(f"Making destination path absolute: {destination}")
            destination = self.directory / destination
        
        if not self.dry_run:
            if verify:
                source_hash = self.hash_file(source)
            
            try:
                source.rename(destination)
            except Exception as e:
                raise OneFileException(f'Error moving file {source} to {destination}') from e

            if verify:
                destination_hash = self.hash_file(destination)
                if source_hash != destination_hash:
                    logger.critical(f"Checksum mismatch after moving {source} to {destination}")
                    raise ShouldTerminateException('Checksum mismatch after moving')

        self.append_moved_file(destination)
        if message:
            self.debug(f"{message}: {source} to {destination.relative_to(self.directory)}")
            
        return destination

    def handle_single_conflict(self, source_file : Path, destination: Path) -> Path | Literal[False]:
        """
        Handle a single filename conflict.

        Args:
            source_file: The source file.
            destination: The target file.

        Returns:
            The target file if a viable path was found, or False if the file should be skipped.

        Raises:
            DuplicationHandledException: If the duplicate file was handled.
            OneFileException: If an error occurs while deleting the source file, or hashing either file.
        """
        if not destination.exists():
            # No conflict; return the target file
            return destination
        
        if self.hashes_match(source_file, destination):
            # Files are identical; delete the source file
            self.duplicates_found += 1
            self.delete_file(source_file, "Duplicate file found; deleted")
            raise DuplicationHandledException(f"Duplicate file {source_file} handled")

        return False

    def hashes_match(self, source_file : Path, destination: Path) -> bool:
        """
        Check if the MD5 hashes of two files match.

        Args:
            source_file: The source file.
            destination: The target file.

        Returns:
            True if the hashes match, False otherwise.

        Raises:
            OneFileException: If an error occurs while hashing either file.
        """
        if not destination.exists():
            return False
                
        source_hash = self.hash_file(source_file)
        destination_hash = self.hash_file(destination)

        return source_hash == destination_hash

    def handle_collision(self, file: Path, target_file: Path, max_attempts : int = 1000) -> Path:
        """
        Handle a filename collision by finding a unique filename.

        Args:
            file: The source file.
            target_file: The target file.
            max_attempts: The maximum number of attempts to find a unique filename.

        Returns:
            The new target file path.

        Raises:
            OneFileException: If a unique filename could not be found.
        """
        if (result := self.handle_single_conflict(file, target_file)):
            # A viable path was found
            return result
        
        # Files differ; find a new filename
        base = file.stem  # Filename without extension
        ext = file.suffix  # File extension including the dot
        
        for i in range(max_attempts):
            new_target_file = target_file.parent / f"{base}_{i}{ext}"
            
            if (result := self.handle_single_conflict(file, new_target_file)):
                # A viable path was found
                return result

        raise OneFileException(f"Could not find a unique filename for {file}")

    def report(self, message_prefix : str | None = "Organization Progress:") -> None:
        if self.dry_run:
            message_prefix = f"[DRY RUN] {message_prefix}"
            
        logger.info('%s %s files moved, %s files deleted, %s directories created', 
                    message_prefix or '', 
                    self.count_files_moved, 
                    self.count_files_deleted, 
                    self.directories_created
        )

    def info(self, message : str) -> None:
        """
        Log an INFO message noting that it has been skipped if in dry-run mode.

        This should only be used for logging steps that occur which will be skipped in dry-run mode.

        Args:
            message: The message to log.
        """
        self.notice(message, 'INFO')

    def debug(self, message : str) -> None:
        """
        Log a DEBUG message noting that it has been skipped if in dry-run mode.

        This should only be used for logging steps that occur which will be skipped in dry-run mode.

        Args:
            message: The message to log.
        """
        self.notice(message, 'DEBUG')

    def warning(self, message : str) -> None:
        """
        Log a WARNING message noting that it has been skipped if in dry-run mode.

        This should only be used for logging steps that occur which will be skipped in dry-run mode.

        Args:
            message: The message to log.
        """
        self.notice(message, 'WARNING')

    def error(self, message : str) -> None:
        """
        Log an ERROR message noting that it has been skipped if in dry-run mode.

        This should only be used for logging steps that occur which will be skipped in dry-run mode.

        Args:
            message: The message to log.
        """
        self.notice(message, 'ERROR')

    def critical(self, message : str) -> None:
        """
        Log a CRITICAL message noting that it has been skipped if in dry-run mode.

        This should only be used for logging steps that occur which will be skipped in dry-run mode.

        Args:
            message: The message to log.
        """
        self.notice(message, 'CRITICAL')

    def notice(self, message : str | None, level : str = 'INFO') -> None:
        """
        Log a message with the specified level, noting that it has been skipped if in dry-run mode.

        This should only be used for logging steps that occur which will be skipped in dry-run mode.

        Args:
            message: The message to log.
            level: The logging level to use (default: INFO).
        """
        if not message:
            return
        
        if self.dry_run:
            message = f"[SKIPPED] - {message} - [SKIPPED]"

        match level.lower():
            case 'info':
                logger.info(message)
            case 'debug':
                logger.debug(message)
            case 'warning':
                logger.warning(message)
            case 'error':
                logger.error(message)
            case 'critical':
                logger.critical(message)
            case _:
                logger.debug('Invalid log level: %s', level)
                logger.info(message)

    def __hash__(self) -> int:
        return hash(self.directory)

def main():
    # Customize logger
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Organize PXL_ files into monthly directories.')
    parser.add_argument('-d', '--directory', default='.', help='Directory to organize (default: current directory)')
    parser.add_argument('-p', '--prefix', default='PXL_', help='File prefix to match (default: PXL_)')
    parser.add_argument('-l', '--limit', type=int, default=-1, help='Limit the number of files to process')
    parser.add_argument('-v', '--verbose', action='store_true', help='Increase verbosity')
    parser.add_argument('--dry-run', action='store_true', help='Simulate the file organization without moving files')
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    organizer = FileOrganizer(directory=args.directory, file_prefix=args.prefix, batch_size=args.limit, dry_run=args.dry_run)

    try:
        organizer.organize_files()
    except ShouldTerminateException as e:
        logger.critical(f"Critical error: {e}")
        organizer.report('Before error:')
        sys.exit(1)
    except KeyboardInterrupt:
        logger.warning("Operation interrupted by user")
        organizer.report('Before termination:')
        sys.exit(1)

if __name__ == "__main__":
    main()
