#!/usr/bin/env python3

import os
import re
import hashlib
import shutil
from pathlib import Path

def md5sum(filename):
    """Calculate the MD5 hash of a file."""
    hash_md5 = hashlib.md5()
    with open(filename, "rb") as f:
        # Read the file in chunks to handle large files efficiently
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def main():
    # Get the current directory
    current_dir = Path('.')

    # Loop over all files starting with 'PXL_'
    files = [f for f in current_dir.iterdir() if f.is_file() and f.name.startswith('PXL_')]

    for file in files:
        filename = file.name

        # Extract the date part using regular expressions
        match = re.match(r'^PXL_(\d{8})_', filename)
        if not match:
            print(f"Could not extract date from filename: {filename}")
            continue

        date_part = match.group(1)
        year = date_part[:4]
        month = date_part[4:6]
        dir_name = f"{year}-{month}"
        target_dir = current_dir / dir_name

        # Create the target directory if it doesn't exist
        target_dir.mkdir(exist_ok=True)

        target_file = target_dir / filename

        if not target_file.exists():
            # No collision; move the file
            shutil.move(str(file), str(target_file))
        else:
            # Collision detected; compare MD5 hashes
            src_md5 = md5sum(str(file))
            dest_md5 = md5sum(str(target_file))
            if src_md5 == dest_md5:
                # Files are identical; delete the source file
                print(f"Duplicate file found; deleting {filename}")
                file.unlink()
            else:
                # Files differ; rename the source file
                base = file.stem  # Filename without extension
                ext = file.suffix  # File extension including the dot

                i = 1
                # Generate a new filename until one doesn't exist
                while True:
                    new_filename = f"{base}_{i}{ext}"
                    new_target_file = target_dir / new_filename
                    if not new_target_file.exists():
                        break
                    i += 1

                print(f"Renaming {filename} to {new_filename} due to collision")
                shutil.move(str(file), str(new_target_file))

if __name__ == "__main__":
    main()
