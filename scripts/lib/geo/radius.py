"""*********************************************************************************************************************
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    METADATA:                                                                                                         *
*                                                                                                                      *
*        File:    radius.py                                                                                            *
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
from __future__ import annotations
import os
import sys
import math
import shutil
import logging
import sqlite3
import subprocess
import json
import re
import argparse
import colorlog
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator
from pathlib import Path
from typing import Tuple, Optional, Iterator
from datetime import datetime
from decimal import Decimal, getcontext
from alive_progress import alive_bar

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent

class ExifDataExtractor:
    """Class to extract and parse GPS data from image files."""

    def __init__(self):
        if not shutil.which('exiftool'):
            logger.error("ExifTool is not installed. Please install ExifTool to proceed.")
            sys.exit(1)
        logger.info("ExifTool is installed and ready to use.")

    def get_gps_data(self, file_path: Path) -> Tuple[Optional[Decimal], Optional[Decimal]]:
        """Extract GPS data from image file using ExifTool."""
        try:
            output = subprocess.check_output(
                ['exiftool', '-GPSLatitude', '-GPSLongitude', '-GPSPosition', '-j', str(file_path)],
                stderr=subprocess.STDOUT
            )
            data = json.loads(output.decode('utf-8'))[0]
            lat = data.get('GPSLatitude')
            lon = data.get('GPSLongitude')

            if lat is not None and lon is not None:
                lat = self._convert_to_decimal(lat)
                lon = self._convert_to_decimal(lon)
                return lat, lon
            else:
                gps_position = data.get('GPSPosition')
                if gps_position:
                    lat, lon = self._parse_gps_position(gps_position)
                    return lat, lon
            return None, None
        except subprocess.CalledProcessError as e:
            logger.error(f"ExifTool error on file {file_path}: {e}")
            return None, None
        except Exception as e:
            logger.error(f"Error extracting GPS data from {file_path}: {e}")
            return None, None

    def _convert_to_decimal(self, coord) -> Optional[Decimal]:
        """Convert coordinate to decimal degrees if necessary."""
        if isinstance(coord, (float, int)):
            return Decimal(str(coord))
        elif isinstance(coord, str):
            return self._parse_dms(coord)
        else:
            logger.error(f"Unknown coordinate format: {coord}")
            return None

    def _parse_dms(self, dms_str: str) -> Optional[Decimal]:
        """Parse DMS (degrees, minutes, seconds) string to decimal degrees."""
        try:
            pattern = r'(\d+)\s*deg\s*(\d+)\'\s*([\d\.]+)"\s*([NSEW])'
            match = re.match(pattern, dms_str)
            if not match:
                logger.error(f"Invalid DMS format: {dms_str}")
                return None
            degrees, minutes, seconds, direction = match.groups()
            degrees = Decimal(degrees)
            minutes = Decimal(minutes)
            seconds = Decimal(seconds)
            decimal = degrees + minutes / Decimal('60') + seconds / Decimal('3600')
            if direction in ['S', 'W']:
                decimal *= Decimal('-1')
            return decimal
        except Exception as e:
            logger.error(f"Error parsing DMS coordinate '{dms_str}': {e}")
            return None

    def _parse_gps_position(self, gps_position: str) -> Tuple[Optional[Decimal], Optional[Decimal]]:
        """Parse GPSPosition string into latitude and longitude."""
        try:
            positions = gps_position.split(', ')
            if len(positions) != 2:
                logger.error(f"Invalid GPSPosition format: {gps_position}")
                return None, None
            lat = self._parse_dms(positions[0])
            lon = self._parse_dms(positions[1])
            return lat, lon
        except Exception as e:
            logger.error(f"Error parsing GPSPosition '{gps_position}': {e}")
            return None, None

class DistanceCalculator:
    """Class to calculate the distance between two GPS coordinates."""

    @classmethod
    def calculate_distance(cls, lat1: Decimal, lon1: Decimal, lat2: Decimal, lon2: Decimal) -> float:
        """Calculate the great-circle distance between two coordinates."""
        # Convert Decimal to float for math module functions
        lat1 = float(lat1)
        lon1 = float(lon1)
        lat2 = float(lat2)
        lon2 = float(lon2)
        R = 6371e3  # Earth's radius in meters
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        a = math.sin(delta_phi / 2.0) ** 2 + \
            math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        distance = R * c  # in meters
        return distance

class DatabaseManager:
    """Class to handle SQLite database operations."""

    def __init__(self, db_name: str = 'image_search.db'):
        self.db_path = PROJECT_ROOT / db_name
        self._create_table()

    def _create_table(self):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS images
                         (path TEXT, date TEXT, latitude REAL, longitude REAL)''')
            conn.commit()
        logger.info("Database table 'images' is ready.")

    def insert_record(self, path: Path, date: str, latitude: Decimal, longitude: Decimal):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('INSERT INTO images (path, date, latitude, longitude) VALUES (?, ?, ?, ?)',
                      (str(path), date, float(latitude), float(longitude)))
            conn.commit()
        logger.debug(f"Inserted record into database: {path}, {date}, {latitude}, {longitude}")

    def count_records(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM images')
            count = c.fetchone()[0]
        return count

    def get_records(self) -> Iterator[Tuple[str, str, Decimal, Decimal]]:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('SELECT path, date, latitude, longitude FROM images')
            for row in c.fetchall():
                yield row

class ImageSearcher(BaseModel):
    """Class to search for image files in a directory and its subdirectories."""
    directory : Path = Field(default='/mnt/i/tmp_delete_without_checking/', description="Directory to search for image files")
    extensions : Tuple[str, ...] = Field(default=('.jpg', '.jpeg', '.arw', '.nef', '.dng'), description="File extensions to search for")

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def get_image_files(self) -> Iterator[Path]:
        """Recursively yield all files with specified extensions."""
        logger.info(f"Searching for image files in {self.directory}...")
        for root, _, files in os.walk(self.directory):
            for filename in files:
                if filename.lower().endswith(self.extensions):
                    file_path = Path(root) / filename
                    yield file_path
                    logger.debug(f"Found image file: {file_path}")
    
    def run(self):
        # Target coordinates and search radius
        target_lat = Decimal('41.7345966563581')
        target_lon = Decimal('-73.92416128889411')
        radius = Decimal('1609.34')  # 1 mile in meters

        logger.info('Searching for images within 1 mile of %s, %s', target_lat, target_lon)

        # Initialize components
        exif_extractor = ExifDataExtractor()
        db_manager = DatabaseManager()
        
        record_count = db_manager.count_records()
        logger.info(f"Database contains {record_count} records already.")

        # Prepare to process files
        files = self.get_image_files()
        count : int = 0

        # Process each file
        with alive_bar(title="Searching images...", unit='images', dual_line=True, unknown='waves') as progress_bar:
            for file_path in files:
                try:
                    lat, lon = exif_extractor.get_gps_data(file_path)
                    if lat is not None and lon is not None:
                        distance = DistanceCalculator.calculate_distance(target_lat, target_lon, lat, lon)
                        if Decimal(distance) <= radius:
                            today = datetime.now().strftime('%Y-%m-%d')
                            db_manager.insert_record(file_path, today, lat, lon)
                            count += 1
                            logger.debug(f"Image within radius: {file_path} (Distance: {distance:.2f} meters)")
                        else:
                            logger.debug(f"Image outside radius: {file_path} (Distance: {distance:.2f} meters)")
                    else:
                        logger.debug(f"No GPS data for image: {file_path}")
                except Exception as e:
                    logger.error(f"Error processing file {file_path}: {e}")
                finally:
                    progress_bar()
                    progress_bar.text(f"Images found: {count}")

        logger.info(f"Found {count} images within {radius} meters of target coordinates.")
        record_count = db_manager.count_records()
        logger.info(f"Database now contains {record_count} records.")


def setup_logging():

    logging.basicConfig(level=logging.INFO)

    # Define a custom formatter class
    class CustomFormatter(colorlog.ColoredFormatter):
        def format(self, record):
            self._style._fmt = '(%(log_color)s%(levelname)s%(reset)s) %(message)s'
            return super().format(record)

    # Configure colored logging with the custom formatter
    handler = colorlog.StreamHandler()
    handler.setFormatter(CustomFormatter(
        # Initial format string (will be overridden in the formatter)
        '',
        log_colors={
            'DEBUG':    'green',
            'INFO':     'blue',
            'WARNING':  'yellow',
            'ERROR':    'red',
            'CRITICAL': 'red,bg_white',
        }
    ))

    root_logger = logging.getLogger()
    root_logger.handlers = []  # Clear existing handlers
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)

    return root_logger

class ArgsNamespace(argparse.Namespace):
    verbose: bool

def main():
    try:
        logger = setup_logging()
        load_dotenv()

        parser = argparse.ArgumentParser(description="")
        parser.add_argument('--verbose', '-v', action='store_true', help="Verbose output")

        args = parser.parse_args(namespace=ArgsNamespace())

        if args.verbose:
            logger.setLevel(logging.DEBUG)

        searcher = ImageSearcher()
        searcher.run()
            
    except KeyboardInterrupt:
        logger.info("Script cancelled by user.")

    sys.exit(0)

if __name__ == "__main__":
    main()