#!/usr/bin/env python3
"""
This script organizes files into monthly directories based on the filename. It is useful for dumping 
photos from a phone or camera into a single directory and organizing them later.

Ideally, it should be run as a cron job to automatically organize files on a regular basis.

See also upload.py for a script that should run after this one to upload those files to immich.

This script is referenced in bash_aliases (but not in the github copy of it).

Version 1.0
Date: 2024-09-20
Status: Working

Example:
    >>> python -m scripts.monthly.organize -d /mnt/i/Phone/
    >>> python /mnt/c/Users/jessa/Work/ImageInn/scripts/monthly/organize.py
    # bash_aliases defines 'organize' as an alias for the above command
    >>> organize

TODO:
    Check for symlinks
    Cron
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
from typing import Iterator, Literal
from tqdm import tqdm
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator
from scripts import setup_logging
from scripts.exceptions import ShouldTerminateException
from scripts.monthly.exceptions import OneFileException, DuplicationHandledException
from scripts.lib.file_manager import FileManager

logger = setup_logging()

class FileOrganizer(FileManager):
    """
    Organize files into monthly directories based on the filename.

    - Filenames are expected to start with 'PXL_' followed by an 8-digit date in the format 'YYYYMMDD'.
    - Files are moved to a directory named 'YYYY-MM' under the specified directory.
    - If a file with the same name already exists in the target directory, a unique filename is generated.
    """
    batch_size: int = -1
    skip_collision: bool = False
    skip_hash : bool = False

    duplicates_found: int = 0
    directories_created: int = 0

    # Private attributes
    _progress: tqdm | None = PrivateAttr(default=None)
    _filename_pattern : re.Pattern | None = PrivateAttr(default=None)

    @property
    def progress(self) -> tqdm:
        if self._progress is None:
            self._progress = tqdm(desc='Processing files', leave=False, unit='files', miniters=1000, mininterval=1)
            
        return self._progress

    @property
    def count_files_moved(self) -> int:
        return len(self._files_moved)

    @property
    def count_files_copied(self) -> int:
        return len(self._files_copied)

    @property
    def count_files_deleted(self) -> int:
        return len(self._files_deleted)

    @property
    def count_files_skipped(self) -> int:
        return len(self._files_skipped)

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
            return super().hash_file(filename)
        except IOError as e:
            raise OneFileException(f"Error reading file {filename}") from e


    def files_match(self, source_file : Path, destination_path: Path, skip_hash : bool = False) -> bool:
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
        skip_hash = skip_hash or self.skip_hash

        return super().files_match(source_file, destination_path, skip_hash)

    def organize_files(self) -> None:
        """
        Organize files into subdirectories based on their date.

        Returns:
            The number of files moved into new subdirectories.
        """
        # Loop over all files matching the pattern
        if self.dry_run:
            logger.info('Dry run mode enabled; no files will be moved')

        with tqdm(desc='Processing files', leave=False, unit='files', miniters=1000, mininterval=1) as self._progress:
            for file in self.get_files():
                try:
                    if not file.is_file():
                        continue
                    
                    self.process_file(file)
                except DuplicationHandledException as e:
                    logger.debug(f"Duplicate file {file} handled")
                except OneFileException as e:
                    logger.error(f"Error processing file {file}: {e}")
                finally:
                    self._update_progress()
                    
        self.report('Finished organizing.')
        
    def process_file(self, file_path: Path) -> Path | None:
        """
        Process a single file.

        Args:
            file_path: The file to process.

        Returns:
            The new path of the file if it was moved, or None if it was deleted.
        """
        filename = file_path.name

        # Create the subdir
        target_dir = self.create_subdir(filename)

        # Handle potential filename collisions
        target_file = self.handle_collision(file_path, target_dir / filename)

        # TODO: Check file and target file are same drive. If not, verify=True
        return self.move_file(file_path, target_file)

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
        if self.count_files_skipped > 0:
            description = f'{description}, {self.count_files_skipped} skipped'
            
        self.progress.set_description(description)

        if increase_progress_bar > 0:
            self.progress.update(increase_progress_bar)

    def create_subdir(self, filename: str | Path, parent_directory : Path | None = None) -> Path:
        """
        Find the subdirectory for a file based on its filename.

        Args:
            filename: The filename to extract the date from.

        Returns:
            The path to the subdirectory.

        Raises:
            OneFileException: If the filename does not match the expected format.
        """
        try:
            return super().create_subdir(filename, parent_directory)
        except ValueError as e:
            raise OneFileException(f"Unable to create subdir for: {filename}") from e

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
        if directory.exists():
            return directory
        
        try:
            result = super().mkdir(directory)
                
            self.directories_created += 1
            if message:
                logger.debug(f"{message}: {directory.relative_to(self.directory)}")
        except Exception as e:
            raise ShouldTerminateException(f'Error creating directory: {directory}') from e
        
        return result
        
    def delete_file(self, file_path: Path, message : str = "Deleted file", use_trash : bool = True) -> bool:
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
        if self.skip_hash:
            logger.critical('Cannot delete files without verifying checksums')
            raise OneFileException('Cannot delete files without verifying checksums')
        
        try:
            result = super().delete_file(file_path, use_trash)    
            logger.debug(f"{message}: {file_path}")
        except Exception as e:
            raise OneFileException('Error deleting file') from e

        return result

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
        destination = super().move_file(source, destination, verify=verify)

        if message:
            logger.debug(f"{message}: {source} to {destination.relative_to(self.directory)}")
            
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

        if self.skip_collision:
            # Skip moving files on collision
            self.append_skipped_file(source_file)
            logger.debug(f"Skipping file {source_file} due to collision with {destination}")
            raise DuplicationHandledException(f"Duplicate file {source_file} handled")
        
        if self.files_match(source_file, destination):
            # Files are identical; delete the source file
            self.duplicates_found += 1
            if not self.skip_hash:
                self.delete_file(source_file, "Duplicate file found; deleted")
            raise DuplicationHandledException(f"Duplicate file {source_file} handled")

        return False

    def handle_collision(self, source_file: Path, target_file: Path, max_attempts : int = 1000) -> Path:
        """
        Handle a filename collision by finding a unique filename.

        Args:
            source_file: The source file.
            target_file: The target file.
            max_attempts: The maximum number of attempts to find a unique filename.

        Returns:
            The new target file path.

        Raises:
            OneFileException: If a unique filename could not be found.
        """
        if (result := self.handle_single_conflict(source_file, target_file)):
            # A viable path was found
            return result
        
        # Files differ; find a new filename
        base = source_file.stem  # Filename without extension
        ext = source_file.suffix  # File extension including the dot
        
        for i in range(max_attempts):
            new_target_file = target_file.parent / f"{base}_{i}{ext}"
            
            if (result := self.handle_single_conflict(source_file, new_target_file)):
                # A viable path was found
                return result

        raise OneFileException(f"Could not find a unique filename for {source_file}")

    def report(self, message_prefix : str | None = "Organization Progress:") -> None:
        if self.dry_run:
            message_prefix = f"[DRY RUN] {message_prefix}"
            
        logger.info('%s %s files moved, %s files deleted, %s files skipped, %s directories created', 
                    message_prefix or '', 
                    self.count_files_moved, 
                    self.count_files_deleted, 
                    self.count_files_skipped,
                    self.directories_created
        )

def main():    
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Organize PXL_ files into monthly directories.')
    parser.add_argument('-d', '--directory', default='.', help='Directory to organize (default: current directory)')
    parser.add_argument('-p', '--prefix', default='PXL_', help='File prefix to match (default: PXL_)')
    parser.add_argument('-l', '--limit', type=int, default=-1, help='Limit the number of files to process')
    parser.add_argument('-v', '--verbose', action='store_true', help='Increase verbosity')
    parser.add_argument('--skip-collision', action='store_true', help='Skip moving files on collision')
    parser.add_argument('--skip-hash', action='store_true', help='Skip verifying file hashes')
    parser.add_argument('--dry-run', action='store_true', help='Simulate the file organization without moving files')
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    organizer = FileOrganizer(
        directory       = args.directory, 
        file_prefix     = args.prefix, 
        batch_size      = args.limit, 
        dry_run         = args.dry_run, 
        skip_collision  = args.skip_collision,
        skip_hash       = args.skip_hash
    )

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
