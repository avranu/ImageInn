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
from typing import Any, Tuple, Optional, Iterator
from datetime import datetime
from decimal import Decimal
from alive_progress import alive_bar

from scripts.lib.types import ProgressBar, RESET, RED, GREEN, YELLOW, BLUE, PURPLE, CYAN, WHITE, BLACK, BOLD, UNDERLINE, DIM
from scripts.lib.db import ImagesDatabase

# Set up module-level logger
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent

class ExifDataExtractor:
    """Class to extract and parse GPS data from image files."""

    def __init__(self):
        if not shutil.which('exiftool'):
            logger.error("ExifTool is not installed. Please install ExifTool to proceed.")
            sys.exit(1)
        logger.debug("ExifTool is installed and ready to use.")

    def get_gps_data(self, file_path: Path) -> Tuple[Optional[Decimal], Optional[Decimal]]:
        """Extract GPS data from image file using ExifTool."""
        try:
            output = subprocess.check_output(
                ['exiftool', '-GPSLatitude', '-GPSLongitude', '-GPSPosition', '-j', str(file_path)],
                stderr=subprocess.STDOUT
            )
            data = json.loads(output.decode('utf-8'))[0]
        except subprocess.CalledProcessError as e:
            logger.error(f"ExifTool error on file {file_path}: {e}")
            return None, None
        except Exception as e:
            logger.error(f"Error extracting GPS data from {file_path}: {e}")
            logger.error(f"Output: {output.decode('utf-8')}")
            return None, None

        if not isinstance(data, dict):
            logger.error(f"Invalid JSON data from ExifTool: {data}")
            return None, None

        try:
            lat = data.get('GPSLatitude', None)
            lon = data.get('GPSLongitude', None)

            if all([lat, lon]):
                lat = self._convert_to_decimal(lat)
                lon = self._convert_to_decimal(lon)
                return lat, lon
            gps_position = data.get('GPSPosition', None)
            if gps_position:
                lat, lon = self._parse_gps_position(gps_position)
                return lat, lon
            
        except Exception as e:
            logger.error(f"Error parsing GPS data from {file_path}: {e}")
            raise

        # If the only key in the data is SourceFile, don't log
        if not (len(data) == 1 and 'SourceFile' in data):
            logger.error(f"No GPS data found in {file_path}: {data}")
            
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

class ImageSearcher(BaseModel):
    """Class to search for image files in a directory and its subdirectories."""
    directory : Path = Field(default='.', validate_default=True, description="Directory to search for image files")
    extensions : Tuple[str, ...] = Field(default=('.jpg', '.jpeg', '.arw', '.nef', '.dng'), description="File extensions to search for")

    model_config = ConfigDict(arbitrary_types_allowed=True)


    @field_validator('directory', mode='before')
    def validate_directory(cls, value: Any) -> Path | None:
        if not value:
            return Path('.')

        dir_path = Path(value)
        if not dir_path.exists():
            raise ValueError(f"Directory {dir_path} does not exist.")
            
        return dir_path

    def get_image_files(self) -> Iterator[Path]:
        """Recursively yield all files with specified extensions."""
        logger.info(f"Searching for image files in {self.directory}...")
        for extension in self.extensions:
            pattern = f'**/*{extension}'
            for file_path in self.directory.rglob(pattern):
                yield file_path
                logger.debug(f"Found image file: {file_path}")

    def calculate_distance(self, lat1: Decimal, lon1: Decimal, lat2: Decimal, lon2: Decimal) -> float:
        """Calculate the distance between two coordinates."""
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

    def run(self):
        # Target coordinates and search radius
        target_lat = Decimal('41.7345966563581')
        target_lon = Decimal('-73.92416128889411')
        radius = Decimal('1609.34')  # 1 mile in meters

        logger.info('Searching for images within 1 mile of %s, %s', target_lat, target_lon)

        # Initialize components
        exif_extractor = ExifDataExtractor()
        db_manager = ImagesDatabase()

        if record_count := db_manager.count_records():
            logger.info(f"Database contains {record_count} records already.")

        # Prepare to process files
        files = self.get_image_files()
        count: int = 0

        # Process each file
        with alive_bar(title=f"{YELLOW}Searching images...{RESET}", unit='images', dual_line=True, unknown='waves') as progress_bar:
            for file_path in files:
                try:
                    lat, lon = exif_extractor.get_gps_data(file_path)
                    if lat is not None and lon is not None:
                        distance = self.calculate_distance(target_lat, target_lon, lat, lon)
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
                    progress_bar.text(f"{YELLOW}Images found{RESET}: {count}")

        record_count = db_manager.count_records()
        logger.info(f"Found {count} images near target coordinates. Total records: {record_count}")

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
    directory : str

def main():
    try:
        logger = setup_logging()
        load_dotenv()

        parser = argparse.ArgumentParser(description="")
        parser.add_argument('--verbose', '-v', action='store_true', help="Verbose output")
        parser.add_argument('--directory', '-d', default=None, help="Directory to search for image files")
        args = parser.parse_args(namespace=ArgsNamespace())

        if args.verbose:
            logger.setLevel(logging.DEBUG)

        searcher = ImageSearcher(directory=args.directory)
        searcher.run()

    except KeyboardInterrupt:
        logger.info("Script cancelled by user.")
        sys.exit(0)

if __name__ == "__main__":
    main()