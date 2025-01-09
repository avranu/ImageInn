"""*********************************************************************************************************************
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    METADATA:                                                                                                         *
*                                                                                                                      *
*        File:    distribute_trash.py                                                                                  *
*        Project: imageinn                                                                                             *
*        Version: 0.1.0                                                                                                *
*        Created: 2024-12-12                                                                                           *
*        Author:  Jess Mann                                                                                            *
*        Email:   jess.a.mann@gmail.com                                                                                *
*        Copyright (c) 2024 Jess Mann                                                                                  *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    LAST MODIFIED:                                                                                                    *
*                                                                                                                      *
*        2024-12-12     By Jess Mann                                                                                   *
*                                                                                                                      *
*********************************************************************************************************************"""
import os
import logging
from pathlib import Path
import sys
from alive_progress import alive_it, alive_bar

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def get_last_trash_dir(base_dir : Path) -> int:
    """
    Get the last used subdirectory number in the given directory.

    Args:
        base_dir (Path): The base directory to scan for subdirectories.

    Returns:
        int: The last used subdirectory as a number.
    """
    if not base_dir.is_dir():
        logger.error(f"{base_dir} is not a valid directory.")
        return 0

    logger.debug('Counting already existing subdirs from previous run.')
    subdirs = [int(d.name) for d in base_dir.iterdir() if d.is_dir() and d.name.isdigit()]
    return max(subdirs, default=0)

def distribute_trash(base_dir: Path, files_per_dir: int = 1000):
    """
    Organizes files in the given directory and its subdirectories into
    subdirectories containing at most `files_per_dir` files each.

    Args:
        base_dir (Path): The base directory to scan for files.
        files_per_dir (int): Maximum number of files per subdirectory.
    """
    if not base_dir.is_dir():
        logger.error(f"{base_dir} is not a valid directory.")
        return

    logger.info('Distributing files in %s into groups of %d', base_dir, files_per_dir)

    # Create subdirectories and distribute files
    dir_counter = get_last_trash_dir(base_dir) + 1
    file_counter = 0
    current_subdir = base_dir / str(dir_counter)
    current_subdir.mkdir(exist_ok=True)

    with alive_bar(title="Distributing files", unit='files', unknown='waves') as progress_bar:
        for file in base_dir.rglob("*"):
            if not file.is_file():
                continue

            # Skip files in a numbered subdir
            if file.parent.name.isdigit():
                continue
            
            if file_counter >= files_per_dir:
                # Start a new subdirectory
                dir_counter += 1
                logger.info('Starting new subdir: %d', dir_counter)
                current_subdir = base_dir / str(dir_counter)
                current_subdir.mkdir(exist_ok=True)
                file_counter = 0

            # Resolve naming conflicts by appending a number if needed
            destination = current_subdir / file.name
            counter = 1
            while destination.exists():
                destination = current_subdir / f"{file.stem}_{counter}{file.suffix}"
                counter += 1

            # Move the file to the current subdirectory
            try:
                file.rename(destination)
                file_counter += 1
                progress_bar()
            except Exception as e:
                logger.error(f"Failed to move {file} to {destination}: {e}")

    logger.info("File distribution complete.")

if __name__ == "__main__":
    base_directory = Path.cwd() / '.trash'
    if not base_directory.exists():
        logger.error(f"Directory {base_directory} does not exist.")
        sys.exit(1)
        
    distribute_trash(base_directory)
