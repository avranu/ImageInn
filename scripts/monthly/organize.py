#!/usr/bin/env python3

import os
import re
import hashlib
import shutil
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class PXLFileOrganizer:
    def __init__(self, directory='.'):
        self.current_dir = Path(directory)

    def hash(self, filename : str | Path):
        """Calculate the MD5 hash of a file."""
        hash_md5 = hashlib.md5()
        with open(filename, "rb") as f:
            # Read the file in chunks to handle large files efficiently
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def organize_files(self):
        # Loop over all files starting with 'PXL_'
        files = [f for f in self.current_dir.iterdir() if f.is_file() and f.name.startswith('PXL_')]

        for file in files:
            self.process_file(file)

    def process_file(self, file : Path):
        filename = file.name

        # Extract the date part using regular expressions
        date_part = self.extract_date(filename)
        if not date_part:
            logger.info(f"Could not extract date from filename: {filename}")
            return

        year = date_part[:4]
        month = date_part[4:6]
        dir_name = f"{year}-{month}"
        target_dir = self.current_dir / dir_name

        # Create the target directory if it doesn't exist
        target_dir.mkdir(exist_ok=True)

        # Calculate the MD5 checksum of the source file
        src_hash = self.hash(file)

        # Initialize the target file path
        target_file = target_dir / filename

        # Handle potential filename collisions
        target_file = self.handle_collision(file, target_file, src_hash)

        if target_file is None:
            # File was deleted due to duplication
            return

        # Move the file to the target directory
        shutil.move(str(file), str(target_file))

        # Verify the moved file via checksum
        moved_hash = self.hash(target_file)
        if src_hash != moved_hash:
            logger.info(f"Checksum mismatch after moving {filename} to {target_file.name}")
        else:
            logger.info(f"Successfully moved {filename} to {target_file.relative_to(self.current_dir)}")

    def extract_date(self, filename : str | Path) -> str | None:
        match = re.match(r'^PXL_(\d{8})_', str(filename))
        if match:
            return match.group(1)
        else:
            return None

    def handle_collision(self, file : Path, target_file : Path, src_hash : str) -> Path | None:
        filename = file.name
        if target_file.exists():
            dest_md5 = self.hash(str(target_file))
            if src_hash == dest_md5:
                # Files are identical; delete the source file
                logger.info(f"Duplicate file found; deleting {filename}")
                file.unlink()
                return None  # Indicate that the file was handled
            else:
                # Files differ; find a new filename
                base = file.stem  # Filename without extension
                ext = file.suffix  # File extension including the dot
                i = 1
                while True:
                    new_filename = f"{base}_{i}{ext}"
                    new_target_file = target_file.parent / new_filename
                    if not new_target_file.exists():
                        target_file = new_target_file
                        logger.info(f"Renaming {filename} to {new_filename} due to collision")
                        break
                    else:
                        # Check if the existing file is identical
                        dest_md5 = self.hash(str(new_target_file))
                        if src_hash == dest_md5:
                            logger.info(f"Duplicate file found; deleting {filename}")
                            file.unlink()
                            return None  # File was deleted due to duplication
                    i += 1
                if not file.exists():
                    logger.warning(f"File {filename} may have been deleted due to duplication")
                    return None  # File was deleted due to duplication
        return target_file

if __name__ == "__main__":
    # Customize logger
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', handlers=[logging.StreamHandler()])
    organizer = PXLFileOrganizer()
    organizer.organize_files()
