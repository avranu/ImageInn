from __future__ import annotations
import os
import sys

# Add the root directory of the project to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from typing import Any, Iterable, Iterator
from pathlib import Path
from pydantic import BaseModel, Field, PrivateAttr, field_validator
import threading
from scripts import setup_logging

logger = setup_logging()

STATUS_FILE_NAME = 'upload_status.txt'

class Status(BaseModel):
    """
    Class to manage the status file data, handle locking, and provide iteration over statuses.
    """
    statuses: dict[str, bool] = Field(default_factory=dict)
    last_processed_time: float = 0.0
    directory: Path
    _lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)

    class Config:
        arbitrary_types_allowed = True

    @field_validator('directory', mode="before")
    def validate_directory(cls, v: Path) -> Path:
        if not v:
            raise ValueError("directory must be set.")

        v = Path(v)

        if not v.exists():
            logger.error(f"Directory {v} does not exist.")
            raise FileNotFoundError(f"Directory {v} does not exist.")
        
        return v

    @property
    def status_file(self) -> Path:
        return self.directory / STATUS_FILE_NAME

    @property
    def lock(self) -> threading.Lock:
        return self._lock

    def load(self):
        """
        Load the status data from the status file.
        """
        if self.status_file.exists():
            with self.status_file.open('r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('#'):
                        # Parse header lines
                        if line.startswith('# last_processed_time:'):
                            self.last_processed_time = float(line.split(':', 1)[1].strip())
                        continue
                    if line:
                        parts = line.split('\t')
                        if len(parts) == 2:
                            filename, file_status = parts
                            self.statuses[filename] = True if file_status == 'success' else False

            success = sum(1 for status in self.statuses.values() if status)
            failure = len(self.statuses) - success
            logger.info(f"Loaded status file {self.status_file}. Success: {success}, Failure: {failure}")

    def save(self):
        """
        Save the status data to the status file.
        """
        with self.lock:
            if not self.statuses:
                return
            
            with self.status_file.open('w') as f:
                if self.last_processed_time:
                    f.write(f'# last_processed_time: {self.last_processed_time}\n')
                for filename, file_status in self.statuses.items():
                    status_str = 'success' if file_status else 'failed'
                    f.write(f'{filename}\t{status_str}\n')

    def update_time(self):
        """
        Update the last processed time to the current time.
        """
        self.last_processed_time = self.directory.stat().st_mtime

    def update_status(self, filename: str | Path, status: bool):
        """
        Update the status of a file in a thread-safe manner.
        """ 
        if isinstance(filename, Path):
            filename = filename.name

        with self.lock:
            self.statuses[filename] = status

    def get_status(self, filename: str | Path) -> bool | None:
        """
        Get the status of a file in a thread-safe manner.
        """
        if isinstance(filename, Path):
            filename = filename.name
            
        with self.lock:
            return self.statuses.get(filename)

    def was_successful(self, filename: str | Path) -> bool:
        """
        Check if the file was uploaded successfully.
        """
        status = self.get_status(filename)
        return status is True

    def was_failed(self, filename: str | Path) -> bool:
        """
        Check if the file upload failed.
        """
        status = self.get_status(filename)
        return status is False

    def directory_changed(self) -> bool:
        """
        Check if the directory has changed since the last time it was processed.
        """
        return self.last_processed_time <= self.directory.stat().st_mtime

    def __len__(self) -> int:
        """
        Get the number of statuses.
        """
        with self.lock:
            return len(self.statuses)

    def __iter__(self) -> Iterator[tuple[str, bool]]:
        """
        Iterate over the statuses.
        """
        with self.lock:
            # Return a copy to prevent issues during iteration
            return iter(self.statuses.copy().items())

    def __getitem__(self, key: str) -> bool:
        """
        Get the status of a file.
        """
        if (status := self.get_status(key)) is None:
            raise KeyError(f"No status found for file: {key}")
        return status

    def __setitem__(self, key: str, value: bool):
        """
        Set the status of a file.
        """
        self.update_status(key, value)

    def __delitem__(self, key: str):
        """
        Delete the status of a file.
        """
        with self.lock:
            del self.statuses[key]

    def __contains__(self, key: str) -> bool:
        """
        Check if the status of a file is present.
        """
        with self.lock:
            return key in self.statuses

    def __repr__(self) -> str:
        """
        Get the string representation of the status object.
        """
        return f"Status(directory={self.directory}, statuses={self.statuses})"

    def __str__(self) -> str:
        """
        Get the string representation of the status object.
        """
        return repr(self)

    def __enter__(self) -> Status:
        """
        Enter the runtime context related to this object.
        """
        self.load()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Exit the runtime context and save the status data.
        """
        self.save()