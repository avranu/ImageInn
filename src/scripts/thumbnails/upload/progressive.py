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
import argparse
from pydantic import PrivateAttr
from alive_progress import alive_bar

from scripts.lib.db.images import ImagesDatabase
from scripts.thumbnails.upload.meta import DEFAULT_DB_PATH

# Add the root directory of the project to sys.path
PARENT_DIR = Path(__file__).resolve().parents[3]
sys.path.append(PARENT_DIR.absolute().as_posix())

from scripts import setup_logging
from scripts.lib.types import ProgressBar, RED, CYAN, CYAN2, YELLOW, YELLOW2, BLUE, PURPLE, RESET
from scripts.lib.utils import seconds_to_human
from scripts.exceptions import AppError
from scripts.thumbnails.upload.meta import MAX_RETRIES, SECONDS_PER_RETRY
from scripts.thumbnails.upload.exceptions import AuthenticationError, ConfigurationError
from scripts.thumbnails.upload.interface import ImmichInterface
from scripts.thumbnails.upload.status import FileStatus, DirectoryStatus, StatusOptions
from scripts.thumbnails.upload.template import PixelFiles

from threading import Event


logger = setup_logging()

class ImmichProgressiveUploader(ImmichInterface):
    
    _planned_total_files: int = PrivateAttr(default=0)
    _plan_ready: Event = PrivateAttr(default_factory=Event)
    _plan_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)
    
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

    def _upload_file(self, image_path: Path, retries: int = 3) -> StatusOptions:
        """
        Upload a file to Immich.

        Args:
            image_path (Path): The file to upload.

        Returns:
            UploadStatus: The status of the upload operation.
        """
        if self.should_ignore_file(image_path):
            logger.debug('Ignoring %s', image_path)
            return StatusOptions.SKIPPED

        self.progress_message(f'Uploading {image_path.name[-15:]}')

        if self.check_dry_run('running immich upload'):
            return StatusOptions.UPLOADED

        command = ["immich", "upload", image_path.as_posix()]
        if self.album:
            command.extend(['-A', self.album])

        # Timeout is a minimum of 60 seconds, plus 10 seconds per MB
        filesize = self.file_size(image_path)
        extra_timeout = filesize * 10 / (1024 * 1024)
        timeout = 60 + extra_timeout
        logger.debug("Setting upload timeout to %s", seconds_to_human(timeout))
        
        attempt = 0
        while attempt <= retries:
            try:
                result = subprocess.run(
                    command,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=timeout,
                    text=True
                )
                output = result.stdout + result.stderr
                self.record_bytes_uploaded(filesize)
                
                # Analyze the output
                if "All assets were already uploaded" in output:
                    logger.debug("%s already uploaded.", image_path)
                    return StatusOptions.DUPLICATE
                if "Unsupported file type" in output:
                    logger.debug("Unsupported file type: %s", image_path)
                    return StatusOptions.ERROR
                if "Successfully uploaded" in output:
                    logger.debug("Uploaded %s successfully.", image_path)
                    return StatusOptions.UPLOADED

                logger.info('Unknown output: %s', output)
                logger.info('By default, issuing an error.', image_path)
                return StatusOptions.ERROR

            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                output = f'{e.stdout} + {e.stderr}'

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
                return StatusOptions.ERROR

        logger.error('Max retries reached for %s.', image_path)
        return StatusOptions.ERROR

    def upload_file_threadsafe(self, image_path: Path) -> StatusOptions:
        """
        Upload a file to Immich in a thread-safe manner.

        Args:
            image_path (Path): The file to upload.

        Returns:
            UploadStatus: The status of the upload operation.
        """
        # default is failure
        result = False

        for i in range(MAX_RETRIES):
            try:
                result = self._upload_file(image_path)

                match result:
                    case StatusOptions.UPLOADED:
                        self.record_upload_file()
                        if self.db:
                            self.db.mark_uploaded(image_path)
                        self.handle_move_after_upload(image_path)
                    case StatusOptions.DUPLICATE:
                        self.record_duplicate_file()
                        if self.db:
                            self.db.mark_uploaded(image_path)
                    case StatusOptions.SKIPPED:
                        self.record_skip_file()
                    case StatusOptions.ERROR:
                        self.record_error()
                    case _:
                        logger.error('Unknown upload status: %s', result)
                        self.record_error()

                FileStatus.update_status(image_path, result)

                # Finished without an exception, so don't retry
                break

            except OSError as ose:
                # Catch error 112 (host is down) and retry
                if ose.errno == 112:
                    self._wait_retry(i, "Host is down")
                    continue
                    
            finally:
                subdir = image_path.parent
                self.progress_advance(f'/{str(subdir)[-25:]}/')

        # Sleep for 10ms after processing each file to reduce disk I/O pressure
        time.sleep(0.01)
        
        return result

    def handle_move_after_upload(self, image_path : Path) -> None:
        """
        Move a file after it has been uploaded to Immich.

        Args:
            image_path (Path): The file to move.
        """
        if not self.move_after_upload:
            return

        target_directory = self.move_after_upload
        if not target_directory.absolute():
            target_directory = image_path.parent.absolute() / target_directory
        if not target_directory.exists():
            self.mkdir(target_directory)

        destination = target_directory / image_path.name

        self.move_file(image_path, destination, rename_on_collision=True)
        logger.info("Moved %s to %s", image_path, destination)

    def _wait_retry(self, loop : int = 1, message : str = 'Attempt failed') -> None:
        """
        Wait for a retry, and logs a message about it.

        Args:
            loop (int): The current loop iteration.
            message (str): The message to display.
        """
        if loop >= MAX_RETRIES:
            logger.error("%s. Max retries reached.", message)
            return
        
        wait = 1 + SECONDS_PER_RETRY * loop
        logger.error("%s. Retrying in %d seconds...", message, wait)

        time.sleep(wait)

    def upload(self, directory: Path | None = None, *, recursive: bool = True):
        """
        Upload files to Immich.

        Args:
            directory (Path): The directory to upload.
            recursive (bool): Whether to upload recursively.

        Raises:
            AuthenticationError: If authentication fails with Immich
        """
        if not self._authenticated:
            self.authenticate()

        directory = directory or self.directory
        if not self.exists(directory):
            raise FileNotFoundError(f"Directory {directory} does not exist.")

        # --- start background counter early; won't block uploads ---
        try:
            self._plan_ready.clear()
            t = threading.Thread(
                target=self._count_files_background, args=(directory,), daemon=True
            )
            t.start()
        except Exception as e:
            logger.debug("Unable to start background counter: %s", e)
        # -----------------------------------------------------------

        with alive_bar(
            title=f"{CYAN2}Uploading{RESET} {str(directory.absolute())[-25:]}/",
            unit='files',
            dual_line=True,
            unknown='waves'
        ) as self._progress_bar:
            self.progress_message('Searching...')

            for subdir in self.yield_directories(directory, recursive=recursive):
                self.progress_message(f'Counting files in {subdir.name}')
                last_modified_time = self.get_last_modified_time(subdir)
                files_to_upload = self.get_all_files(subdir, recursive=False)
                file_count = len(files_to_upload)

                if DirectoryStatus.has_directory_changed(
                    subdir, file_count, last_modified_time, self.get_glob_patterns()
                ):
                    logger.info('Skipping subdir because it has not changed since last upload: %s', subdir)
                    continue

                self.progress_message(f'{file_count} files queued')

                # Remove previous uploads from the list
                successful_uploads = FileStatus.get_all_status(subdir, StatusOptions.UPLOADED)
                files_to_upload = [f for f in files_to_upload if f not in successful_uploads]
                if (files_to_upload_count := len(files_to_upload)) < 1:
                    logger.debug('Pruned all files from %s', subdir)
                    continue
                if (pruned_count := file_count - files_to_upload_count) > 0:
                    logger.info('Pruned %d files from %s', pruned_count, subdir)

                with ThreadPoolExecutor(max_workers=self.max_threads) as executor:
                    # initialize the start time for calculating upload speed / ETA
                    self._start_ns = time.time_ns()

                    futures = []
                    for filepath in files_to_upload:
                        futures.append(executor.submit(self.upload_file_threadsafe, filepath))

                    for future in as_completed(futures):
                        for i in range(MAX_RETRIES):
                            try:
                                future.result()
                            except OSError as ose:
                                # Catch error 112 (host is down) and retry
                                if ose.errno == 112:
                                    self._wait_retry(i, "Host is down")
                                    continue
                                raise
                            except Exception as e:
                                # Catch, report, and re-raise
                                self.record_error()
                                logger.error("Exception during upload: %s", e)
                                logger.exception(e)
                                raise
                                                    
                            # Finished without an exception, so don't retry
                            break

                # IFF we finish looping without error, update the DirectoryStatus
                DirectoryStatus.update(subdir, file_count, last_modified_time, self.get_glob_patterns())
                
    def upload_from_db(self):
        """
        Upload files from a database to Immich.
        """
        if not self._authenticated:
            self.authenticate()

        if not self.db:
            raise ConfigurationError("No database specified.")

        total = self.db.count_records(uploaded=False)

        with alive_bar(total=total, title=f"{CYAN2}Uploading from db{RESET}", unit='files', dual_line=True, unknown='waves') as self._progress_bar:
            self.progress_message('Searching DB...')
            
            with ThreadPoolExecutor(max_workers=self.max_threads) as executor:
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

    def handle_sd_card(self, directory : Path | str = '') -> bool:
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
            self.upload(dcim_directory)
            return True

        # Otherwise, upload files from the root directory
        self.upload(sd_directory)
        return True

    def _count_files_background(self, root: Path) -> None:
        """
        Count, in the background, how many files *will* be attempted for upload.
        Respects templates, ignore rules, 'skip', and unchanged-directory pruning.
        When finished, sets self._planned_total_files and flips self._plan_ready.
        """
        try:
            total = 0
            for subdir in self.yield_directories(root, recursive=True):
                try:
                    last_modified_time = self.get_last_modified_time(subdir)
                    # List candidates quickly (non-recursive per your main loop)
                    files = self.get_all_files(subdir, recursive=False)
                    file_count = len(files)

                    # Mimic main-loop pruning: skip unchanged dirs
                    if DirectoryStatus.has_directory_changed(
                        subdir, file_count, last_modified_time, self.get_glob_patterns()
                    ):
                        continue

                    # Remove files that won't be processed (skip per status/templates/etc)
                    # - honor per-file ignore rules and 'skip' of already-successful uploads
                    pruned = 0
                    for f in files:
                        if self.should_ignore_file(f):
                            pruned += 1
                            continue
                        if self.skip and FileStatus.was_successful(f):
                            pruned += 1
                            continue
                        total += 1
                except Exception as e:
                    # Non-fatal: keep counting other dirs
                    logger.debug("Background count error in %s -> %s", subdir, e)

            with self._plan_lock:
                self._planned_total_files = total
                self._plan_ready.set()
            # Nudge the UI once plan is ready; message kept short to avoid noise.
            self.progress_message("ETA ready")
        except Exception as e:
            logger.error("Background counting failed: %s", e)
            # Still flip the event so we don't wait forever; total stays 0.
            self._plan_ready.set()

    def report(self, message_prefix: str | None = None) -> str:
        """
        Create a report of the process so far (extended to include ETA once count is ready).

        Args:
            message_prefix: An optional message to prefix the report with.

        Returns:
            The report string.
        """
        if message_prefix is None:
            message_prefix = self._progress_message

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

        upload_speed = self.get_upload_speed()
        if upload_speed:
            speed_str = f"{BLUE}{upload_speed} MB/s{RESET}"
            buffer.append(f"{speed_str:10s}")

        # --- ETA once background count finishes ---
        if self._plan_ready.is_set():
            with self._plan_lock:
                planned = self._planned_total_files
            processed = (
                self.files_uploaded
                + self.files_duplicated
                + self.errors
            )

            if planned > 0:
                total = max(0, planned - self.files_skipped)
                remaining = max(0, total - processed)
                # time basis: elapsed seconds since first upload started
                if self._start_ns and processed > 0:
                    elapsed = max(1e-6, (time.time_ns() - self._start_ns) / 1e9)
                    files_per_sec = processed / elapsed
                    if files_per_sec > 0:
                        eta_secs = int(remaining / files_per_sec)
                        eta_str = seconds_to_human(eta_secs)
                    else:
                        eta_str = "--"
                else:
                    eta_str = "--"

                eta_disp = f"{YELLOW}ETA:{RESET} {eta_str} {YELLOW2}({remaining} left/{total}){RESET}"
                buffer.append(f"{eta_disp:28s}")

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

    def run(self):
        """
        Run the uploader.
        """
        if self.db:
            self.upload_from_db()
        else:
            self.upload()

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
    move_after_upload : str | None = None
    info : bool = False
    
def validate_args(args: ArgNamespace) -> bool:
    """
    Validate the arguments passed to the script.

    Args:
        args (argparse.Namespace): The arguments passed to the script.

    Returns:
        bool: True if the arguments are valid, False otherwise
    """
    if not args.url or not args.api_key:
        logger.error("IMMICH_INSTANCE_URL and IMMICH_API_KEY must be set.")
        return False

    if not args.sd and not args.import_path:
        logger.error("IMAGEINN_THUMBNAILS_DIR must be set if not uploading from an SD card.")
        return False

    return True

def main():
    """
    Called when the script is run from the command line. Parses arguments and uploads files to Immich.
    """
    try:
        api_key = os.getenv("IMMICH_API_KEY")
        thumbnails_dir = os.getenv("IMMICH_THUMBNAILS_DIR", '.')
        
        url = os.getenv("IMMICH_INSTANCE_URL")
        if home_network := ImmichProgressiveUploader.is_home_network():
            logger.info('Detected home network.')
            url = os.getenv("IMMICH_LOCAL_URL")
        else:
            logger.info('Detected remote network.')

        parser = argparse.ArgumentParser(description="Upload files to Immich.")
        parser.add_argument("--url", help="Immich URL", default=url)
        parser.add_argument("--api-key", help="Immich API key", default=api_key)
        parser.add_argument('--allow-extension', '-e', help="Allow only files with these extensions", nargs='+')
        parser.add_argument("--ignore-extension", help="Ignore files with these extensions", nargs='+')
        parser.add_argument('--ignore-path', help="Ignore files with these paths", nargs='+')
        parser.add_argument('--max-threads', type=int, default=0, help="Maximum number of threads for concurrent uploads")
        parser.add_argument('--verbose', '-v', action='store_true', help="Verbose output")
        parser.add_argument('--templates', '-T', help="File templates to match", nargs='+')
        parser.add_argument('--sd', help="Upload files from an SD card", action='store_true')
        parser.add_argument('--use_db', action='store_true', help='Use the SQLite database to retrieve upload targets')
        parser.add_argument('--db-path', help='Path to the SQLite database', default=DEFAULT_DB_PATH)
        parser.add_argument('--album', '-A', help='Immich album to upload files to')
        parser.add_argument('--skip', help='Skip assets that were previously uploaded.', action='store_true')
        parser.add_argument('--move-after-upload', help='Move files to this directory after uploading', default=None)
        parser.add_argument('--info', action='store_true', help='Show information about the script and exit')
        parser.add_argument("import_path", nargs='?', default=thumbnails_dir, help="Path to import files from")
        args = parser.parse_args(namespace=ArgNamespace())

        if args.verbose:
            logger.setLevel(logging.DEBUG)

        if not args.info and not validate_args(args):
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

        if args.info:
            print(f"""
                    Env:
                    API Key: {api_key[1:3]+"..." if api_key else 'N/A'}
                    URL: {url or 'N/A'}
                    ----------------------------------------
                    Args: 
                    {args}
                    ----------------------------------------
                    """)
            """
                    Immich Configuration:
                    ----------------------------------------
                    URL: {immich.url}
                    API Key: {immich.api_key[1:3]}...{immich.api_key[-3:]}
                    Import Path: {immich.directory}
                    Use DB: {immich.db is not None}
                    DB Path: {immich.db_path if immich.db else 'N/A'}
                    Album: {immich.album or 'N/A'}
                    Skip previously uploaded: {immich.skip}
                    Move after upload: {immich.move_after_upload or 'N/A'}
                    Max Threads: {immich.max_threads}
                    Templates: {', '.join([t.__name__ for t in immich.templates]) or 'N/A'}
                    Allowed Extensions: {', '.join(immich.extensions) if immich.extensions else 'All'}
                    Ignored Extensions: {', '.join(immich.ignore_extensions) if immich.ignore_extensions else 'None'}
                    Ignored Paths: {', '.join(immich.ignore_paths) if immich.ignore_paths else 'None'}
            """
            sys.exit(0)
            
        immich = ImmichProgressiveUploader(
            url=args.url,
            api_key=args.api_key,
            directory=args.import_path,
            ignore_extensions=args.ignore_extension,
            ignore_paths=args.ignore_path,
            extensions=args.allow_extension,
            templates=templates,
            use_db=args.use_db,
            db_path=args.db_path,
            album=args.album,
            skip=args.skip,
            max_threads=args.max_threads,
            # Cloudflare prevents uploads over 100MB. 
            # ...On the local network, disable skipping large files.
            # ...Everywhere else, use the default large file size of 100MB.
            large_file_size = 0 if home_network else (1024 * 1024 * 100),
            move_after_upload=args.move_after_upload
        )
                
        try:
            if args.sd:
                immich.handle_sd_card()
            else:
                immich.run()

        except AuthenticationError:
            logger.error("Authentication failed. Check your API key and URL.")
            sys.exit(1)
        except (FileNotFoundError, FileExistsError, AppError) as e:
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
