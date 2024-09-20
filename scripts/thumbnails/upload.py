#!/usr/bin/env python3
"""
Version 1.0
Date: 2024-09-20
Working

Example:
    >>> python upload.py
    >>> python upload.py -d /mnt/i/Phone
    # bash_aliases defines `upload` to run this script for the current dir
    >>> upload
"""
from __future__ import annotations
import os
import sys

# Add the root directory of the project to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import subprocess
from pathlib import Path
from dotenv import load_dotenv
import argparse
from pydantic import BaseModel, Field, PrivateAttr, field_validator
from typing import Iterable, List
from tqdm import tqdm
from scripts import setup_logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from abc import ABC, abstractmethod

logger = setup_logging()

class AuthenticationError(Exception):
    pass

ALLOWED_EXTENSIONS = [
    # Images
    'jpg', 'jpeg', 'png', 'gif', 'tiff', 'webp',
    # RAW
    'arw', 'dng', 'nef',
    # Videos
    'mp4', 'mov', 'm4a', 'wmv', 'avi', 'mkv', 'flv', 'webm',
    # Audio
    'mp3', 'wav', 'm4a', 'ogg',
    # Photo editing
    'psd', 'svg',
]

class ImmichInterface(BaseModel, ABC):
    url: str
    api_key: str
    directory: Path
    ignore_extensions: List[str] = Field(default_factory=list)
    ignore_paths: List[str] = Field(default_factory=list)
    large_file_size: int = 1024 * 1024 * 100  # 100 MB

    _authenticated: bool = PrivateAttr(default=False)

    @field_validator('directory', mode="before")
    def validate_directory(cls, v):
        # Allow str and list[str]
        v = Path(v)
        if not v.exists():
            logger.error(f"Directory {v} does not exist.")
            raise FileNotFoundError(f"Directory {v} does not exist.")
        return v

    @field_validator('ignore_extensions', mode="before")
    def validate_ignore_extensions(cls, v):
        if not v:
            return []
        if isinstance(v, str):
            return [v]
        if isinstance(v, list):
            return v
        raise ValueError("Invalid ignore_extensions value.")

    @field_validator('ignore_paths', mode="before")
    def validate_ignore_paths(cls, v):
        if not v:
            return []
        if isinstance(v, (str, Path)):
            return [str(v)]
        if isinstance(v, Iterable):
            return [str(path) for path in v]
        raise ValueError("Invalid ignore_paths value.")

    def authenticate(self):
        if self._authenticated:
            return
        try:
            subprocess.run(["immich", "login-key", self.url, self.api_key], check=True)
            self._authenticated = True
            logger.info("Authenticated successfully.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Authentication failed: {e}")
            raise AuthenticationError("Authentication failed.") from e

    @abstractmethod
    def upload(self, directory: Path | None = None, recursive: bool = True):
        """Abstract method to upload files."""
        pass

    # Shared methods
    def should_ignore_file(self, file: Path, status: dict[str, str] | None = None, status_lock: threading.Lock | None = None) -> bool:
        if not file.is_file():
            return True

        suffix = file.suffix.lstrip('.').lower()

        # Ignore non-image extensions
        if suffix not in ALLOWED_EXTENSIONS:
            logger.debug("Ignoring non-media file due to extension: %s", file)
            return True

        if suffix in self.ignore_extensions:
            logger.debug("Ignoring file due to extension: %s", file)
            return True

        # Ignore hidden
        if file.name.startswith('.'):
            logger.debug("Ignoring hidden file: %s", file)
            return True

        if str(file) in self.ignore_paths:
            logger.debug("Ignoring file due to path: %s", file)
            return True

        if file.stat().st_size > self.large_file_size:
            logger.debug(f"File {file} is larger than {self.large_file_size} bytes and will be skipped.")
            return True

        if status is not None and status_lock is not None:
            filename = file.name
            with status_lock:
                if filename in status and status[filename] == 'success':
                    logger.debug(f"Skipping already uploaded file {file}")
                    return True

        return False

    def load_status_file(self, directory: Path | None = None) -> dict[str, str]:
        directory = directory or self.directory
        status_file = directory / 'upload_status.txt'
        status = {}
        if status_file.exists():
            with status_file.open('r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        parts = line.split('\t')
                        if len(parts) == 2:
                            filename, file_status = parts
                            status[filename] = file_status

            success = len([s for s in status.values() if s == 'success'])
            failure = len([s for s in status.values() if s == 'failed'])
            logger.info(f"Loaded status file {status_file}. Success: {success}, Failure: {failure}")

        return status

    def save_status_file(self, directory: Path, status: dict[str, str], status_lock: threading.Lock):
        with status_lock:
            status_file = directory / 'upload_status.txt'
            logger.debug(f"Saving status file {status_file}")
            with status_file.open('w') as f:
                for filename, file_status in status.items():
                    f.write(f'{filename}\t{file_status}\n')

class ImmichProgressiveUploader(ImmichInterface):

    def upload_file(self, file: Path) -> bool:
        command = ["immich", "upload", file.as_posix()]
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
                logger.debug("%s already uploaded.", file)
                return True
            if "Unsupported file type" in output:
                logger.debug("Unsupported file type: %s", file)
                return False
            if "Successfully uploaded" in output:
                logger.debug("Uploaded %s successfully.", file)
                return True

            logger.info('Unknown output: %s', output)
            logger.info('By default, marking file %s uploaded successfully.', file)
            return True
        except subprocess.CalledProcessError as e:
            output = e.stdout + e.stderr
            logger.error(f"Failed to upload {file}: {output}")

        return False

    def upload_file_threadsafe(self, file: Path, status: dict[str, str], status_lock: threading.Lock) -> bool:
        filename = file.name

        if self.should_ignore_file(file):
            return False

        success = self.upload_file(file)

        with status_lock:
            status[filename] = 'success' if success else 'failed'

        return success

    def get_directories(self, directory: Path, recursive: bool = True) -> list[Path]:
        if not recursive:
            return [directory]

        logger.info('Searching %s for directories.', directory.absolute())

        result = []
        for dirpath, dirnames, _ in os.walk(directory):
            # Remove hidden directories from dirnames so os.walk doesn't traverse into them
            dirnames[:] = [d for d in dirnames if not d.startswith('.')]

            # Skip the directory if it's hidden
            if Path(dirpath).name.startswith('.'):
                continue

            result.append(Path(dirpath))

        return result

    def upload(self, directory : Path | None = None, recursive: bool = True, max_threads: int = 4):
        if not self._authenticated:
            self.authenticate()

        directory = directory or self.directory
        directories = self.get_directories(directory, recursive=recursive)

        logger.info("Uploading files from %d directories.", len(directories))

        for directory in tqdm(directories, desc="Directories"):
            status = self.load_status_file(directory)
            status_lock = threading.Lock()
            try:
                files = list(directory.iterdir())
                files_to_upload = [file for file in files if not self.should_ignore_file(file, status, status_lock)]
                if not files_to_upload:
                    logger.debug("No files to upload in %s", directory)
                    continue

                with ThreadPoolExecutor(max_workers=max_threads) as executor:
                    futures = []
                    for file in files_to_upload:
                        future = executor.submit(self.upload_file_threadsafe, file, status, status_lock)
                        futures.append(future)
                    for future in tqdm(
                        as_completed(futures), 
                        total=len(futures), 
                        unit="file", 
                        leave=False,
                        desc=f"Uploading {directory.name}"
                    ):
                        # re-raise any exceptions
                        future.result()  
            finally:
                self.save_status_file(directory, status, status_lock)

class ImmichDirectUploader(ImmichInterface):
    """
    Deprecated. Use ImmichProgressiveUploader for uploading files.

    This class is kept in case Immich optimizes their upload feature in the future. It works, but
    does not support terminating and resuming uploads, so requires re-computing the hash of all files
    every time it is run.
    """

    def find_large_files(self, directory: Path | None = None, size: int = 1024 * 1024 * 100) -> list[Path]:
        if not directory:
            directory = self.directory

        large_files = []
        for file in directory.rglob("**/*"):
            if file.stat().st_size > size:
                large_files.append(file)
        return large_files

    def _compile_ignore_patterns(self, directory: Path) -> list[str]:
        ignore_patterns = []

        for ext in self.ignore_extensions:
            # Handle not (!)
            if ext.startswith("!"):
                ignore_patterns.append(f'!*.{ext[1:]}')
            else:
                ignore_patterns.append(f'*.{ext}')

        for path in self.ignore_paths:
            ignore_patterns.append(path)

        if large_files := self.find_large_files(directory):
            logger.warning("%d Large files found, which will be skipped.", len(large_files))
            ignore_patterns.extend([file.as_posix() for file in large_files])

        return ignore_patterns

    def upload(self, directory: Path | None = None, recursive: bool = True):
        if not self._authenticated:
            self.authenticate()

        logger.warning('Using ImmichDirectUploader is not recommended. Use ImmichProgressiveUploader instead.')

        directory = directory or self.directory

        command = ["immich", "upload"]

        # Ignore files
        if ignore_patterns := self._compile_ignore_patterns(directory):
            ignore_string = "|".join(ignore_patterns)
            command.extend(["-i", f'({ignore_string})'])

        if recursive:
            command.append("--recursive")

        command.append(directory.as_posix())

        try:
            subprocess.run(command, check=True)
            logger.info("Files uploaded successfully.")
        except subprocess.CalledProcessError as e:
            logger.error(f"File upload failed: {e}")

def main():
    try:
        load_dotenv()

        url = os.getenv("IMMICH_URL")
        api_key = os.getenv("IMMICH_API_KEY")
        thumbnails_dir = os.getenv("CLOUD_THUMBNAILS_DIR", '.')

        parser = argparse.ArgumentParser(description="Upload files to Immich.")
        parser.add_argument("--url", help="Immich URL", default=url)
        parser.add_argument("--api-key", help="Immich API key", default=api_key)
        parser.add_argument("--thumbnails-dir", '-d', help="Cloud thumbnails directory", default=thumbnails_dir)
        parser.add_argument("--ignore-extensions", "-e", help="Ignore files with these extensions", nargs='+')
        parser.add_argument('--ignore-paths', '-i', help="Ignore files with these paths", nargs='+')
        parser.add_argument('--max-threads', '-t', type=int, default=4, help="Maximum number of threads for concurrent uploads")
        args = parser.parse_args()

        if not args.url or not args.api_key or not args.thumbnails_dir:
            logger.error("IMMICH_URL, IMMICH_API_KEY, and CLOUD_THUMBNAILS_DIR must be set.")
            sys.exit(1)
            
        immich = ImmichProgressiveUploader(
            url=args.url,
            api_key=args.api_key,
            directory=Path(args.thumbnails_dir),
            ignore_extensions=args.ignore_extensions,
            ignore_paths=args.ignore_paths
        )
        immich.upload(max_threads=args.max_threads)

    except AuthenticationError:
        logger.error("Authentication failed. Check your API key and URL.")
    except KeyboardInterrupt:
        logger.info("Upload cancelled by user.")

if __name__ == "__main__":
    main()