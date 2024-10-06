from __future__ import annotations
import os
import sys

# Add the root directory of the project to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from typing import Iterator
from enum import Enum
from pathlib import Path
from pydantic import BaseModel, Field, PrivateAttr, field_validator
import threading
from scripts import setup_logging

logger = setup_logging()

STATUS_FILE_NAME = 'upload_status.txt'
# When version increases, directories will be reprocessed even if their last modified time hasn't changed.
VERSION = 2

class UploadStatus(Enum):
    UPLOADED = 'uploaded'
    SKIPPED = 'skipped'
    DUPLICATE = 'duplicate'
    ERROR = 'error'


class Status(BaseModel):
    """
    Class to manage the status file data, handle locking, and provide iteration over statuses.
    """
    statuses: dict[str, UploadStatus] = Field(default_factory=dict)
    last_processed_time: float = 0.0
    directory: Path
    version : int = -1
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
                        if line.startswith('# version:'):
                            self.version = int(line.split(':', 1)[1].strip())
                            
                        continue
                    if line:
                        parts = line.split('\t')
                        if len(parts) == 2:
                            filename, file_status = parts
                            # Handle aliases. We can remove these eventually. TODO
                            if file_status == 'failed':
                                file_status = 'error'
                            elif file_status == 'success':
                                file_status = 'uploaded'
                            elif file_status.startswith('UploadStatus.'):
                                file_status = file_status.split('.')[1]
                            self.statuses[filename] = UploadStatus(file_status.lower())

            success = sum(1 for status in self.statuses.values() if self.was_successful(status))
            skipped = sum(1 for status in self.statuses.values() if self.was_skipped(status))
            failure = sum(1 for status in self.statuses.values() if self.was_failed(status))
            logger.debug(f"Loaded status file in {self.directory.name}. Success: {success}, Skipped: {skipped}, Failure: {failure}")

    def save(self):
        """
        Save the status data to the status file.
        """
        with self.lock:
            if not self.statuses:
                logger.debug('Skipping saving empty status file')
                return
            
            with self.status_file.open('w') as f:
                if self.last_processed_time:
                    f.write(f'# last_processed_time: {self.last_processed_time}\n')
                if self.version > 0:
                    f.write(f'# version: {self.version}\n')
                for filename, file_status in self.statuses.items():
                    # Do not save "skipped" statuses
                    if file_status == UploadStatus.SKIPPED:
                        continue
                    f.write(f'{filename}\t{file_status.value}\n')

    def update_meta(self):
        """
        Update the last processed time to the current time, and update the version.
        """
        self.last_processed_time = self.directory.stat().st_mtime
        self.version = VERSION

    def update_status(self, filename: str | Path, status: UploadStatus):
        """
        Update the status of a file in a thread-safe manner.
        """ 
        if isinstance(filename, Path):
            filename = filename.name

        with self.lock:
            self.statuses[filename] = status

    def get_status(self, filename: str | Path) -> UploadStatus | None:
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
        return status in [UploadStatus.DUPLICATE, UploadStatus.UPLOADED]

    def was_failed(self, filename: str | Path) -> bool:
        """
        Check if the file upload failed.
        """
        status = self.get_status(filename)
        return status in [UploadStatus.ERROR]

    def was_skipped(self, filename : str | Path) -> bool:
        """
        Check if the file was skipped.
        """
        status = self.get_status(filename)
        return status in [UploadStatus.SKIPPED]

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

    def __hash__(self) -> int:
        """
        Get the hash of the status object.
        """
        return hash(self.directory)