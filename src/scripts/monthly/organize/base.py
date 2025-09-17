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
        'auto' mode (jpg to /mnt/i/Photos/, arw to /mnt/p/, etc) 
            - this may be better solved by changing our drive partitions...

        GPT suggestions:
            Process Pool Executor: For CPU-bound tasks, using ProcessPoolExecutor might be more efficient, but be cautious with the overhead and potential resource contention.
            Asynchronous I/O: If available, use asynchronous I/O operations to prevent blocking.
            Prioritize I/O Operations: On Unix systems, use ionice to set the I/O scheduling class and priority when running the script.
                ionice -c3 python your_script.py
            Lower the CPU priority of your script.
                Nice Command: Lower the CPU priority of your script.
                Cgroups (Linux): Use control groups to limit CPU and memory usage.
            Limit Bandwidth Usage: Use tools or libraries that support bandwidth limiting.
                For example, use pyftpdlib or other libraries that allow setting bandwidth limits.
            Concurrent Downloads: Limit the number of concurrent downloads.
                semaphore = threading.Semaphore(max_concurrent_downloads)
            Monitoring: Implement monitoring to track resource usage and adjust as needed.
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
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
import datetime
from ftplib import FTP
import re
import subprocess
import sys
import os
import time

# Add the root directory of the project to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from pathlib import Path
import logging
import argparse
from typing import Any, Literal, Optional, Protocol
from alive_progress import alive_it, alive_bar
from pydantic import Field, PrivateAttr, field_validator
from dotenv import load_dotenv
from scripts.lib.types import ProgressBar, RESET, RED, GREEN, YELLOW, BLUE, BLUE2, PURPLE, CYAN
from scripts import setup_logging
from scripts.exceptions import ShouldTerminateError
from scripts.lib.file_manager import StrPattern
from scripts.monthly.exceptions import OneFileException, DuplicationHandledException
from scripts.lib.file_manager import FileManager

logger = logging.getLogger(__name__)

filename_date_patterns = [
    re.compile(r'[^_\s-](?P<year>20[012]\d)(?P<month>[01]\d)(?P<day>[0123]\d)[_\s$-]'),
    re.compile(r'[^_\s-](?P<year>20[012]\d)-(?P<month>[01]\d)-(?P<day>[0123]\d)[_\s$-]'),
    re.compile(r'[^_\s-](?P<year>20[012]\d)_(?P<month>[01]\d)_(?P<day>[0123]\d)[_\s$-]'),
]

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
        return r'.*[.](jpe?g|webp|png|heic|dng|arw|nef|psd|tiff?|mp4|mov|avi|mkv|3gp)'

    @classmethod
    def get_default_extensions(cls) -> list[str]:
        # A temporary hack to inject a class attribute into a pydantic model.
        return ['jpg', 'jpeg', 'webp', 'png', 'heic', 'dng', 'arw', 'nef', 'psd', 'tif', 'tiff', 'mp4', 'avi', 'mov', 'mkv', '3gp']

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
    
    def fetch_files_from_ftp(self, host: str, user: str, password: str, remote_dir: str = '/device/DCIM/Camera') -> None:
        """
        Connect to an FTP server and download files from a specified directory.

        Untested!

        Args:
            host: The FTP server hostname
            user: The FTP username
            password: The FTP password
            remote_dir: The remote directory to download files from
        """
        logger.critical('WARNING: This feature is untested.')
        import time
        time.sleep(20)
        try:
            with FTP(host) as ftp:
                ftp.login(user=user, passwd=password)
                logger.info("Connected to FTP server: %s", host)

                ftp.cwd(remote_dir)
                file_list = ftp.nlst()

                # Use a progress bar to show file download progress
                with alive_bar(len(file_list), title="Downloading and Organizing from FTP", unit='files') as progress_bar:
                    for filename in file_list:
                        local_file_path: Path | None = None
                        try:
                            # Get the modification time of the remote file
                            mdtm_response = ftp.sendcmd(f"MDTM {filename}")
                            # The response is in the format '213 YYYYMMDDHHMMSS'
                            mod_time_str = mdtm_response[4:].strip()
                            mod_time = datetime.datetime.strptime(mod_time_str, "%Y%m%d%H%M%S")

                            # Determine the expected destination directory and file path
                            destination_dir = self.create_subdir_from_date(mod_time)
                            destination_path = destination_dir / filename

                            if destination_path.exists():
                                logger.debug("File already exists locally, skipping: %s", filename)
                                continue

                            # Create a temporary file path in a temp directory
                            temp_dir = self.mkdir('.ftp_downloads')
                            local_file_path = temp_dir / filename

                            # Download the file to temporary location
                            with open(local_file_path, 'wb') as local_file:
                                ftp.retrbinary(f"RETR {filename}", local_file.write)
                            logger.debug("Downloaded: %s", filename)

                            # Now process the file as per copy mode
                            self.process_file_threadsafe(local_file_path)

                        except PermissionError as e:
                            logger.warning("Permission error downloading %s: %s", filename, e)
                        except Exception as e:
                            logger.error("Error downloading file %s: %s", filename, e)

                        finally:
                            # Delete the temporary file if it still exists
                            if local_file_path and local_file_path.exists():
                                local_file_path.unlink()
                            progress_bar()

                # Optionally, remove the temp directory if empty
                if temp_dir.exists() and not any(temp_dir.iterdir()):
                    temp_dir.rmdir()

        except Exception as e:
            logger.error("Failed to fetch files from FTP: %s", e)
            raise ShouldTerminateError("FTP fetch failed.") from e

    def organize_files(self, *, cleanup : bool = True) -> None:
        """
        Organize files into subdirectories based on their date.
        """
        if self.check_dry_run(f'organizing files with {self.glob_pattern=} in {self.directory.absolute()}'):
            return

        print(f'{RESET}Organizing files in {BLUE}{self.directory.absolute()}{RESET} to {GREEN}{self.get_target_directory().absolute()}{RESET} with {self.max_threads} threads.')

        with alive_bar(title=f"{BLUE2}Organize{RESET} {self._shortpath(self.directory.absolute())}", unit='files', dual_line=True, unknown='waves') as self._progress_bar:
            self.progress_message('Searching...')

            with ThreadPoolExecutor(max_workers=self.max_threads) as executor:
                futures = []
                for filepath in self.yield_files():
                    submit_result = executor.submit(self.process_file_threadsafe, filepath)
                    futures.append(submit_result)
                    
                    if len(futures) >= self.max_threads * 2:
                        # Wait for the first batch to complete
                        self.handle_futures(futures[:self.max_threads])
                        futures = futures[self.max_threads:]

                if futures:
                    self.handle_futures(futures)

        self.report('Moving files complete')

        # After organization, cleanup empty directories
        if cleanup and not self.copy_mode:
            self.delete_empty_directories()

        logger.info(self.report('Finished organizing.'))

    def handle_futures(self, futures : list[Future]) -> tuple[int, int]:
        """
        Handle the results of a list of futures.

        Args:
            futures: A list of futures to handle.

        Returns:
            tuple[int, int]: A tuple of success and failure counts.
        """
        results : list[bool] = []
        
        for future in futures:
            try:
                result = future.result()
                results.append(result)
            except OneFileException as ofe:
                logger.error("Error organizing file: %s", ofe)
                results.append(False)
            except Exception as e:
                # log and re-raise
                logger.error("Error organizing file: %s", e)
                self.record_error()
                raise

        return (results.count(True), results.count(False))

    def process_file_threadsafe(self, file: Path) -> bool:
        """
        Process a single file and handle exceptions safely.
        """
        # default is failure
        result = False

        try:
            # Allow for retries in case of network issues
            for i in range(10000):
                try:
                    result = self.process_file(file)
                except DuplicationHandledException:
                    logger.debug("Duplicate file handled: %s", file.absolute())
                    result = True
                except OneFileException as e:
                    logger.error("Error processing file (process_file_threadsafe) %s: %s", file.absolute(), e)
                except OSError as ose: 
                    # Check for errno 107 or 112 (host down), and if so, wait and retry
                    if ose.errno in {107, 112}:
                        wait_time = min(60, 5 * i)
                        logger.warning("There may be a network issue. Waiting %ss to retry: %s", wait_time, ose)
                        time.sleep(wait_time)
                        continue
                    raise

                # No retry was requested, so we're finished
                break
        finally:
            self.progress_advance(self._shortpath(file.parent))

        # Sleep for 10ms after processing each file to reduce disk I/O pressure
        time.sleep(0.01)
        return result

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
        MAX_ATTEMPTS = 3
        for i in range(MAX_ATTEMPTS):
            # Handle potential filename collisions. This will throw an exception if the collision cannot be handled.
            destination_file = self.handle_collision(file_path, destination_path)

            try:
                if self.copy_mode:
                    return self.copy_file(file_path, destination_file)
                return self.move_file(file_path, destination_file)
            except FileExistsError as fee:
                logger.warning("File was created by another process. Attempt(%d/%d). destination_path='%s' -> %s", i, MAX_ATTEMPTS, destination_file, fee)
                raise ShouldTerminateError(f"File was created by another process. {destination_file.absolute()=} -> {fee=}")
            except FileNotFoundError as fnf:
                logger.warning("File not found while moving file. Attempt(%d/%d). source_path='%s' -> %s", i, MAX_ATTEMPTS, file_path, fnf)
            except PermissionError as pe:
                logger.warning("Permission error moving file. Attempt(%d/%d). destination_path='%s' -> %s", i, MAX_ATTEMPTS, destination_file, pe)
            except BrokenPipeError as bpe:
                logger.warning("Broken pipe error moving file. Attempt(%d/%d). destination_path='%s' -> %s", i, MAX_ATTEMPTS, destination_file, bpe)
            except subprocess.TimeoutExpired as te:
                logger.warning("Timeout error moving file. Attempt(%d/%d). destination_path='%s' -> %s", i, MAX_ATTEMPTS, destination_file, te)

            # Wait a bit before trying again.
            # -- 1 second, 10 seconds, 20 seconds
            wait_time = max(1, (i - 1) * 10)
            time.sleep(wait_time)

        logger.error("File could not be moved after 3 attempts. destination_path='%s'", destination_file)
        raise OneFileException(f"File could not be moved after 3 attempts. {destination_file.absolute()=}")

    def mkdir(self, directory: Path | str, success_message: str | None = "Created directory", *, parents: bool = True, exist_ok : bool = True) -> Path:
        """
        Create a directory if it does not exist.

        Args:
            directory (str | Path): The directory to create. If a string, it is treated as a relative path to self.directory.
            message (str): An optional message to log.
            parents (bool): If True, create parent directories as needed.
            exist_ok (bool): If True, do not raise an exception if the directory already exists.

        Returns:
            The directory path.

        Raises:
            ShouldTerminateError: If an error occurs while creating the directory.
        """
        if not isinstance(directory, Path):
            directory = Path(directory)
            if not directory.is_absolute():
                directory = self.directory / directory
            
        if directory.exists():
            return directory

        try:
            result = super().mkdir(directory, parents=parents, exist_ok=exist_ok)

            if success_message:
                logger.debug(f"{success_message}: {directory=}")
        except OSError as ose:
            raise ShouldTerminateError(f'Error creating directory: {directory=} -> {ose=}') from ose

        return result

    def delete_file(self, file_path: Path, *, use_trash : bool = True, dont_record : bool = False) -> bool:
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
            raise ShouldTerminateError('Cannot delete files without verifying checksums')

        # This should never happen, but safety check
        if self.copy_mode:
            logger.critical('Cannot delete files in copy mode')
            raise ShouldTerminateError('Cannot delete files in copy mode')

        try:
            result = super().delete_file(file_path, use_trash=use_trash, dont_record=dont_record)
        except OSError as ose:
            logger.error('Unable to delete the file: file_path="%s" -> %s', file_path.absolute(), ose)
            logger.exception(ose)
            raise OneFileException(f'Error deleting file: {ose=}') from ose

        return result

    def match_date_in_filename(self, filename: str) -> tuple[str, str, str] | None:
        """
        Match a date in the filename.

        Args:
            filename: The filename to match.

        Returns:
            The match object if a date was found, None otherwise.
        """
        matches = None
        for pattern in filename_date_patterns:
            if matches := pattern.search(filename):
                continue

        if matches:
            year = matches.group('year')
            month = matches.group('month')
            day = matches.group('day')
            return (year, month, day)
        
        return None
    
    def find_subdir(self, filepath : Path) -> str:
        """
        Find the subdirectory for a file based on its filename.

        Args:
            filepath: The file path to extract the date from.

        Returns:
            The name of the proposed subdirectory.
        """
        year, month, day = self.determine_ymd(filepath)

        # Generate the directory name in the format year/year-month
        dir_name = f"{year}/{year}-{month}-{day}/"
            
        return dir_name

    def determine_ymd(self, filepath : Path) -> tuple[str, str, str]:
        """
        Determine the year, month, and day for a file based on its filename or metadata.

        Args:
            filepath: The file path to extract the date from.

        Returns:
            A tuple of (year, month, day).
        """
        # Prefer a date in the filename, if one exists, over the file metadata
        if (match := self.match_date_in_filename(filepath.name)):
            return match
        
        try:
            # Get the created date from the filepath
            file_stat = filepath.stat()
            created_time = datetime.datetime.fromtimestamp(file_stat.st_ctime)

            # Extract the year and month
            year = created_time.strftime('%Y')
            month = created_time.strftime('%m')
            day = created_time.strftime('%d')

        except OSError as ose:
            logger.error("Error occurred while determining year/month/day: %s", ose)
            raise ValueError(f"Unable to determine year/month/day from: {filepath.absolute()=} -> {ose=}") from ose
        
        return (year, month, day)

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

    def create_subdir_from_date(self, modified_date : datetime.datetime, parent_directory : Path | None = None) -> Path:
        """
        Create a subdirectory based on a date.

        Args:
            date: The date to create the subdirectory for.
            parent_directory: The parent directory to create the subdirectory in, defaults to self.directory.

        Returns:
            The path to the subdirectory.
        """
        parent_directory = parent_directory or self.get_target_directory()

        subdir = modified_date.strftime('%Y/%Y-%m-%d/')

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
        
        if not destination_path.exists():
            if not xmp_destination_path.exists():
                # No conflict; return the destination file
                return destination_path

            # Destination has no conflict, but potential xmp file conflict. Don't handle it.
            return False
        
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
        if (viable_path := self.handle_single_conflict(source_file, target_file)):
            return viable_path

        # Files differ; find a new filename
        base = source_file.stem  # Filename without extension
        ext = source_file.suffix  # File extension including the dot

        new_target_file : Path | None = None
        for i in range(max_attempts):
            new_target_file = target_file.parent / f"{base}_{i}{ext}"

            if (viable_path := self.handle_single_conflict(source_file, new_target_file)):
                return viable_path

        raise OneFileException(f"Could not find a unique filename for {source_file.absolute()=}... last name tried: {new_target_file=}")

    def report(self, message_prefix : str | None = None) -> str:
        """
        Create a report of the file organization.

        Args:
            message_prefix: An optional message to prefix the report with.

        Returns:
            The report string.
        """
        if message_prefix is None:
            message_prefix = self._progress_message
            
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

def autopilot(organizer : FileOrganizer) -> None:
    """
    Automatically organize files based on their extension.
    """
    # Compile glob patterns
    raw_globs = [
        'JAM_*',
        '_JAM*',
        'PXL_*',
        'IMG_*',
        'DSC_*',
    ]
    raw_jpgs = [
        'JAM_*',
        '_JAM*',
        'DSC_*',
    ]
    raw_extensions = [
        'arw',
        'nef',
        'dng',
        'tif',
        'tiff',
        'xmp',
    ]
    photo_globs = [
        'PXL_*',
        'IMG_*',
    ]
    photo_extensions = [
        'jpg',
        'jpeg',
        'mp4',
        'mov',
        'mkv',
        'avi',
    ]
    video_globs = [
        'VID_*',
    ]
    video_extensions = [
        'mp4',
        'mov',
        'mkv',
        'avi',
        '3gp',
    ]
    globs = {
        '*-a7r4-*': '/mnt/p/',
        '*.psd': '/mnt/p/',
        '*-Edit.tif': '/mnt/p/',
    }

    for glob in raw_globs:
        # Photography goes to separate drive due to bracketing
        for ext in raw_extensions:
            globs[f'{glob}.{ext}'] = '/mnt/p/'
        # Videos go to the main media/photos drive
        for ext in video_extensions:
            globs[f'{glob}.{ext}'] = '/mnt/i/Photos/'

    # Bracketed photography jpgs goes to the photography drive, even though they're jpgs
    for glob in raw_jpgs:
        globs[f'{glob}.jpg'] = '/mnt/p/'
        globs[f'{glob}.jpeg'] = '/mnt/p/'

    # Photos go to the main media/photos drive
    for glob in photo_globs:
        for ext in photo_extensions:
            globs[f'{glob}.{ext}'] = '/mnt/i/Photos/'
    for glob in video_globs:
        for ext in video_extensions:
            globs[f'{glob}.{ext}'] = '/mnt/i/Photos/'
    
    # Copy organizer and change the target directory
    for glob, target in globs.items():
        logger.info('Organizing %s to %s', glob, target)
        glob_organizer = FileOrganizer(
            directory       = organizer.directory,
            target_directory= target,
            glob_pattern    = glob,
            batch_size      = organizer.batch_size,
            dry_run         = organizer.dry_run,
            skip_collision  = organizer.skip_collision,
            skip_hash       = organizer.skip_hash,
            copy_mode       = organizer.copy_mode,
            keep_duplicates = organizer.keep_duplicates,
            trash_directory = organizer.trash_directory,
            max_threads     = organizer.max_threads,
        )
        glob_organizer.organize_files(cleanup=False)

    organizer.delete_empty_directories()

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
    max_threads : int
    ftp_host: str
    ftp_user: str
    ftp_pass: str


def main() -> int:
    logger = setup_logging()

    load_dotenv()
    
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
    parser.add_argument('--action', default='organize', choices=['organize', 'cleanup', 'auto'], help='Action to perform')
    parser.add_argument('--trash', default=DEFAULT_TRASH, help='Directory to move deleted files to. Defaults to env variable ORGANIZE_IMAGE_TRASH, which is "{DEFAULT_TRASH}", or ./.trash/')
    parser.add_argument('--skip-collision', action='store_true', help='Skip moving files on collision')
    parser.add_argument('--skip-hash', action='store_true', help='Skip verifying file hashes')
    parser.add_argument('--max-threads', type=int, default=0, help='Maximum number of threads to use')
    parser.add_argument('--dry-run', action='store_true', help='Simulate the file organization without moving files')
    parser.add_argument('--ftp-host', help='FTP host to connect to')
    parser.add_argument('--ftp-user', help='FTP username')
    parser.add_argument('--ftp-pass', help='FTP password')
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
        max_threads     = args.max_threads,
    )

    try:
        match str(args.action).lower():
            case 'organize':
                if args.ftp_host:
                    organizer.fetch_files_from_ftp(args.ftp_host, args.ftp_user, args.ftp_pass)
                else:
                    organizer.organize_files()
            case 'cleanup':
                organizer.delete_empty_directories()
            case 'auto':
                autopilot(organizer)
            case _:
                logger.error("Invalid action: %s", args.action)
                return 1
    except ShouldTerminateError as e:
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
