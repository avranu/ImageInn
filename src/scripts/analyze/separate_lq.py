"""*********************************************************************************************************************
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    METADATA:                                                                                                         *
*                                                                                                                      *
*        File:    analyze.py                                                                                           *
*        Project: imageinn                                                                                             *
*        Version: 0.1.0                                                                                                *
*        Created: 2025-02-21                                                                                           *
*        Author:  Jess Mann                                                                                            *
*        Email:   jess.a.mann@gmail.com                                                                                *
*        Copyright (c) 2025 Jess Mann                                                                                  *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    LAST MODIFIED:                                                                                                    *
*                                                                                                                      *
*        2025-02-21     By Jess Mann                                                                                   *
*                                                                                                                      *
*********************************************************************************************************************"""
import re
from typing import Iterator
import rawpy
import numpy as np
from pathlib import Path
import logging
import sqlite3
from datetime import datetime
import argparse
from pydantic import BaseModel
from enum import Enum

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Threshold constants
DARK_DARKEST_THRESHOLD = 400
DARK_BRIGHTEST_THRESHOLD = 2000
DARK_AVERAGE_THRESHOLD = 500
BRIGHT_BRIGHTEST_THRESHOLD = 16383
BRIGHT_DARKEST_THRESHOLD = 4000
BRIGHT_AVERAGE_THRESHOLD = 12000

GLOBS = [
    '*.NEF',
    '*.ARW',
    '*.dng',
]

SKIP_MOVE_PATTERNS = [
    r'.*-HDR',
    r'.*-Edit',
]
SKIP_MOVE = [re.compile(p) for p in SKIP_MOVE_PATTERNS]

class QualityCategory(Enum):
    UNDEREXPOSED = "Underexposed"
    OVEREXPOSED = "Overexposed"
    NORMAL = "Normal"

class ImageRecord(BaseModel):
    file_path: str
    brightest_pixel: int
    darkest_pixel: int
    average_brightness: float
    quality_category: QualityCategory
    processed_at: datetime

class DatabaseHandler:
    """Handles SQLite operations for storing image data."""
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.connection: sqlite3.Connection | None = None
        self.connect()
        self.create_table()

    def connect(self) -> None:
        try:
            self.connection = sqlite3.connect(str(self.db_path))
        except sqlite3.Error as e:
            logger.error(f"Database connection error: {e}")
            raise

    def create_table(self) -> None:
        query = """
            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT UNIQUE,
                brightest_pixel INTEGER,
                darkest_pixel INTEGER,
                average_brightness REAL,
                quality_category TEXT,
                processed_at TEXT
            )
        """
        try:
            with self.connection:
                self.connection.execute(query)
        except sqlite3.Error as e:
            logger.error(f"Error creating table: {e}")
            raise

    def record_exists(self, file_path: str) -> bool:
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT 1 FROM images WHERE file_path = ?", (file_path,))
            return cursor.fetchone() is not None
        except sqlite3.Error as e:
            logger.error(f"Error checking record existence: {e}")
            return False

    def insert_record(self, record: ImageRecord) -> None:
        query = """
            INSERT INTO images (
                file_path, brightest_pixel, darkest_pixel,
                average_brightness, quality_category, processed_at
            ) VALUES (?, ?, ?, ?, ?, ?)
        """
        try:
            with self.connection:
                self.connection.execute(query, (
                    record.file_path,
                    record.brightest_pixel,
                    record.darkest_pixel,
                    record.average_brightness,
                    record.quality_category.value,
                    record.processed_at.isoformat()
                ))
        except sqlite3.Error as e:
            logger.error(f"Error inserting record for {record.file_path}: {e}")

class ImageAnalyzer:
    """Analyzes brightness properties of a  image."""
    def __init__(self, image_path: Path) -> None:
        self.image_path = image_path
        self.brightest_pixel: int | None = None
        self.darkest_pixel: int | None = None
        self.average_brightness: float | None = None

    def analyze(self) -> dict | None:
        try:
            raw = rawpy.imread(str(self.image_path))
            raw_image = raw.raw_image_visible.astype(np.uint16)
            self.brightest_pixel = int(np.max(raw_image))
            self.darkest_pixel = int(np.min(raw_image))
            self.average_brightness = float(np.mean(raw_image))
            return {
                "brightest_pixel": self.brightest_pixel,
                "darkest_pixel": self.darkest_pixel,
                "average_brightness": self.average_brightness,
            }
        except Exception as e:
            logger.error(f"Failed to process {self.image_path}: {e}")
            return None

class BaseProcessor:
    """Encapsulates file renaming logic."""
    def move_file(self, source: Path, destination: Path) -> bool:
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            source.rename(destination)
            logger.debug(f"Renamed {source.name} to {destination}")
            return True
        except Exception as e:
            logger.error(f"Error renaming {source.name} to {destination}: {e}")
        return False

class DirectoryProcessor(BaseProcessor):
    """Processes RAW images in a directory and stores results in a SQLite DB."""
    directory : Path
    db_handler : DatabaseHandler

    def __init__(self, directory: Path, db_handler: DatabaseHandler) -> None:
        self.directory = directory
        self.db_handler = db_handler
        self.subdirs = {
            QualityCategory.UNDEREXPOSED: self.directory / "LQ",
            QualityCategory.OVEREXPOSED: self.directory / "LQ"
        }
        for subdir in self.subdirs.values():
            subdir.mkdir(exist_ok=True)

    def should_process(self, filepath : Path) -> bool:
        if not filepath.is_file():
            return False
        
        for pattern in SKIP_MOVE:
            if pattern.match(str(filepath.absolute())):
                return False
        return True

    def yield_images(self, dir : Path) -> Iterator[Path]:
        for glob in GLOBS:
            for f in dir.glob(glob):
                if not self.should_process(f):
                    continue
                yield f

    def get_images(self, dir : Path) -> list[Path]:
        return list(self.yield_images(dir))

    def process_images(self) -> None:
        all_files = self.get_images(self.directory)
        
        if not all_files:
            logger.warning(f"No RAW files found in {self.directory}")
            return

        logger.info(f"Processing {len(all_files)} RAW files in {self.directory}")
        for nef_file in all_files:
            if self.db_handler.record_exists(str(nef_file)):
                logger.debug(f"Skipping already processed file: {nef_file.name}")
                continue

            analyzer = ImageAnalyzer(nef_file)
            result = analyzer.analyze()
            if not result:
                continue

            quality = self.determine_quality(result)
            if quality in self.subdirs:
                destination = self.subdirs[quality] / nef_file.name
                self.move_file(nef_file, destination)

                logger.info(
                    f"{nef_file.name}: Brightest={result['brightest_pixel']}, "
                    f"Darkest={result['darkest_pixel']}, Avg={result['average_brightness']:.2f}, "
                    f"Quality={quality.value}"
                )

            record = ImageRecord(
                file_path=str(nef_file),
                brightest_pixel=result["brightest_pixel"],
                darkest_pixel=result["darkest_pixel"],
                average_brightness=result["average_brightness"],
                quality_category=quality,
                processed_at=datetime.now()
            )
            self.db_handler.insert_record(record)

    def determine_quality(self, result: dict) -> QualityCategory:
        if result["brightest_pixel"] < DARK_BRIGHTEST_THRESHOLD and result["average_brightness"] < DARK_AVERAGE_THRESHOLD:
            return QualityCategory.UNDEREXPOSED
        if result["brightest_pixel"] >= BRIGHT_BRIGHTEST_THRESHOLD and result["darkest_pixel"] > BRIGHT_DARKEST_THRESHOLD and result["average_brightness"] > BRIGHT_AVERAGE_THRESHOLD:
            return QualityCategory.OVEREXPOSED
        return QualityCategory.NORMAL

def run_subdirs(parent_dir : Path, db_handler : DatabaseHandler):
    for directory in parent_dir.iterdir():
        if not directory.is_dir():
            continue

        logger.debug('Handling images in %s', directory)
        processor = DirectoryProcessor(directory, db_handler)
        processor.process_images()

class ArgumentNamespace(argparse.Namespace):
    directory: str
    db: str
    verbose : bool = False
    subdirs : bool = False

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze RAW images, categorize by brightness, and store results in a SQLite database."
    )
    parser.add_argument("directory", type=str, help="Path to the directory containing RAW images.")
    parser.add_argument("--db", type=str, default="image_data.db", help="Path to the SQLite database file.")
    parser.add_argument('--subdirs', action='store_true')
    parser.add_argument('--verbose', '-v', action='store_true')
    args = parser.parse_args(namespace=ArgumentNamespace)

    if args.verbose:
        logger.setLevel(logging.DEBUG)
            
    dir_path = Path(args.directory)
    if not dir_path.exists() or not dir_path.is_dir():
        logger.error(f"Invalid directory: {dir_path}")
        return

    db_handler = DatabaseHandler(Path(args.db))
    
    if args.subdirs:
        run_subdirs(dir_path, db_handler)
    else:
        processor = DirectoryProcessor(dir_path, db_handler)
        processor.process_images()

if __name__ == "__main__":
    main()
