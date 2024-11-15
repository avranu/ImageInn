"""*********************************************************************************************************************
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    METADATA:                                                                                                         *
*                                                                                                                      *
*        File:    direct.py                                                                                            *
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
*        2024-10-29     By Jess Mann                                                                                   *
*                                                                                                                      *
*********************************************************************************************************************"""
#!/usr/bin/env python3
"""
Upload files to Immich.

Deprecated. Another approach, competing with progressive.py

Version 1.0
Date: 2024-09-20
Status: Working

Example:
    >>> python direct.py
    >>> python direct.py -d /mnt/i/Phone
    # bash_aliases defines `upload` to run this script for the current dir
    >>> upload
"""
from __future__ import annotations
import logging
import os
import sys

# Add the root directory of the project to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

import subprocess
from pathlib import Path
from dotenv import load_dotenv
import argparse
from scripts import setup_logging
from scripts.thumbnails.upload.exceptions import AuthenticationError
from scripts.thumbnails.upload.interface import ImmichInterface

logger = setup_logging()

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
            if self.file_size(file) > size:
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
            logger.error("File upload failed: %s", e)
def main():
    """
    Called when the script is run from the command line. Parses arguments and uploads files to Immich.
    """
    try:
        logger.warning('Using ImmichDirectUploader is not recommended. Use ImmichProgressiveUploader instead.')

        load_dotenv()

        url = os.getenv("IMMICH_URL")
        api_key = os.getenv("IMMICH_API_KEY")
        thumbnails_dir = os.getenv("IMAGEINN_THUMBNAILS_DIR", '.')

        parser = argparse.ArgumentParser(description="Upload files to Immich.")
        parser.add_argument("--url", help="Immich URL", default=url)
        parser.add_argument("--api-key", help="Immich API key", default=api_key)
        parser.add_argument("--thumbnails-dir", '-d', help="Cloud thumbnails directory", default=thumbnails_dir)
        parser.add_argument("--ignore-extensions", "-e", help="Ignore files with these extensions", nargs='+')
        parser.add_argument('--ignore-paths', '-i', help="Ignore files with these paths", nargs='+')
        parser.add_argument("--verbose", "-v", help="Enable verbose logging", action="store_true")
        args = parser.parse_args()

        if args.verbose:
            logger.setLevel(logging.DEBUG)

        if not args.url or not args.api_key or not args.thumbnails_dir:
            logger.error("IMMICH_URL, IMMICH_API_KEY, and IMAGEINN_THUMBNAILS_DIR must be set.")
            sys.exit(1)

        immich = ImmichDirectUploader(
            url=args.url,
            api_key=args.api_key,
            directory=Path(args.thumbnails_dir),
            ignore_extensions=args.ignore_extensions,
            ignore_paths=args.ignore_paths
        )
        immich.upload()

    except AuthenticationError:
        logger.error("Authentication failed. Check your API key and URL.")
    except KeyboardInterrupt:
        logger.info("Upload cancelled by user.")

if __name__ == "__main__":
    main()