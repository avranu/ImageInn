"""*********************************************************************************************************************
*                                                                                                                      *
*                                                                                                                      *
    This script organizes files into monthly directories based on the filename. It is useful for dumping
    photos from a phone or camera into a single directory and organizing them later.

    Ideally, it should be run as a cron job to automatically organize files on a regular basis.

    See also upload.py for a script that should run after this one to upload those files to immich.

    This script is referenced in bash_aliases (but not in the github copy of it).

    Example:
        >>> python -m scripts.monthly.organize.base -d /mnt/i/Phone/
        >>> python -m scripts.monthly.organize.base -d /mnt/c/Users/jessa/Pictures -t /mnt/i/Photos
        >>> python /mnt/c/Users/jessa/Work/ImageInn/scripts/monthly/organize/base.py
        # bash_aliases defines 'organize' as an alias for the above command
        >>> organize
        >>> organize -t /mnt/i/Photos

    TODO:
        Check for symlinks
        Cron
*                                                                                                                      *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    METADATA:                                                                                                         *
*                                                                                                                      *
*        File:    organize.py                                                                                          *
*        Project: imageinn                                                                                             *
*        Version: 1.0.0                                                                                                *
*        Created: 2024-09-16                                                                                           *
*        Author:  Jess Mann                                                                                            *
*        Email:   jess.a.mann@gmail.com                                                                                *
*        Copyright (c) 2024 Jess Mann                                                                                  *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    LAST MODIFIED:                                                                                                    *
*                                                                                                                      *
*        2024-10-19     By Jess Mann                                                                                   *
*                                                                                                                      *
*********************************************************************************************************************"""
from __future__ import annotations
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime
import sys
import os

# Add the root directory of the project to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from pathlib import Path
import logging
import argparse
from typing import Any, Iterator, Literal
from tqdm import tqdm
from alive_progress import alive_it, alive_bar
from pydantic import Field, PrivateAttr, field_validator
from scripts import setup_logging
from scripts.exceptions import ShouldTerminateException
from scripts.lib.file_manager import StrPattern
from scripts.monthly.exceptions import OneFileException, DuplicationHandledException
from scripts.lib.file_manager import FileManager

logger = logging.getLogger(__name__)

class FileOrganizer(FileManager):
    """
    Organize files into monthly directories based on the filename.

    - Files are moved to a directory named 'YYYY/YYYY-MM-DD' under the specified directory.
    - If a file with the same name already exists in the target directory, and hashes match, it is deleted.
        - If the hash does not match, a unique filename is generated.
    """
    batch_size: int = -1
    skip_collision: bool = False
    skip_hash : bool = False
    target_directory : Path | None = None

    @field_validator('target_directory', mode='before')
    def validate_target_directory(cls, value: Any) -> Path | None:
        if value is None:
            return None

        dir_path = Path(value)
        if not dir_path.exists():
            logger.debug('target_directory does not exist. Creating it: "%s"', dir_path)
            dir_path.mkdir(exist_ok=True, parents=True)
            
        return dir_path

    @property
    def files_duplicated(self) -> int:
        return self.get_stat('duplicate_file')

    @classmethod
    def get_default_filename_pattern(cls) -> StrPattern:
        # A temporary hack to inject a class attribute into a pydantic model.
        return r'.*[.](jpg|jpeg|webp|png|dng|arw|nef|psd|tif|tiff|mp4)'

    @classmethod
    def get_default_glob_pattern(cls) -> str:
        # A temporary hack to inject a class attribute into a pydantic model.
        return '*.{jpg,jpeg,webp,png,dng,arw,nef,psd,tif,tiff,mp4}'

    def record_duplicate_file(self, count : int = 1) -> None:
        self.record_stat('duplicate_file', count)

    def get_target_directory(self) -> Path:
        if not self.target_directory:
            return self.directory
        return self.target_directory

    def hash_file(self, filename: str | Path, partial : bool = False, hashing_algorithm : str = 'xxhash') -> str:
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
            return super().hash_file(filename, partial, hashing_algorithm)
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
        """
        if self.check_dry_run(f'organizing files with {self.glob_pattern=} in {self.directory.absolute()}'):
            return

        # Gather subdirectories in the source directory
        directories = self.yield_directories(self.directory)
        # Start counting directories asynchronously
        #total_count_task = asyncio.create_task(self.count_files(self.directory))

        with alive_bar(title="Organizing Files", unit='files', unknown='waves') as progress_bar:
            progress_bar.text(f'Searching... - {self.report()}')
            total_was_set = False
            
            for subdir in directories:
                # Check if the total dir count is available
                """
                if not total_was_set and total_count_task.done():
                    logger.critical('Total directories: %d', total_count_task.result())
                    progress_bar.total = total_count_task.result()
                    progress_bar.unknown = False
                    total_was_set = True
                """
                    
                try:
                    # Gather all files to process
                    files_to_process = self.yield_files(subdir, recursive=False)

                    with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
                        futures = []
                        for file in files_to_process:
                            futures.append(executor.submit(self.process_file_threadsafe, file))

                        if (count := len(futures)) < 1:
                            # We will attempt to delete the dir in `finally` below
                            continue

                        logger.debug('%d files found in %s', count, subdir)

                        for future in as_completed(futures):
                            try:
                                future.result()
                            except OneFileException as ofe:
                                logger.error(f"Error organizing file: {ofe}")
                            except Exception as e:
                                # log and re-raise
                                logger.error(f"Error organizing file: {e}")
                                self.record_error()
                                raise
                            finally:
                                progress_bar.text(f'/{str(subdir)[-10:]}/ - {self.report()}')
                                progress_bar()
                finally:
                    # Remove the directory if it is now empty
                    self.delete_directory_if_empty(subdir)

        logger.info('Moving files complete. Total: %d moved, %d skipped, %s deleted',
                    self.files_moved,
                    self.files_skipped,
                    self.files_deleted,
        )

        # After organization, cleanup empty directories
        self.delete_empty_directories()
        
        # Ensure the counting task is complete
        if not total_count_task.done():
            # Discard the task
            total_count_task.cancel()

        logger.info('Finished organizing. %s', self.report())
        return

    def process_file_threadsafe(self, file: Path) -> bool:
        """
        Process a single file and handle exceptions safely.
        """
        try:
            if self.process_file(file):
                return True
        except DuplicationHandledException:
            logger.debug(f"Duplicate file {file} handled")
            return True
        except OneFileException as e:
            logger.error(f"Error processing file {file}: {e}")

        return False


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
        target_dir = self.create_subdir(file_path)
        destination_path = target_dir / filename

        if file_path == destination_path:
            self.record_skip_file()
            logger.debug(f"Skipping file {file_path} as it is already in the correct directory")
            return None

        # Handle potential filename collisions. This will throw an exception if the collision cannot be handled.
        target_file = self.handle_collision(file_path, destination_path)

        # TODO: Check file and target file are same drive. If not, verify=True
        return self.move_file(file_path, target_file)

    def mkdir(self, directory: Path, success_message: str | None = "Created directory", *, parents: bool = True, exist_ok : bool = True) -> Path:
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
            result = super().mkdir(directory, parents=parents, exist_ok=exist_ok)

            if success_message:
                logger.debug(f"{success_message}: {directory}")
        except OSError as ose:
            raise ShouldTerminateException(f'Error creating directory: {directory} -> {ose}') from ose

        return result

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
        if self.skip_hash:
            logger.critical('Cannot delete files without verifying checksums')
            raise OneFileException('Cannot delete files without verifying checksums')

        try:
            result = super().delete_file(file_path, use_trash)
        except OSError as ose:
            raise OneFileException(f'Error deleting file: {ose}') from ose

        return result

    def move_file(self, source: Path, destination: Path, verify : bool = False) -> Path:
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

        return destination

    def find_subdir(self, filepath : Path) -> str:
        """
        Find the subdirectory for a file based on its filename.

        Args:
            filepath: The file path to extract the date from.

        Returns:
            The name of the proposed subdirectory.
        """
        try:
            # Get the created date from the filepath
            file_stat = filepath.stat()
            created_time = datetime.datetime.fromtimestamp(file_stat.st_ctime)

            # Extract the year and month
            year = created_time.strftime('%Y')
            month = created_time.strftime('%m')
            day = created_time.strftime('%d')

            # Generate the directory name in the format year/year-month
            dir_name = f"{year}/{year}-{month}-{day}/"

        except OSError as ose:
            logger.error(f"Error occurred while finding subdirectory: {ose}")
            raise ValueError(f"Unable to determine a subdir from: {filepath} -> {ose}") from ose

        return dir_name

    def create_subdir(self, filepath : Path, parent_directory : Path | None = None) -> Path:
        """
        Create a subdirectory for a file based on its filename.

        Args:
            filepath: The file path to extract the date from.
            parent_directory: The parent directory to create the subdirectory in, defaults to self.directory.

        Returns:
            The path to the subdirectory.
        """
        parent_directory = parent_directory or self.get_target_directory()

        subdir = self.find_subdir(filepath)

        return self.mkdir(parent_directory / subdir)

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
            self.record_skip_file()
            logger.debug(f"Skipping file {source_file} due to collision with {destination}")
            raise DuplicationHandledException(f"Duplicate file {source_file} handled")

        if self.files_match(source_file, destination, self.skip_hash):
            # Files are identical; delete the source file
            self.record_duplicate_file()
            if not self.skip_hash:
                logger.debug('Duplicate file found: %s', source_file)
                self.delete_file(source_file)
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

    def report(self) -> str:
        """
        Create a report of the file organization.

        Returns:
            The report string.
        """
        # Files
        buffer = f'{self.files_moved} files moved'
        if self.files_deleted > 0:
            buffer = f'{buffer}, {self.files_deleted} deleted'
        if self.files_skipped > 0:
            buffer = f'{buffer}, {self.files_skipped} skipped'

        # Directories
        buffer = f'{buffer}, {self.directories_created} directories created'
        if self.directories_deleted > 0:
            buffer = f'{buffer}, {self.directories_deleted} removed'

        # Errors
        if self.errors > 0:
            buffer = f'{buffer}, {self.errors} errors'
        return buffer

def main():
    logger = setup_logging()

    # Set up argument parser
    parser = argparse.ArgumentParser(description='Organize files into monthly directories.')
    parser.add_argument('-d', '--directory', default='.', help='Directory to organize (default: current directory)')
    parser.add_argument('-t', '--target', default=None, help='Target directory to move files to')
    parser.add_argument('-g', '--glob-pattern', default=None, help='Glob pattern to use when searching for files.')
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
        target_directory= args.target,
        glob_pattern    = args.glob_pattern,
        batch_size      = args.limit,
        dry_run         = args.dry_run,
        skip_collision  = args.skip_collision,
        skip_hash       = args.skip_hash
    )

    try:
        organizer.organize_files()
    except ShouldTerminateException as e:
        logger.critical(f"Critical error: {e}")
        logger.info('Before error: %s', organizer.report())
        sys.exit(1)
    except KeyboardInterrupt:
        logger.warning("Operation interrupted by user")
        logger.info('Before termination: %s', organizer.report())
        sys.exit(1)
        
    return

if __name__ == "__main__":
    main()
