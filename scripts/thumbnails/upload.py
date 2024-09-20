#!/usr/bin/env python3
"""
Version 1.0
Date: 2024-09-17
Working

Example:
    >>> python upload.py
    >>> python upload.py -d /mnt/i/Phone
    # bash_aliases defines `upload` to run this script for the current dir
    >>> upload

TODO:
    Suppress immich output
    progress bar
    concurrency
    
"""
from __future__ import annotations
import subprocess
import os
import logging
from pathlib import Path
from dotenv import load_dotenv
import argparse
from pydantic import BaseModel, Field, PrivateAttr, field_validator
from typing import Iterable, List, Union, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AuthenticationError(Exception):
    pass

class Immich(BaseModel):
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
            logger.error(f"Thumbnails directory {v} does not exist.")
            raise FileNotFoundError(f"Thumbnails directory {v} does not exist.")
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

    def should_ignore_file(self, file: Path) -> bool:
        if file.suffix.lstrip('.').lower() in self.ignore_extensions:
            logger.info(f"Ignoring file {file} due to extension.")
            return True
        if str(file) in self.ignore_paths:
            logger.info(f"Ignoring file {file} due to path.")
            return True
        if file.stat().st_size > self.large_file_size:
            logger.warning(f"File {file} is larger than {self.large_file_size} bytes and will be skipped.")
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

    def save_status_file(self, directory: Path, status: dict[str, str]):
        status_file = directory / 'upload_status.txt'
        logger.debug(f"Saving status file {status_file}")
        with status_file.open('w') as f:
            for filename, file_status in status.items():
                f.write(f'{filename}\t{file_status}\n')

    def upload_file(self, file: Path) -> bool:
        command = ["immich", "upload", file.as_posix()]
        try:
            subprocess.run(command, check=True)
            logger.info(f"Uploaded {file}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to upload {file}: {e}")
            return False

    def upload_files(self, recursive: bool = False):
        if not self._authenticated:
            self.authenticate()

        directories = [self.directory]
        if recursive:
            directories.extend([d for d in self.directory.rglob('*') if d.is_dir()])

        for directory in directories:
            status = self.load_status_file(directory)
            try:
                for file in directory.iterdir():
                    if not file.is_file():
                        continue

                    filename = file.name
                    if filename in status and status[filename] == 'success':
                        logger.debug(f"Skipping already uploaded file {file}")
                        continue
                    if self.should_ignore_file(file):
                        continue

                    success = self.upload_file(file)
                    status[filename] = 'success' if success else 'failed'
            finally:
                self.save_status_file(directory, status)

    def find_large_files(self, directory : Path | None = None, size : int = 1024 * 1024 * 100) -> list[Path]:
        """
        Only used for upload_directory()
        """
        if not directory:
            directory = self.directory
            
        large_files = []
        for file in directory.rglob("**/*"):
            if file.stat().st_size > size:
                large_files.append(file)
        return large_files

    def _compile_ignore_patterns(self, directory : Path) -> list[str]:
        """
        Only used for upload_directory()
        """
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

    def upload_directory(self, directory : Path | None = None, recursive : bool = True):
        """
        Not used, in favor of upload_files()

        This method uses immich to upload the entire directory. However, re-compiling hashes for
        every file is time consuming, and progress can't be resumed if terminated early. 
        """
        if not self._authenticated:
            self.authenticate()
            
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
    load_dotenv()

    url = os.getenv("IMMICH_URL")
    api_key = os.getenv("IMMICH_API_KEY")
    thumbnails_dir = os.getenv("CLOUD_THUMBNAILS_DIR")

    try:
        parser = argparse.ArgumentParser(description="Upload files to Immich.")
        parser.add_argument("--url", help="Immich URL", default=url)
        parser.add_argument("--api-key", help="Immich API key", default=api_key)
        parser.add_argument("--thumbnails-dir", '-d', help="Cloud thumbnails directory", default=thumbnails_dir)
        parser.add_argument("--ignore-extensions", "-e", help="Ignore files with these extensions", nargs='+')
        parser.add_argument('--ignore-paths', '-i', help="Ignore files with these paths", nargs='+')
        parser.add_argument('--group', '-g', action='store_true', help="Upload files as a group via immich. Kept for legacy reasons, or if immich optimizes their recursive upload feature.")
        args = parser.parse_args()

        if not args.url or not args.api_key or not args.thumbnails_dir:
            logger.error("IMMICH_URL, IMMICH_API_KEY, and CLOUD_THUMBNAILS_DIR must be set.")
            exit(1)

        immich = Immich(
            url=args.url,
            api_key=args.api_key,
            directory=Path(args.thumbnails_dir),
            ignore_extensions=args.ignore_extensions,
            ignore_paths=args.ignore_paths
        )

        if args.group:
            immich.upload_directory()
        else:
            immich.upload_files()
    except AuthenticationError:
        logger.error("Authentication failed. Check your API key and URL.")
    except KeyboardInterrupt:
        logger.info("Upload cancelled by user.")

if __name__ == "__main__":
    main()
