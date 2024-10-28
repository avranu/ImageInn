"""*********************************************************************************************************************
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    METADATA:                                                                                                         *
*                                                                                                                      *
*        File:    separate_raws.py                                                                                     *
*        Project: imageinn                                                                                             *
*        Version: 0.1.0                                                                                                *
*        Created: 2024-10-28                                                                                           *
*        Author:  Jess Mann                                                                                            *
*        Email:   jess.a.mann@gmail.com                                                                                *
*        Copyright (c) 2024 Jess Mann                                                                                  *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    LAST MODIFIED:                                                                                                    *
*                                                                                                                      *
*        2024-10-28     By Jess Mann                                                                                   *
*                                                                                                                      *
*********************************************************************************************************************"""
import os
import sys
import argparse
import logging
from pathlib import Path
import shutil
import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def move_raw_files_with_matching_jpg(source_dir, target_dir, dry_run=False, limit=-1, verbose=False):
    if verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    raw_extensions = ['.nef', '.arw']
    files_processed = 0

    # Ensure the target directory exists
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    source_dir = Path(source_dir)
    if not source_dir.exists():
        logger.error(f"Source directory {source_dir} does not exist.")
        sys.exit(1)

    for raw_file in source_dir.rglob('*'):
        if raw_file.is_file() and raw_file.suffix.lower() in raw_extensions:
            # Check for matching JPG file
            jpg_file = raw_file.with_suffix('.jpg')
            if not jpg_file.exists():
                continue
            
            # Determine the date from the file's modification time
            mod_time = datetime.datetime.fromtimestamp(raw_file.stat().st_mtime)
            dest_subdir = mod_time.strftime('%Y/%Y-%m-%d')
            dest_dir = target_dir / dest_subdir
            dest_dir.mkdir(parents=True, exist_ok=True)

            # Handle potential filename collisions
            dest_file = dest_dir / raw_file.name
            if dest_file.exists():
                base_name = raw_file.stem
                extension = raw_file.suffix
                counter = 1
                while True:
                    new_name = f"{base_name}_{counter}{extension}"
                    dest_file = dest_dir / new_name
                    if not dest_file.exists():
                        break
                    counter += 1

            # Move the RAW file
            try:
                if raw_file.resolve() == dest_file.resolve():
                    logger.warning(f"Source and destination are the same file: {raw_file}")
                    continue
                if dry_run:
                    logger.info(f"Dry run: Would move {raw_file} to {dest_file}")
                else:
                    shutil.move(str(raw_file), str(dest_file))
                    logger.info(f"Moved {raw_file} to {dest_file}")
                files_processed += 1
                if limit > 0 and files_processed >= limit:
                    logger.info(f"Limit of {limit} files reached.")
                    break
            except Exception as e:
                logger.error(f"Error moving {raw_file} to {dest_file}: {e}")

    if files_processed == 0:
        logger.info("No files processed.")
    else:
        logger.info(f"Processed {files_processed} files.")

def main():
    parser = argparse.ArgumentParser(description='Move RAW files with matching JPG files.')
    parser.add_argument('-s', '--source', default='.', help='Source directory to search for files (default: current directory)')
    parser.add_argument('-t', '--target', default='/mnt/p/', help='Target directory to move files to (default: /mnt/p/)')
    parser.add_argument('-n', '--dry-run', action='store_true', help='Perform a dry run without moving files')
    parser.add_argument('-v', '--verbose', action='store_true', help='Increase verbosity')
    parser.add_argument('-l', '--limit', type=int, default=-1, help='Limit the number of files to process')
    args = parser.parse_args()

    move_raw_files_with_matching_jpg(
        source_dir=args.source,
        target_dir=args.target,
        dry_run=args.dry_run,
        limit=args.limit,
        verbose=args.verbose
    )

if __name__ == '__main__':
    main()