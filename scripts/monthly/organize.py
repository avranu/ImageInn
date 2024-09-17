#!/usr/bin/env python3

import os
import re
import hashlib
import shutil
from pathlib import Path
import logging
import argparse
from functools import lru_cache
import sys
from typing import Literal
from tqdm import tqdm
from scripts.monthly.exceptions import ShouldTerminateException, OneFileException, DuplicationHandledException

logger = logging.getLogger(__name__)

class FileOrganizer:
    directory : Path
    pattern : str
    dry_run : bool
    
    def __init__(self, directory: str = '.', pattern: str = 'PXL_*', dry_run: bool = False):
        self.directory = Path(directory)
        self.pattern = pattern
        self.dry_run = dry_run

    @lru_cache(maxsize=1024)
    def hash(self, filename: str | Path) -> str:
        """Calculate the MD5 hash of a file."""
        try:
            hash_md5 = hashlib.md5()
            with open(filename, "rb") as f:
                # Read the file in chunks to handle large files efficiently
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except IOError as e:
            raise OneFileException(f"Error reading file {filename}") from e

    def organize_files(self) -> int:
        # Loop over all files matching the pattern
        try:
            files = [f for f in self.directory.glob(self.pattern) if f.is_file()]
        except Exception as e:
            logger.error(f"Error accessing directory {self.directory}: {e}")
            return 0

        paths : list[Path] = []
        for file in tqdm(files, desc='Processing files'):
            try:
                result = self.process_file(file)
                paths.append(result) if result else None
            except DuplicationHandledException as e:
                logger.debug(f"Duplicate file {file} handled")
            except OneFileException as e:
                logger.error(f"Error processing file {file}: {e}")

        return len(paths)

    def process_file(self, file: Path) -> Path | None:
        filename = file.name

        # Create the subdir
        target_dir = self.find_subdir(filename)

        # Handle potential filename collisions
        target_file = self.handle_collision(file, target_dir / filename)

        return self.move_file(file, target_file)

    def find_subdir(self, filename: str | Path) -> Path:
        if isinstance(filename, Path):
            filename = filename.name
            
        if not (match := re.match(r'^PXL_(\d{8})_', str(filename))):
            raise OneFileException(f"Invalid filename format: {filename}")

        # Subdir name
        date_part = match.group(1)
        year = date_part[:4]
        month = date_part[4:6]
        dir_name = f"{year}-{month}"

        # Turn into path
        return self.mkdir(self.directory / dir_name) 

    def mkdir(self, directory: Path, message: str | None = "Created directory") -> Path:
        try:
            if not self.dry_run:
                directory.mkdir(exist_ok=True)
            if message:
                logger.info(f"{message}: {directory.relative_to(self.directory)}")
        except Exception as e:
            raise ShouldTerminateException(f'Error creating directory: {directory}') from e

        return directory
        
    def delete_file(self, file: Path, message : str = "Deleted file") -> bool:
        try:
            if not self.dry_run:
                file.unlink()
            logger.info(f"{message}: {file}")
        except Exception as e:
            raise OneFileException('Error deleting file') from e

        return not file.exists()

    def move_file(self, source: Path, destination: Path, message : str | None = "Moved file") -> Path:
        source_hash = self.hash(source)
        
        if not self.dry_run:
            try:
                shutil.move(str(source), str(destination))
            except Exception as e:
                raise OneFileException(f'Error moving file {source} to {destination}') from e

            destination_hash = self.hash(destination)
            if source_hash != destination_hash:
                logger.critical(f"Checksum mismatch after moving {source} to {destination}")
                raise ShouldTerminateException('Checksum mismatch after moving')

            if message:
                logger.info(f"{message}: {source} to {destination.relative_to(self.directory)}")
            
        return destination

    def handle_single_conflict(self, source_file : Path, destination: Path) -> Path | Literal[False]:
        if not destination.exists():
            # No conflict; return the target file
            return destination
        
        if self.hashes_match(source_file, destination):
            # Files are identical; delete the source file
            self.delete_file(source_file, "Duplicate file found; deleted")
            raise DuplicationHandledException(f"Duplicate file {source_file} handled")

        return False

    def hashes_match(self, source_file : Path, destination: Path) -> bool:
        if not destination.exists():
            return False
                
        source_hash = self.hash(source_file)
        destination_hash = self.hash(destination)

        return source_hash == destination_hash

    def handle_collision(self, file: Path, target_file: Path, max_attempts : int = 1000) -> Path:
        if (result := self.handle_single_conflict(file, target_file)):
            # A viable path was found
            return result
        
        # Files differ; find a new filename
        base = file.stem  # Filename without extension
        ext = file.suffix  # File extension including the dot
        
        for i in range(max_attempts):
            new_target_file = target_file.parent / f"{base}_{i}{ext}"
            
            if (result := self.handle_single_conflict(file, new_target_file)):
                # A viable path was found
                return result

        raise OneFileException(f"Could not find a unique filename for {file}")

def main():
    # Customize logger
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    
    try:
        # Set up argument parser
        parser = argparse.ArgumentParser(description='Organize PXL_ files into monthly directories.')
        parser.add_argument('-d', '--directory', default='.', help='Directory to organize (default: current directory)')
        parser.add_argument('-p', '--pattern', default='PXL_*', help='File pattern to match (default: PXL_*)')
        parser.add_argument('--dry-run', action='store_true', help='Simulate the file organization without moving files')
        parser.add_argument('-v', '--verbose', action='store_true', help='Increase verbosity')
        args = parser.parse_args()

        if args.verbose:
            logger.setLevel(logging.DEBUG)

        organizer = FileOrganizer(directory=args.directory, pattern=args.pattern, dry_run=args.dry_run)

        count = organizer.organize_files()
        logger.info(f"Organized {count} files")
    except ShouldTerminateException as e:
        logger.critical(f"Critical error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.warning("Operation interrupted by user")
        sys.exit(1)

if __name__ == "__main__":
    main()
