"""*********************************************************************************************************************
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    METADATA:                                                                                                         *
*                                                                                                                      *
*        File:    images.py                                                                                            *
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

# Set up module-level logger
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]

class ImagesDatabase:
    """Class to handle SQLite database operations."""
    db_path : Path

    def __init__(self, db_name: str = 'image_search.db'):
        self.db_path = PROJECT_ROOT / db_name
        self._create_table()

    def _create_table(self):
        logger.info(f"Creating database table 'images' in {self.db_path}...")
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS images
                         (path TEXT UNIQUE, date TEXT, latitude REAL, longitude REAL, uploaded BOOLEAN DEFAULT 0)''')
            conn.commit()
        logger.debug("Database table 'images' is ready.")

    def insert_record(self, path: Path, date: str, latitude: Decimal, longitude: Decimal):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('INSERT OR IGNORE INTO images (path, date, latitude, longitude) VALUES (?, ?, ?, ?)',
                      (str(path), date, float(latitude), float(longitude)))
            conn.commit()
        logger.debug(f"Inserted record into database: {path}, {date}, {latitude}, {longitude}")

    def mark_uploaded(self, path: Path):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('UPDATE images SET uploaded=1 WHERE path=?', (str(path),))
            conn.commit()
        logger.debug(f"Marked image as uploaded: {path}")

    def count_records(self, *, uploaded : bool | None = None) -> int:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            query = 'SELECT COUNT(*) FROM images'
            if uploaded is not None:
                query = f'{query} WHERE uploaded={int(uploaded)}'
            c.execute(query)
            count = c.fetchone()[0]
        return count

    def get_records(self, *, uploaded : bool | None = None) -> Iterator[Tuple[str, str, Decimal, Decimal]]:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            query = 'SELECT path, date, latitude, longitude FROM images'
            if uploaded is not None:
                query = f'{query} WHERE uploaded={int(uploaded)}'
            c.execute(query)
            for row in c.fetchall():
                yield row

    def get_images(self, *, uploaded : bool | None = None) -> Iterator[Path]:
        for row in self.get_records(uploaded=uploaded):
            yield Path(row[0])