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

import logging
from pathlib import Path
import logging
import argparse
from tqdm import tqdm
from pydantic import PrivateAttr, field_validator
from scripts import setup_logging
from scripts.exceptions import ShouldTerminateException
from scripts.lib.file_manager import StrPattern
from scripts.monthly.organize.base import FileOrganizer

logger = logging.getLogger(__name__)

class PixelFileOrganizer(FileOrganizer):
    """
    Organize files into monthly directories based on the filename.

    - Filenames are expected to start with 'PXL_' followed by an 8-digit date in the format 'YYYYMMDD'.
    - Files are moved to a directory named 'YYYY-MM' under the specified directory.
    - If a file with the same name already exists in the target directory, a unique filename is generated.
    """
    glob_pattern : str = 'PXL_*'

    @classmethod
    def get_default_filename_pattern(cls):
        return r'^PXL_(20\d{6})_'

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

        if not (matches := self.filename_match(filename)):
            raise ValueError(f"Invalid filename format: {filename}")

        # Subdir name
        date_part = matches.group(1)
        year = date_part[:4]
        month = date_part[4:6]
        dir_name = f"{year}/{year}-{month}"

        return dir_name

def main():
    logger = setup_logging()

    # Set up argument parser
    parser = argparse.ArgumentParser(description='Organize PXL_ files into monthly directories.')
    parser.add_argument('-d', '--directory', default='.', help='Directory to organize (default: current directory)')
    parser.add_argument('-t', '--target', default=None, help='Target directory to move files to')
    parser.add_argument('-g', '--glob-pattern', default='PXL_', help='Glob pattern to use when searching for files (default: PXL_)')
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
        glob_pattern     = args.glob_pattern,
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

if __name__ == "__main__":
    main()
