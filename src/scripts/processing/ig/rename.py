# Single use script to rename scans so they are ordered correctly.
# This script can be deleted at any time with no consequences.

import re
from pathlib import Path

def pad_photo_numbers(directory: Path) -> None:
    """
    Rename files in the given directory to ensure the middle numeric group is 3 digits (zero-padded).

    Example:
        HRSH PhotoBox - 9 - 01.tif -> HRSH PhotoBox - 009 - 01.tif
    """
    pattern = re.compile(r"(.*?PhotoBox\s*-\s*)(\d{1,2})(\s*-\s*\d+)(\.\w+)", re.IGNORECASE)

    for file in sorted(directory.iterdir()):
        if not file.is_file():
            continue

        match = pattern.match(file.name)
        if not match:
            continue

        prefix, number, suffix, ext = match.groups()
        padded_number = number.zfill(3)
        new_name = f"{prefix}{padded_number}{suffix}{ext}"
        new_path = file.with_name(new_name)

        if new_path != file:
            print(f"Renaming: {file.name} -> {new_path.name}")
            file.rename(new_path)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Pad middle number in HRSH PhotoBox filenames to 3 digits.")
    parser.add_argument("directory", type=Path, help="Path to the folder containing the files to rename.")
    args = parser.parse_args()

    pad_photo_numbers(args.directory)
