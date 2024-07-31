"""
Sync JPG files to a thumbnails directory, so that there are no duplicates.

This script is useful for collecting all the jpg files scattered throughout a filesystem so that they can be 
uploaded to a cloud provider without making a mess.
"""
from __future__ import annotations
import os
import logging
import hashlib
from pathlib import Path
from datetime import datetime
import shutil
import subprocess
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor
import argparse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class JPGSyncer:
    target_dir: Path
    dry_run: bool
    threads : int

    def __init__(self, target_dir: Path, dry_run: bool = False, threads : int = 4):
        self.target_dir = target_dir
        self.dry_run = dry_run
        self.threads = threads

    def find_jpg_files(self, source_dir: Path) -> list[Path]:
        """
        Find all JPG files in the source directory.

        Args:
            source_dir (Path): Source directory to search for JPG files.

        Returns:
            list[Path]: List of JPG files found in the source directory.
        """
        jpg_files = []
        for file in source_dir.rglob("*"):
            if file.suffix.lower() == ".jpg":
                dest_path = self.get_file_structure(file)
                if not self.should_skip_file(file, dest_path):
                    jpg_files.append(file)
        return jpg_files

    def get_file_structure(self, file: Path) -> Path:
        """
        Generate the target directory structure for the file.

        Args:
            file (Path): File to generate the target directory structure for.

        Returns:
            Path: Absolute path for the target file.
        """
        mod_time = datetime.fromtimestamp(file.stat().st_mtime)
        year = mod_time.strftime("%Y")
        date = mod_time.strftime("%Y-%m-%d")
        return self.target_dir / year / date / file.name

    def generate_file_hash(self, file: Path) -> str:
        """
        Generate a SHA-256 hash for the file.

        Args:
            file (Path): File to generate the hash for.

        Returns:
            str: SHA-256 hash for the
        """
        hash_func = hashlib.sha256()
        with file.open('rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                hash_func.update(chunk)
        return hash_func.hexdigest()

    def should_skip_file(self, src: Path, dest: Path) -> bool:
        """
        Check if the file should be skipped based on the destination file.

        Args:
            src (Path): Source file to check.
            dest (Path): Destination file to check.

        Returns:
            bool: True if the file should be skipped, False otherwise.
        """
        if dest.exists() and self.generate_file_hash(src) == self.generate_file_hash(dest):
            logger.debug(f"Skipping {src} as it already exists with the same content.")
            return True
        return False

    def get_filename(self, src: Path, dest: Path) -> Path | None:
        """
        Get the destination filename for the source file.

        Args:
            src (Path): Source file to get the destination filename for.
            dest (Path): Destination file to check for collisions.

        Returns:
            Path | None: Destination filename if it should be copied, None otherwise.
        """
        if self.should_skip_file(src, dest):
            return None
        return self.resolve_collision(dest) if dest.exists() else dest

    def check_and_copy(self, src: Path, dest: Path) -> bool:
        """
        Check if the file should be copied and copy it if necessary.

        Args:
            src (Path): Source file to copy.
            dest (Path): Destination file to copy to.

        Returns:
            bool: True if the file was copied successfully, False otherwise.
        """
        destination = self.get_filename(src, dest)

        if not destination:
            return True

        # If windows, rsync isn't available, so copy with shutil
        if os.name == 'nt':
            return self.copy_with_shutil(src, destination)
                
        return self.copy_with_rsync(src, destination)

    def resolve_collision(self, dest: Path) -> Path:
        """
        Resolve filename collisions by appending a number to the filename.

        Args:
            dest (Path): Destination file to resolve collisions for.

        Returns:
            Path: Destination filename without collisions.
        """
        dest_dir = dest.parent
        dest_stem = dest.stem
        dest_suffix = dest.suffix
        i = 1
        while dest.exists():
            dest = dest_dir / f"{dest_stem}-{i}{dest_suffix}"
            i += 1
        return dest

    def copy_with_rsync(self, src: Path, dest: Path) -> bool:
        """
        Copy the file using rsync.

        Args:
            src (Path): Source file to copy.

        Returns:
            bool: True if the file was copied successfully, False otherwise.
        """
        if self.dry_run:
            logger.info(f"Copied {src} to {dest}")
            return True
        
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["rsync", "-aq", src.as_posix(), dest.as_posix()], check=True)
            logger.debug(f"Copied {src} to {dest}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to copy {src} to {dest}: {e}")
        return False

    def copy_with_shutil(self, src: Path, dest: Path) -> bool:
        """
        Copy the file using shutil.

        Args:
            src (Path): Source file to copy.

        Returns:
            bool: True if the file was copied successfully, False otherwise.
        """
        if self.dry_run:
            logger.info(f"Copied {src} to {dest}")
            return True
        
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            logger.debug(f"Copied {src} to {dest}")
            return True
        except Exception as e:
            logger.error(f"Failed to copy {src} to {dest}: {e}")
        return False

    def sync(self, source_dirs: list[Path]):
        """
        Sync JPG files from the source directories to the target directory.

        Args:
            source_dirs (list[Path]): Source directories to search for JPG files.
        """
        jpg_files = []
        for source_dir in source_dirs:
            jpg_files.extend(self.find_jpg_files(source_dir))
        
        total = len(jpg_files)

        if not total:
            logger.info("No JPG files found to sync.")
            return
        logger.info('%s JPG files found.', total)
        
        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            list(tqdm(executor.map(self.process_file, jpg_files), total=total, desc="Syncing JPG files"))

        logger.info("Sync completed on %s files.", total)

    def process_file(self, file: Path) -> bool:
        """
        Process a single file by copying it to the target directory.

        Args:
            file (Path): File to process.

        Returns:
            bool: True if the file was processed successfully, False otherwise.
        """
        try:
            dest_path = self.get_file_structure(file)
            return self.check_and_copy(file, dest_path)
        except Exception as e:
            logger.error(f"Failed to process {file}: {e}")
        return False

def main():
    # Load default target from environment variable CLOUD_THUMBNAILS_DIR
    target_dir = os.getenv("CLOUD_THUMBNAILS_DIR")

    try:
        parser = argparse.ArgumentParser(description="Sync JPG files with defined structure.")
        parser.add_argument("sources", type=Path, nargs='+', help="Source directories to search for JPG files.")
        if target_dir:
            parser.add_argument("--target", '-t', type=Path, default=Path(target_dir), help="Target directory to copy JPG files to.")
        else:
            parser.add_argument("--target", '-t', type=Path, help="Target directory to copy JPG files to.")
        parser.add_argument('--threads', '-w', type=int, default=4, help="Number of threads to use for processing files.")
        parser.add_argument("--dry-run", action="store_true", help="Perform a dry run without making any changes.")
        args = parser.parse_args()

        # Target is required
        if not args.target:
            parser.error("Target directory is required. Set it using the CLOUD_THUMBNAILS_DIR environment variable, or pass it as an argument using the --target option.")

        syncer = JPGSyncer(args.target, args.dry_run, args.threads)
        syncer.sync(args.sources)
    except KeyboardInterrupt:
        logger.info("Sync interrupted by user.")

if __name__ == "__main__":
    main()