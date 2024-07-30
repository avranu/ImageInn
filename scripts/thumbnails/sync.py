import os
import logging
import hashlib
from pathlib import Path
from datetime import datetime
import shutil
import subprocess
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class JPGSyncer:
    source_dir : Path
    target_dir : Path
    dry_run : bool
    
    def __init__(self, source_dir: Path, target_dir: Path, dry_run : bool = False):
        self.source_dir = source_dir
        self.target_dir = target_dir
        self.dry_run = dry_run

    def find_jpg_files(self):
        return [file for file in self.source_dir.rglob("*.jpg", case_sensitive=False)]

    def get_file_structure(self, file: Path) -> Path:
        mod_time = datetime.fromtimestamp(file.stat().st_mtime)
        year = mod_time.strftime("%Y")
        date = mod_time.strftime("%Y-%m-%d")
        return self.target_dir / year / date / file.name

    def generate_file_hash(self, file: Path) -> str:
        hash_func = hashlib.sha256()
        with file.open('rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                hash_func.update(chunk)
        return hash_func.hexdigest()

    def check_and_copy(self, src: Path, dest: Path) -> bool:
        if dest.exists():
            if self.generate_file_hash(src) == self.generate_file_hash(dest):
                logger.debug(f"Skipping {src} as it already exists with the same content.")
                return False

            dest = self.resolve_collision(dest)
                
        return self.copy_with_rsync(src, dest)

    def resolve_collision(self, dest: Path) -> Path:
        dest_dir = dest.parent
        dest_stem = dest.stem
        dest_suffix = dest.suffix
        i = 1
        while dest.exists():
            dest = dest_dir / f"{dest_stem}-{i}{dest_suffix}"
            i += 1
        return dest

    def copy_with_rsync(self, src: Path, dest: Path) -> bool:
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

    def sync(self):
        jpg_files = self.find_jpg_files()
        total = len(jpg_files)

        if not total:
            logger.info("No JPG files found to sync.")
            return
        logger.info('%s JPG files found.', total)
        
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(tqdm(executor.map(self.process_file, jpg_files), total=total, desc="Syncing JPG files"))

        logger.info("Sync completed on %s files.", total)

    def process_file(self, file: Path) -> bool:
        try:
            dest_path = self.get_file_structure(file)
            return self.check_and_copy(file, dest_path)
        except Exception as e:
            logger.error(f"Failed to process {file}: {e}")
        return False

def main():
    import argparse

    # Load default target from environment variable CLOUD_THUMBNAILS_DIR
    target_dir = os.getenv("CLOUD_THUMBNAILS_DIR")

    try:
        parser = argparse.ArgumentParser(description="Sync JPG files with defined structure.")
        parser.add_argument("source", type=Path, help="Source directory to search for JPG files.")
        if target_dir:
            parser.add_argument("--target", '-t', type=Path, default=Path(target_dir), help="Target directory to copy JPG files to.")
        else:
            parser.add_argument("--target", '-t', type=Path, help="Target directory to copy JPG files to.")
        parser.add_argument("--dry-run", action="store_true", help="Perform a dry run without making any changes.")
        args = parser.parse_args()

        # Target is required
        if not args.target:
            parser.error("Target directory is required. Set it using the CLOUD_THUMBNAILS_DIR environment variable, or pass it as an argument using the --target option.")

        syncer = JPGSyncer(args.source, args.target, args.dry_run)
        syncer.sync()
    except KeyboardInterrupt:
        logger.info("Sync interrupted by user.")

if __name__ == "__main__":
    main()