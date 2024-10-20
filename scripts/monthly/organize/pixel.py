"""*********************************************************************************************************************
*                                                                                                                      *
*                                                                                                                      *
    This script organizes files into monthly directories based on the filename. It is useful for dumping
    photos from a phone or camera into a single directory and organizing them later.

    Ideally, it should be run as a cron job to automatically organize files on a regular basis.

    See also upload.py for a script that should run after this one to upload those files to immich.

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
import sys
import os

# Add the root directory of the project to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import re
from pathlib import Path
import logging
import argparse
from tqdm import tqdm
from pydantic import PrivateAttr, field_validator
from scripts import setup_logging
from scripts.exceptions import ShouldTerminateException
from scripts.monthly.organize.base import FileOrganizer

logger = setup_logging()

class PixelFileOrganizer(FileOrganizer):
    """
    Organize files into monthly directories based on the filename.

    - Filenames are expected to start with 'PXL_' followed by an 8-digit date in the format 'YYYYMMDD'.
    - Files are moved to a directory named 'YYYY-MM' under the specified directory.
    - If a file with the same name already exists in the target directory, a unique filename is generated.
    """
    # Private attributes
    _filename_pattern : re.Pattern | None = PrivateAttr(default=None)

    @property
    def filename_pattern(self) -> re.Pattern:
        if not self._filename_pattern:
            self._filename_pattern = re.compile(rf'^{re.escape(self.file_prefix)}(20\d{{6}})_.*\.jpg$')
        return self._filename_pattern

    def find_subdir(self, filepath: Path) -> str:
        """
        Find the subdirectory for a file based on its filename.

        Args:
            filename: The file path to extract the date from.

        Returns:
            The name of the proposed subdirectory.

        Raises:
            ValueError: If the filename does not match the expected format.
        """
        filename = filepath.name

        if not (match := self.filename_pattern.match(filename)):
            raise ValueError(f"Invalid filename format: {filename}")

        # Subdir name
        date_part = match.group(1)
        year = date_part[:4]
        month = date_part[4:6]
        dir_name = f"{year}/{year}-{month}"

        return dir_name

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Organize PXL_ files into monthly directories.')
    parser.add_argument('-d', '--directory', default='.', help='Directory to organize (default: current directory)')
    parser.add_argument('-t', '--target', default=None, help='Target directory to move files to')
    parser.add_argument('-p', '--prefix', default='PXL_', help='File prefix to match (default: PXL_)')
    parser.add_argument('-l', '--limit', type=int, default=-1, help='Limit the number of files to process')
    parser.add_argument('-v', '--verbose', action='store_true', help='Increase verbosity')
    parser.add_argument('--skip-collision', action='store_true', help='Skip moving files on collision')
    parser.add_argument('--skip-hash', action='store_true', help='Skip verifying file hashes')
    parser.add_argument('--dry-run', action='store_true', help='Simulate the file organization without moving files')
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    organizer = PixelFileOrganizer(
        directory       = args.directory,
        target_directory= args.target,
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
