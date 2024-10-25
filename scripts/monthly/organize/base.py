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
*        Version: 0.1.0                                                                                                *
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
import subprocess
import sys
import os

# Add the root directory of the project to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from pathlib import Path
import logging
import argparse
from typing import Any, Callable, Iterator, Literal, Optional, Protocol
from alive_progress import alive_it, alive_bar
from pydantic import Field, PrivateAttr, field_validator
from scripts.lib.types import ProgressBar, RED, GREEN, YELLOW, BLUE, PURPLE, RESET
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
    - If a file with the same name already exists in the target directory:
        - if hashes match, it is deleted.
        - if hashes do not match, a unique filename is generated.
    """
    batch_size: int = -1
    skip_collision: bool = False
    skip_hash : bool = False
    target_directory : Path | None = None
    copy_mode : bool = False
    keep_duplicates : bool = False

    _progress_bar : ProgressBar | None = PrivateAttr(default=None)

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
    def progress_bar(self) -> ProgressBar:
        if not self._progress_bar:
            self._progress_bar = alive_bar(title=f"{RESET}Organizing Files", unit='files', unknown='waves')
        return self._progress_bar

    @property
    def files_duplicated(self) -> int:
        return self.get_stat('duplicate_file')

    @classmethod
    def get_default_filename_pattern(cls) -> StrPattern:
        # A temporary hack to inject a class attribute into a pydantic model.
        return r'.*[.](jpg|jpeg|webp|png|heic|dng|arw|nef|psd|tif|tiff|mp4)'

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
            ValueError: If the source and destination files are the same.
        """
        skip_hash = skip_hash or self.skip_hash

        return super().files_match(source_file, destination_path, skip_hash)

    def organize_files(self) -> None:
        """
        Organize files into subdirectories based on their date.
        """
        if self.check_dry_run(f'organizing files with {self.glob_pattern=} in {self.directory.absolute()}'):
            return

        print(f'{RESET}Organizing files in {BLUE}{self.directory.absolute()}{RESET} to {GREEN}{self.get_target_directory().absolute()}{RESET}')

        # Gather subdirectories in the source directory
        directories = self.yield_directories(self.directory)
        # Start counting directories asynchronously
        #total_count_task = asyncio.create_task(self.count_files(self.directory))

        with alive_bar(title=f"{RESET}Organize {self._shortpath(self.directory.absolute())}", unit='files', dual_line=True, unknown='waves') as self._progress_bar:
            self.progress_bar.text(f'{self.report('Searching...')}')
            #total_was_set = False
            consecutive_ofe_errors : int = 0 
            
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

                        logger.debug('%d files found in /%s/', count, subdir)

                        for future in as_completed(futures):
                            try:
                                future.result()
                                consecutive_ofe_errors = 0
                            except OneFileException as ofe:
                                consecutive_ofe_errors += 1
                                logger.error("Error organizing file: %s", ofe)
                            except Exception as e:
                                # log and re-raise
                                logger.error("Error organizing file: %s", e)
                                self.record_error()
                                raise

                            if consecutive_ofe_errors > 5:
                                logger.error("Too many consecutive errors in %s. Skipping the rest of the files.", subdir)
                                raise ShouldTerminateException(f'Too many consecutive errors in {subdir=}. Skipping the rest of the files.')
                finally:
                    # Remove the directory if it is now empty
                    if not self.copy_mode:
                        self.delete_directory_if_empty(subdir)

        logger.info('Moving files complete. Total: %d moved, %d skipped, %s deleted. Cleaning up...',
                    self.files_moved,
                    self.files_skipped,
                    self.files_deleted,
        )

        # After organization, cleanup empty directories
        if not self.copy_mode:
            result = self.delete_empty_directories()
            if result and self.directory.samefile('.'):
                # The dir no longer exists. run "cd .."
                os.chdir('..')

        # Ensure the counting task is complete
        """
        if not total_count_task.done():
            # Discard the task
            total_count_task.cancel()
        """

        logger.info(self.report('Finished organizing.'))
        return

    def process_file_threadsafe(self, file: Path) -> bool:
        """
        Process a single file and handle exceptions safely.
        """
        try:
            if self.process_file(file):
                return True
        except DuplicationHandledException:
            logger.debug(f"Duplicate file {file.absolute()=} handled")
            return True
        except OneFileException as e:
            logger.error("Error processing file (process_file_threadsafe) %s: %s", file.absolute(), e)
        finally:
            subdir = file.parent
            self.progress_report(self._shortpath(subdir))

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
        destination_dir = self.create_subdir(file_path)
        destination_path = destination_dir / filename

        if destination_path.exists() and file_path.samefile(destination_path):
            self.record_skip_file()
            logger.debug(f"Skipping file {file_path.absolute()=} as it is already in the correct directory")
            return None

        # Loop in case another process hijacks our destination path
        for i in range(3):
            # Handle potential filename collisions. This will throw an exception if the collision cannot be handled.
            destination_file = self.handle_collision(file_path, destination_path)

            try:
                if self.copy_mode:
                    return self.copy_file(file_path, destination_file)
                return self.move_file(file_path, destination_file)
            except FileExistsError as fee:
                logger.warning("File was created by another process. Attempt(%d/3). destination_path='%s' -> %s", i, destination_file, fee)
                raise ShouldTerminateException(f"File was created by another process. {destination_file.absolute()=} -> {fee=}")
            except PermissionError as pe:
                logger.warning("Permission error moving file. Attempt(%d/3). destination_path='%s' -> %s", destination_file, pe)
            except subprocess.TimeoutExpired as te:
                logger.warning("Timeout error moving file. Attempt(%d/3). destination_path='%s' -> %s", destination_file, te)

        logger.error("File could not be moved after 3 attempts. destination_path='%s'", destination_file)
        raise OneFileException(f"File could not be moved after 3 attempts. {destination_file.absolute()=}")

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
                logger.debug(f"{success_message}: {directory=}")
        except OSError as ose:
            raise ShouldTerminateException(f'Error creating directory: {directory=} -> {ose=}') from ose

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
        # This should never happen, but safety check
        if self.skip_hash:
            logger.critical('Cannot delete files without verifying checksums')
            raise ShouldTerminateException('Cannot delete files without verifying checksums')

        # This should never happen, but safety check
        if self.copy_mode:
            logger.critical('Cannot delete files in copy mode')
            raise ShouldTerminateException('Cannot delete files in copy mode')

        try:
            result = super().delete_file(file_path, use_trash)
        except OSError as ose:
            logger.error('Unable to delete the file: file_path="%s" -> %s', file_path.absolute(), ose)
            logger.exception(ose)
            raise OneFileException(f'Error deleting file: {ose=}') from ose

        return result
    
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
            logger.error("Error occurred while finding subdirectory: %s", ose)
            raise ValueError(f"Unable to determine a subdir from: {filepath.absolute()=} -> {ose=}") from ose

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

    def handle_single_conflict(self, source_path : Path, destination_path: Path) -> Path | Literal[False]:
        """
        Handle a single filename conflict.

        Args:
            source_path: The source file.
            destination_path: The target file.

        Returns:
            The target file if a viable path was found, or False if the file should be skipped.

        Raises:
            DuplicationHandledException: If the duplicate file was handled.
            OneFileException: If an error occurs while deleting the source file, or hashing either file.
        """
        # XMP files go with their respective RAW files
        xmp_source_path = source_path.with_suffix('.xmp')
        xmp_destination_path = destination_path.with_suffix('.xmp')
        
        if not destination_path.exists() and not xmp_destination_path.exists():
            # No conflict; return the destination file
            return destination_path
        
        if self.skip_collision:
            # Skip moving files on collision
            self.record_skip_file()
            logger.debug(f"Skipping file {source_path.absolute()=} due to collision with {destination_path.absolute()=}")
            raise DuplicationHandledException(f"Duplicate file {source_path.absolute()=} skipped")

        if self.files_match(source_path, destination_path, skip_hash=self.skip_hash):
            logger.debug('Duplicate file found: %s', source_path)
            self.record_duplicate_file()
            
            if not self.keep_duplicates and not self.copy_mode and not self.skip_hash:
                # Files are identical; delete the source file
                self.delete_file(source_path)
                if xmp_source_path.exists(follow_symlinks=False):
                    self.delete_file(xmp_source_path)
                raise DuplicationHandledException(f"Duplicate file {source_path.absolute()=} deleted")
                
            raise DuplicationHandledException(f"Duplicate file {source_path.absolute()=} skipped")

        # Files differ; the conflict was not handled.
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

        new_target_file : Path | None = None
        for i in range(max_attempts):
            new_target_file = target_file.parent / f"{base}_{i}{ext}"

            if (result := self.handle_single_conflict(source_file, new_target_file)):
                # A viable path was found
                return result

        raise OneFileException(f"Could not find a unique filename for {source_file.absolute()=}... last name tried: {new_target_file=}")

    def report(self, message_prefix : str | None = None) -> str:
        """
        Create a report of the file organization.

        Args:
            message_prefix: An optional message to prefix the report with.

        Returns:
            The report string.
        """
        buffer = []

        if message_prefix:
            buffer.append(f'{BLUE}{message_prefix[-30:]:31s}{RESET}')
        
        # Files
        file_buffer = []
        if self.files_moved > 0:
            file_buffer.append(f'{self.files_moved} moved')
        if self.files_copied > 0:
            file_buffer.append(f'{self.files_copied} copied')
        if self.files_deleted > 0:
            file_buffer.append(f'{self.files_deleted} deleted')
        if self.files_skipped > 0:
            file_buffer.append(f'{self.files_skipped} skipped')
            
        # Directories
        directory_buffer = []
        if self.directories_created > 0:
            directory_buffer.append(f'{self.directories_created} created')
        if self.directories_deleted > 0:
            directory_buffer.append(f'{self.directories_deleted} removed')


        if file_buffer:
            files_str = f"{PURPLE}Files [{', '.join(file_buffer)}]{RESET}"
            buffer.append(f"{files_str:50s}")
        if directory_buffer:
            directory_str = f"{YELLOW}Directories [{', '.join(directory_buffer)}]{RESET}"
            buffer.append(f"{directory_str:50s}")

        # Errors
        if self.errors > 0:
            error_str = f"{RED}Errors: {self.errors}{RESET}"
            buffer.append(f'{error_str:12s}')
            
        return f"{RESET}{' '.join(buffer) or 'No files changed'}{RESET}"

    def progress_report(self, message_prefix : str | None = None):
        """
        Report progress to the progress bar.

        Args:
            message_prefix: An optional message to prefix the report with.
        """
        self.progress_bar.text(self.report(message_prefix))
        self.progress_bar()

class ArgsNamespace(argparse.Namespace):
    directory: str
    target: str
    glob_pattern: Optional[str]
    copy: bool
    keep_duplicates: bool
    limit: int
    verbose: bool
    action: str
    trash: str
    skip_collision: bool
    skip_hash: bool
    dry_run: bool


def main() -> int:
    logger = setup_logging()

    DEFAULT_TARGET = os.getenv('IMAGEINN_ORGANIZE_TARGET', '.')
    DEFAULT_TRASH = os.getenv('IMAGEINN_ORGANIZE_TRASH', None)

    # Set up argument parser
    parser = argparse.ArgumentParser(description='Organize files into monthly directories.')
    parser.add_argument('-d', '--directory', default='.', help='Directory to organize (default: current directory)')
    parser.add_argument('-t', '--target', default=DEFAULT_TARGET, help=f'Target directory to move files to (defaults to env var IMAGEINN_ORGANIZE_TARGET, which is "{DEFAULT_TARGET}")')
    parser.add_argument('-g', '--glob-pattern', default=None, help='Glob pattern to use when searching for files.')
    parser.add_argument('-c', '--copy', action='store_true', help='Copy files instead of moving them')
    parser.add_argument('-k', '--keep-duplicates', action='store_true', help="Keep duplicate files in the source directory (don't delete)")
    parser.add_argument('-l', '--limit', type=int, default=-1, help='Limit the number of files to process')
    parser.add_argument('-v', '--verbose', action='store_true', help='Increase verbosity')
    parser.add_argument('--action', default='organize', choices=['organize', 'cleanup'], help='Action to perform')
    parser.add_argument('--trash', default=DEFAULT_TRASH, help='Directory to move deleted files to. Defaults to env variable ORGANIZE_IMAGE_TRASH, which is "{DEFAULT_TRASH}", or ./.trash/')
    parser.add_argument('--skip-collision', action='store_true', help='Skip moving files on collision')
    parser.add_argument('--skip-hash', action='store_true', help='Skip verifying file hashes')
    parser.add_argument('--dry-run', action='store_true', help='Simulate the file organization without moving files')
    args = parser.parse_args(namespace=ArgsNamespace())

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    organizer = FileOrganizer(
        directory       = args.directory,
        target_directory= args.target,
        glob_pattern    = args.glob_pattern,
        batch_size      = args.limit,
        dry_run         = args.dry_run,
        skip_collision  = args.skip_collision,
        skip_hash       = args.skip_hash,
        copy_mode       = args.copy,
        keep_duplicates = args.keep_duplicates,
        trash_directory = args.trash,
    )

    try:
        match str(args.action).lower():
            case 'organize':
                organizer.organize_files()
            case 'cleanup':
                organizer.delete_empty_directories()
            case _:
                logger.error("Invalid action: %s", args.action)
                return 1
    except ShouldTerminateException as e:
        logger.critical("Critical error: %s", e)
        logger.info('Before error: %s', organizer.report())
        return 1
    except KeyboardInterrupt:
        logger.warning("Operation interrupted by user")
        logger.info('Before termination: %s', organizer.report())
        return 1
    except Exception as e:
        logger.error('Uncaught error: %s', e)
        logger.info(organizer.report('Before error'))
        raise
        
    return 0

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
