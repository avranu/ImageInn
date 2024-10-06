"""
Upload files to Immich.

This script is used because the immich app isn't reliable for uploading files, and I don't want to
manually upload files via the web interface (and leave that interface open in Chrome).

Instead, this cli script can be run as a periodic cronjob.

See also the organize.py script for organizing files into directories prior to this script being 
executed.

This script is referenced in bash_aliases (but not in the github copy of it).

Version 1.0
Date: 2024-09-20
Status: Working

Example:
    >>> python progressive.py
    >>> python progressive.py /mnt/i/Phone
    # bash_aliases defines `upload` to run this script for the current dir
    >>> upload
    >>> upload -e jpg /mnt/d/Photos
    >>> upload -t pixel /mnt/i/Phone

TODO:
    - When supplying arguments to the script (such as --allow-extension), the script will skip some files, but still save
      last_processed_time and version. Therefore, a subsequent run without those args will still skip some directories.
    - Don't skip current directory
    - "dont-skip" argument, or "fast".
"""
from __future__ import annotations
import logging
import os
import sys
import time

# Add the root directory of the project to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from typing import Collection, Generator
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from dotenv import load_dotenv
import argparse
from tqdm import tqdm
from scripts import setup_logging
from scripts.lib.file_manager import FileManager
from scripts.thumbnails.upload.exceptions import AuthenticationError
from scripts.thumbnails.upload.interface import ImmichInterface
from scripts.thumbnails.upload.status import Status, UploadStatus
from scripts.thumbnails.upload.template import PixelFiles, FileTemplate

logger = setup_logging()

class ImmichProgressiveUploader(ImmichInterface):
        
    def _upload_file(self, image_path: Path, status: Status | None = None) -> UploadStatus:
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
        try:
            result = subprocess.run(
                command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
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
            logger.info('By default, marking file %s uploaded successfully.', image_path)
            return UploadStatus.UPLOADED
        except subprocess.CalledProcessError as e:
            output = e.stdout + e.stderr
            logger.error(f"Failed to upload {image_path}: {output}")
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

        result = self._upload_file(image_path, status)

        # Do not save skipped statuses, because it would change 'uploaded' to 'skipped' in our file on a 2nd run.
        if status is not None and result != UploadStatus.SKIPPED:
            status.update_status(filename, result)

        return result


    def upload(self, directory: Path | None = None, recursive: bool = True, max_threads: int = 4):
        """
        Upload files to Immich.

        Args:
            directory (Path): The directory to upload.
            recursive (bool): Whether to upload recursively.
            max_threads (int): The maximum number of threads for concurrent uploads.
        """
        if not self._authenticated:
            self.authenticate()

        directory = directory or self.directory
        directories = self.yield_directories(directory, recursive=recursive)

        uploaded_count = 0
        skipped_count = 0
        error_count = 0
        duplicate_count = 0

        with tqdm(desc="Directories", unit='dir') as progress_bar:
            for directory in directories:

                try:
                    with Status(directory=directory) as status:

                        # Check if the directory has changed since the last processed time
                        if not status.directory_changed():
                            logger.debug(f"Skipping directory {directory} as it has not changed since last processed.")
                            continue

                        files_to_upload = self.get_files(directory)

                        with ThreadPoolExecutor(max_workers=max_threads) as executor:
                            futures = []
                            for file in files_to_upload:
                                future = executor.submit(self.upload_file_threadsafe, file, status)
                                futures.append(future)

                            # Initialize the progress bar
                            for future in tqdm(
                                as_completed(futures), 
                                total=len(futures), 
                                unit='files', 
                                leave=False,
                                desc=f"Uploading {directory.name}"
                            ):

                                try:
                                    result = future.result()
                                    if result == UploadStatus.UPLOADED:
                                        uploaded_count += 1
                                    elif result == UploadStatus.SKIPPED:
                                        skipped_count += 1
                                    elif result == UploadStatus.ERROR:
                                        error_count += 1
                                    elif result == UploadStatus.DUPLICATE:
                                        duplicate_count += 1

                                except Exception as e:
                                    error_count += 1
                                    logger.error(f"Exception during upload: {e}")
                                    raise
                                
                                finally:
                                    progress_bar.set_postfix(
                                        uploaded=uploaded_count, skipped=skipped_count, error=error_count, duplicates=duplicate_count
                                    )

                        # At the conclusion of the upload, update the last processed time
                        # -- if the upload is cancelled, the last processed time will not be updated
                        status.update_meta()
                finally:
                    progress_bar.update(1)


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
        parser.add_argument("thumbnails_dir", nargs='?', default=thumbnails_dir, help="Cloud thumbnails directory")
        args = parser.parse_args()
        
        if args.verbose:
            logger.setLevel(logging.DEBUG)

        if not args.url or not args.api_key or not args.thumbnails_dir:
            logger.error("IMMICH_URL, IMMICH_API_KEY, and CLOUD_THUMBNAILS_DIR must be set.")
            sys.exit(1)

        templates = []
        if args.templates:
            template : str
            for template in args.templates:
                match template.lower():
                    case 'pixel':
                        templates.append(PixelFiles)
                    case _:
                        logger.error(f"Unknown template: {template}. See --help for available templates.")
                        sys.exit(1)
            
        immich = ImmichProgressiveUploader(
            url=args.url,
            api_key=args.api_key,
            directory=args.thumbnails_dir,
            ignore_extensions=args.ignore_extension,
            ignore_paths=args.ignore_path,
            allowed_extensions=args.allow_extension,
            templates=templates,
        )
        immich.upload(max_threads=args.max_threads)

    except AuthenticationError:
        logger.error("Authentication failed. Check your API key and URL.")
    except KeyboardInterrupt:
        logger.info("Upload cancelled by user.")

if __name__ == "__main__":
    main()