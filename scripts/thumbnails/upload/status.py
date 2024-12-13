"""*********************************************************************************************************************
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    METADATA:                                                                                                         *
*                                                                                                                      *
*        File:    status.py                                                                                            *
*        Project: imageinn                                                                                             *
*        Version: 0.1.0                                                                                                *
*        Created: 2024-09-27                                                                                           *
*        Author:  Jess Mann                                                                                            *
*        Email:   jess.a.mann@gmail.com                                                                                *
*        Copyright (c) 2024 Jess Mann                                                                                  *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    LAST MODIFIED:                                                                                                    *
*                                                                                                                      *
*        2024-10-19     By Jess Mann                                                                                   *
*                                                                                                                      *
*********************************************************************************************************************"""
from __future__ import annotations
import os
import sys

# Add the root directory of the project to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

import threading
import sqlalchemy.exc
from typing import Iterator
from enum import Enum
from pathlib import Path
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import create_engine, Column, String, Float, Integer, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from scripts import setup_logging

logger = setup_logging()

# When version increases, directories will be reprocessed even if their last modified time hasn't changed.
VERSION = 3

class UploadStatus(Enum):
    UPLOADED = 'uploaded'
    SKIPPED = 'skipped'
    DUPLICATE = 'duplicate'
    ERROR = 'error'

Base = declarative_base()

class StatusRecord(Base):
    __tablename__ = 'status'
    
    id = Column(Integer, primary_key=True)
    directory = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    status = Column(SQLEnum(UploadStatus), nullable=False)
    last_processed_time = Column(Float, nullable=False, default=0.0)
    version = Column(Integer, nullable=False, default=-1)

# Setup DB once
project_root = Path(__file__).parent.parent.parent.parent
db_path = project_root / 'file_status.db'
engine = create_engine(f'sqlite:///{db_path}')
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)

class Status(BaseModel):
    """
    Class to manage the status in SQLite, handle locking, and provide iteration over statuses.
    """
    directory: Path
    version: int = -1
    last_processed_time: float = 0.0
    _lock: threading.Lock = Field(default_factory=threading.Lock, repr=False)
    _session = Field(default=None, repr=False)

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, **data):
        super().__init__(**data)
        if not self.directory.exists():
            raise FileNotFoundError(f"Directory {self.directory} does not exist.")
        self._session = SessionLocal()


    @field_validator('directory', mode="before")
    def validate_directory(cls, v: Path) -> Path:
        if not v:
            raise ValueError("directory must be set.")

        v = Path(v)

        if not v.exists():
            logger.error("Directory %s does not exist.", v)
            raise FileNotFoundError(f"Directory {v} does not exist.")

        return v

    @property
    def lock(self) -> threading.Lock:
        return self._lock

    def save(self) -> bool:
        """
        Commit any pending changes to SQLite
        """
        try:
            self._session.commit()
            return True
        except sqlalchemy.exc.SQLAlchemyError as e:
            logger.error("Error saving to database: %s", e)
            self._session.rollback()
            return False

    def update_meta(self):
        """
        Update the last processed time and version for all records in this directory
        """
        self.last_processed_time = self.directory.stat().st_mtime
        self.version = VERSION
        with self.lock:
            self._session.query(StatusRecord).filter_by(
                directory=str(self.directory)
            ).update({
                'last_processed_time': self.last_processed_time,
                'version': self.version
            })
            self.save()

    def update_status(self, filename: str | Path, status: UploadStatus):
        """
        Update the status of a file in a thread-safe manner.
        """
        if isinstance(filename, Path):
            filename = filename.name
        with self.lock:
            record = self._session.query(StatusRecord).filter_by(
                directory=str(self.directory),
                filename=filename
            ).first()

            if status == UploadStatus.SKIPPED and record is not None:
                # Do not overwrite existing status with "skipped"
                return

            if record is None:
                record = StatusRecord(
                    directory=str(self.directory),
                    filename=filename,
                    status=status,
                    last_processed_time=self.last_processed_time,
                    version=self.version
                )
                self._session.add(record)
            else:
                record.status = status
                record.last_processed_time = self.last_processed_time
                record.version = self.version
            self.save()

    def get_status(self, filename: str | Path) -> UploadStatus | None:
        """
        Get the status of a file in a thread-safe manner.
        """
        if isinstance(filename, Path):
            filename = filename.name
        with self.lock:
            record = self._session.query(StatusRecord).filter_by(
                directory=str(self.directory),
                filename=filename
            ).first()
            return record.status if record else None

    def was_successful(self, filename: str | Path) -> bool:
        """
        Check if the file was uploaded successfully.
        """
        status = self.get_status(filename)
        return status in [UploadStatus.DUPLICATE, UploadStatus.UPLOADED]

    def was_failed(self, filename: str | Path) -> bool:
        """
        Check if the file upload failed.
        """
        return self.get_status(filename) == UploadStatus.ERROR

    def was_skipped(self, filename: str | Path) -> bool:
        """
        Check if the file was skipped.
        """
        return self.get_status(filename) == UploadStatus.SKIPPED

    def directory_changed(self) -> bool:
        """
        Check if the directory has changed since the last time it was processed.
        """
        # If our version has changed, we can't trust that our directory iterator will be the same.
        if self.version < VERSION:
            return True
        return self.last_processed_time <= self.directory.stat().st_mtime

    def __len__(self) -> int:
        """
        Get the number of statuses.
        """
        with self.lock:
            return self._session.query(StatusRecord).filter_by(
                directory=str(self.directory)
            ).count()

    def __iter__(self) -> Iterator[tuple[str, UploadStatus]]:
        """
        Iterate over the statuses.
        """
        with self.lock:
            records = self._session.query(StatusRecord).filter_by(
                directory=str(self.directory)
            ).all()
        return iter((r.filename, r.status) for r in records)

    def __getitem__(self, key: str) -> UploadStatus:
        """
        Get the status of a file.
        """
        if (status := self.get_status(key)) is None:
            raise KeyError(f"No status found for file: {key}")
        return status

    def __setitem__(self, key: str, value: UploadStatus):
        """
        Set the status of a file.
        """
        self.update_status(key, value)

    def __delitem__(self, key: str):
        """
        Delete the status of a file.
        """
        with self.lock:
            self._session.query(StatusRecord).filter_by(
                directory=str(self.directory),
                filename=key
            ).delete()
            self.save()

    def __contains__(self, key: str) -> bool:
        return self.get_status(key) is not None

    def __enter__(self) -> Status:
        """
        Enter the runtime context related to this object.
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Exit the runtime context and ensure changes are saved.
        """
        self.save()
        self._session.close()

    def __repr__(self) -> str:
        return f"Status(directory={self.directory})"
