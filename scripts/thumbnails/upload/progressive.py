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
*        Copyright (c) 2024 Jess Mann                                                                                  *
*        >>> python progressive.py /mnt/i/Phone
*        # bash_aliases defines `upload` to run this script for the current dir
*        >>> upload
*        >>> upload -e jpg /mnt/d/Photos
*        >>> upload -t pixel /mnt/i/Phone
*
*    TODO:
*        - When supplying arguments to the script (such as --allow-extension), the script will skip some files, but still save
*        last_processed_time and version. Therefore, a subsequent run without those args will still skip some directories.
*        - Don't skip current directory
*        - "dont-skip" argument, or "fast".
*                                                                                                                      *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    METADATA:                                                                                                         *
*                                                                                                                      *
*        File:    progressive.py                                                                                       *
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
import logging
import os
import sys
import threading
import time
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Protocol
from dotenv import load_dotenv
import argparse
from pydantic import PrivateAttr
from tqdm import tqdm
from alive_progress import alive_it, alive_bar

from scripts.lib.db.images import ImagesDatabase
from scripts.thumbnails.upload.meta import DEFAULT_DB_PATH

# Add the root directory of the project to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from scripts import setup_logging
from scripts.lib.types import ProgressBar, RED, CYAN, CYAN2, YELLOW, YELLOW2, BLUE, PURPLE, RESET
from scripts.exceptions import AppException
from scripts.thumbnails.upload.exceptions import AuthenticationError, ConfigurationError
from scripts.thumbnails.upload.interface import ImmichInterface
from scripts.thumbnails.upload.status import Status, UploadStatus
from scripts.thumbnails.upload.template import PixelFiles

logger = setup_logging()

class ImmichProgressiveUploader(ImmichInterface):

    _progress_bar : ProgressBar | None = PrivateAttr(default=None)
    
    @property
    def progress_bar(self) -> ProgressBar:
        if not self._progress_bar:
            self._progress_bar = alive_bar(title="Organizing Files", unit='files', unknown='waves')
        return self._progress_bar
    
    @property
    def files_uploaded(self) -> int:
        return self.get_stat('uploaded_file')

    @property
    def files_duplicated(self) -> int:
        return self.get_stat('duplicate_file')

    def record_upload_file(self, count : int = 1) -> None:
        self.record_stat('uploaded_file', count)

    def record_duplicate_file(self, count : int = 1) -> None:
        self.record_stat('duplicate_file', count)

    def _upload_file(self, image_path: Path, status: Status | None = None, retries: int = 3) -> UploadStatus:
        """
        Upload a file to Immich.

        Args:
            image_path (Path): The file to upload.
            status (Status): An instance of the Status class.

        Returns:
            UploadStatus: The status of the upload operation.
        """
        if self.should_ignore_file(image_path, status):
            logger.debug('Ignoring %s', image_path)
            return UploadStatus.SKIPPED

        if self.check_dry_run('running immich upload'):
            return UploadStatus.UPLOADED

        command = ["immich", "upload", image_path.as_posix()]
        if self.album:
            command.extend(['-A', self.album])
        
        attempt = 0
        while attempt <= retries:
            try:
                result = subprocess.run(
                    command,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=120,
                    text=True
                )
                output = result.stdout + result.stderr

                # Analyze the output
                if "All assets were already uploaded" in output:
                    logger.debug("%s already uploaded.", image_path)
                    return UploadStatus.DUPLICATE
                if "Unsupported file type" in output:
                    logger.debug("Unsupported file type: %s", image_path)
                    return UploadStatus.ERROR
                if "Successfully uploaded" in output:
                    logger.debug("Uploaded %s successfully.", image_path)
                    return UploadStatus.UPLOADED

                logger.info('Unknown output: %s', output)
                logger.info('By default, issuing an error.', image_path)
                return UploadStatus.ERROR

            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                output = e.stdout + e.stderr

                reason = ''
                if 'ETIMEDOUT' in output or isinstance(e, subprocess.TimeoutExpired):
                    reason = 'Connection timed out'
                elif 'ENETUNREACH' in output:
                    reason = 'Network unreachable'
                elif 'fetch failed' in output:
                    reason = 'Fetch failed'

                if reason:
                    # A known reason, so don't log the output
                    logger.error('%s - Failed to upload %s', reason, image_path.name)
                    attempt += 1
                    if attempt <= retries:
                        logger.debug(f"Retrying upload in 10 seconds... (Attempt {attempt}/{retries})")
                        time.sleep(10)
                        continue

                    logger.error("Max retries reached for %s.", image_path)

                # Unknown reason, log the output
                logger.error(f"Failed to upload {image_path} for unknown reason: {output}")
                return UploadStatus.ERROR

        logger.error('Max retries reached for %s.', image_path)
        return UploadStatus.ERROR

    def upload_file_threadsafe(self, image_path: Path, status: Status | None = None) -> UploadStatus:
        """
        Upload a file to Immich in a thread-safe manner.

        Args:
            image_path (Path): The file to upload.
            status (Status): An instance of the Status class.

        Returns:
            UploadStatus: The status of the upload operation.
        """
        filename = image_path.name

        try:
            result = self._upload_file(image_path, status)

            match result:
                case UploadStatus.UPLOADED:
                    self.record_upload_file()
                    if self.db:
                        self.db.mark_uploaded(image_path)
                case UploadStatus.DUPLICATE:
                    self.record_duplicate_file()
                    if self.db:
                        self.db.mark_uploaded(image_path)
                case UploadStatus.SKIPPED:
                    self.record_skip_file()
                case UploadStatus.ERROR:
                    self.record_error()
                case _:
                    logger.error('Unknown upload status: %s', result)
                    self.record_error()

            if status:
                status.update_status(filename, result)
                
        finally:
            subdir = image_path.parent
            self.progress_bar.text(self.report(f'/{str(subdir)[-25:]}/'))
            self.progress_bar()

        return result

    def upload(self, directory: Path | None = None, recursive: bool = True, max_threads: int = 4):
        """
        Upload files to Immich.

        Args:
            directory (Path): The directory to upload.
            recursive (bool): Whether to upload recursively.
            max_threads (int): The maximum number of threads for concurrent uploads.

        Raises:
            AuthenticationError: If authentication fails with Immich
        """
        if not self._authenticated:
            self.authenticate()

        directory = directory or self.directory
        if not self.exists(directory):
            raise FileNotFoundError(f"Directory {directory} does not exist.")
        directories = self.yield_directories(directory, recursive=recursive)


        with alive_bar(title=f"{CYAN2}Uploading{RESET} {str(directory.absolute())[-25:]}/", unit='files', dual_line=True, unknown='waves') as self._progress_bar:
            self.progress_bar.text(self.report('Searching...'))
            for subdir in directories:

                with Status(directory=subdir) as status:
                    # Check if the directory has changed since the last processed time
                    if not status.directory_changed():
                        logger.debug("Skipping directory %s as it has not changed since last processed.", subdir)
                        continue

                    files_to_upload = self.yield_files(subdir)

                    with ThreadPoolExecutor(max_workers=max_threads) as executor:
                        futures = []
                        for filepath in files_to_upload:
                            future = executor.submit(self.upload_file_threadsafe, filepath, status)
                            futures.append(future)

                        for future in as_completed(futures):
                            try:
                                future.result()
                            except Exception as e:
                                # Catch, report, and re-raise
                                self.record_error()
                                logger.error("Exception during upload: %s", e)
                                logger.exception(e)
                                raise

                    # At the conclusion of the upload, update the last processed time
                    # -- if the upload is cancelled, the last processed time will not be updated
                    status.update_meta()

    def upload_from_db(self, *, max_threads : int = 4):
        """
        Upload files from a database to Immich.

        Args:
            max_threads (int): The maximum number of threads for concurrent uploads.
        """
        if not self._authenticated:
            self.authenticate()

        if not self.db:
            raise ConfigurationError("No database specified.")

        total = self.db.count_records(uploaded=False)

        with alive_bar(total=total, title=f"{CYAN2}Uploading from db{RESET}", unit='files', dual_line=True, unknown='waves') as self._progress_bar:
            self.progress_bar.text(self.report())
            
            with ThreadPoolExecutor(max_workers=max_threads) as executor:
                futures = []
                for image_path in self.db.get_images(uploaded=False):
                    # Ensure the image still exists
                    if not self.exists(image_path):
                        logger.warning("File %s no longer exists.", image_path)
                        continue

                    future = executor.submit(self.upload_file_threadsafe, image_path)
                    futures.append(future)

                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as e:
                        # Catch, report, and re-raise
                        self.record_error()
                        logger.error("Exception during upload: %s", e)
                        raise

    def handle_sd_card(self, directory : Path | str = '', max_threads: int = 4) -> bool:
        """
        Triggered when an SD card is inserted. Uploads files from the SD card to Immich.

        Args:
            directory (Path | str): The directory of the SD card.

        Returns:
            bool: True if the upload was successful, False

        Raises:
            AuthenticationError: If authentication fails with Immich

        TODO:
            - Detect sd card directory (not just D:/)
            - Mount in WSL
        """
        if not directory:
            # If Windows, default directory is D:/
            if os.name == 'nt':
                directory = 'D:/'
            else:
                # Otherwise, linux, wsl, etc
                directory = '/mnt/d'

        sd_directory = Path(directory)
        if not self.exists(sd_directory):
            logger.error("SD card not found at %s", sd_directory)
            return False

        # If a DCIM directory exists, upload files from there
        dcim_directory = sd_directory / 'DCIM'
        if self.exists(dcim_directory):
            self.upload(dcim_directory, max_threads)
            return True

        # Otherwise, upload files from the root directory
        self.upload(sd_directory, max_threads)
        return True

    
    def report(self, message_prefix : str | None = None) -> str:
        """
        Create a report of the process so far.

        Args:
            message_prefix: An optional message to prefix the report with.

        Returns:
            The report string.
        """
        # Files
        file_buffer = []
        if self.files_uploaded > 0:
            file_buffer.append(f'{self.files_uploaded} uploaded')
        if self.files_duplicated > 0:
            file_buffer.append(f'{self.files_duplicated} duplicates')
        if self.files_moved > 0:
            file_buffer.append(f'{self.files_moved} moved')
        if self.files_deleted > 0:
            file_buffer.append(f'{self.files_deleted} deleted')
        if self.files_skipped > 0:
            file_buffer.append(f'{self.files_skipped} skipped')
            
        # Directories
        directory_buffer = []
        if self.directories_created > 0:
            directory_buffer.append(f'{self.directories_created} created')
        if self.directories_deleted > 0:
            directory_buffer.append(f'{self.directories_deleted} deleted')

        buffer = []
        if message_prefix:
            buffer.append(f'{CYAN}{message_prefix[-30:]:31s}{RESET}')
        if file_buffer:
            files_str = f"{PURPLE}Files [{', '.join(file_buffer)}]{RESET}"
            buffer.append(f"{files_str:50s}")
        if directory_buffer:
            directory_str = f"{YELLOW}Directories [{', '.join(directory_buffer)}]{RESET}"
            buffer.append(f"{directory_str:50s}")
        if self.errors > 0:
            error_str = f"{RED}Errors: {self.errors}{RESET}"
            buffer.append(f'{error_str:12s}')
            
        return f"{RESET}{' '.join(buffer) or '...'}{RESET}"

    def run(self, max_threads: int = 4):
        """
        Run the uploader.

        Args:
            max_threads (int): The maximum number of threads for concurrent uploads.
        """
        if self.db:
            self.upload_from_db(max_threads=max_threads)
        else:
            self.upload(max_threads=max_threads)

def validate_args(args: argparse.Namespace) -> bool:
    """
    Validate the arguments passed to the script.

    Args:
        args (argparse.Namespace): The arguments passed to the script.

    Returns:
        bool: True if the arguments are valid, False otherwise
    """
    if not args.url or not args.api_key:
        logger.error("IMMICH_URL and IMMICH_API_KEY must be set.")
        return False

    if not args.sd and not args.import_path:
        logger.error("CLOUD_THUMBNAILS_DIR must be set if not uploading from an SD card.")
        return False

    return True

class ArgNamespace(argparse.Namespace):
    """
    A custom namespace class for argparse.
    """
    url: str
    api_key: str
    allow_extension: list[str]
    ignore_extension: list[str]
    ignore_path: list[str]
    max_threads: int
    verbose: bool
    templates: list[str]
    sd: bool
    use_db: bool
    db_path : str | Path
    import_path: str
    album : str
    skip : bool

def main():
    """
    Called when the script is run from the command line. Parses arguments and uploads files to Immich.
    """
    try:
        load_dotenv()

        url = os.getenv("IMMICH_URL")
        api_key = os.getenv("IMMICH_API_KEY")
        thumbnails_dir = os.getenv("IMMICH_THUMBNAILS_DIR", '.')
        max_threads = os.getenv("IMMICH_MAX_THREADS", 4)

        parser = argparse.ArgumentParser(description="Upload files to Immich.")
        parser.add_argument("--url", help="Immich URL", default=url)
        parser.add_argument("--api-key", help="Immich API key", default=api_key)
        parser.add_argument('--allow-extension', '-e', help="Allow only files with these extensions", nargs='+')
        parser.add_argument("--ignore-extension", "-E", help="Ignore files with these extensions", nargs='+')
        parser.add_argument('--ignore-path', '-P', help="Ignore files with these paths", nargs='+')
        parser.add_argument('--max-threads', '-t', type=int, default=max_threads, help="Maximum number of threads for concurrent uploads")
        parser.add_argument('--verbose', '-v', action='store_true', help="Verbose output")
        parser.add_argument('--templates', '-T', help="File templates to match", nargs='+')
        parser.add_argument('--sd', help="Upload files from an SD card", action='store_true')
        parser.add_argument('--use_db', action='store_true', help='Use the SQLite database to retrieve upload targets')
        parser.add_argument('--db-path', help='Path to the SQLite database', default=DEFAULT_DB_PATH)
        parser.add_argument('--album', '-A', help='Immich album to upload files to')
        parser.add_argument('--skip', help='Skip assets that were previously uploaded.', action='store_true')
        parser.add_argument("import_path", nargs='?', default=thumbnails_dir, help="Path to import files from")
        args = parser.parse_args(namespace=ArgNamespace())

        if args.verbose:
            logger.setLevel(logging.DEBUG)

        if not validate_args(args):
            sys.exit(1)

        templates = []
        if args.templates:
            template : str
            for template in args.templates:
                match template.lower():
                    case 'pixel':
                        templates.append(PixelFiles)
                    case _:
                        logger.error("Unknown template: %s. See --help for available templates.", template)
                        sys.exit(1)

        immich = ImmichProgressiveUploader(
            url=args.url,
            api_key=args.api_key,
            directory=args.import_path,
            ignore_extensions=args.ignore_extension,
            ignore_paths=args.ignore_path,
            allowed_extensions=args.allow_extension,
            templates=templates,
            use_db=args.use_db,
            db_path=args.db_path,
            album=args.album,
            skip=args.skip,
        )

        try:
            if args.sd:
                immich.handle_sd_card(max_threads=args.max_threads)
            else:
                immich.run(max_threads=args.max_threads)

        except AuthenticationError:
            logger.error("Authentication failed. Check your API key and URL.")
            sys.exit(1)
        except (FileNotFoundError, FileExistsError, AppException) as e:
            logger.error('Exiting. %s', e)
            raise
            sys.exit(1)
        finally:
            logger.info("Stats: %d uploaded, %d skipped, %d duplicates, %d errors",
                immich.files_uploaded,
                immich.files_skipped,
                immich.files_duplicated,
                immich.errors
            )
    except KeyboardInterrupt:
        logger.info("Upload cancelled by user.")

    sys.exit(0)

if __name__ == "__main__":
    main()
