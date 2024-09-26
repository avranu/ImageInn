from __future__ import annotations
import os
import re
import sys

# Add the root directory of the project to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from pathlib import Path
from functools import lru_cache
import hashlib
import shutil
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator
from scripts import setup_logging
from scripts.exceptions import ShouldTerminateException

logger = setup_logging()

class FileManager(BaseModel):
    directory: Path = Field(default=Path('.'))
    file_prefix: str = 'PXL_'
    dry_run: bool = False
    _files_moved: list[Path] = PrivateAttr(default_factory=list)
    _files_copied : list[Path] = PrivateAttr(default_factory=list)
    _files_deleted: list[Path] = PrivateAttr(default_factory=list)
    _files_skipped: list[Path] = PrivateAttr(default_factory=list)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @field_validator('directory', mode='before')
    def validate_directory(cls, v):
        return Path(v)

    @property
    def files_moved(self) -> list[Path]:
        return self._files_moved

    @property
    def files_deleted(self) -> list[Path]:
        return self._files_deleted

    @property
    def files_skipped(self) -> list[Path]:
        return self._files_skipped

    @property
    def files_copied(self) -> list[Path]:
        return self._files_copied

    @property
    def filename_pattern(self) -> re.Pattern:
        if not self._filename_pattern:
            self._filename_pattern = re.compile(rf'^{re.escape(self.file_prefix)}(20\d{{6}})_')
        return self._filename_pattern

    def append_moved_file(self, file: Path) -> None:
        """
        Add a file to the list of moved files.
        """
        self._files_moved.append(file)

    def append_deleted_file(self, file: Path) -> None:
        """
        Add a file to the list of deleted files. 
        """
        self._files_deleted.append(file)

    def append_skipped_file(self, file: Path) -> None:
        """
        Add a file to the list of skipped files.
        """
        self._files_skipped.append(file)

    def append_copied_file(self, file: Path) -> None:
        """
        Add a file to the list of copied files.
        """
        self._files_copied.append(file)
    
    @lru_cache(maxsize=1024)
    def hash_file(self, filename: str | Path) -> str:
        """
        Calculate the MD5 hash of a file.

        Args:
            filename: The path to the file to hash.

        Returns:
            The MD5 hash of the file.
        """
        hash_md5 = hashlib.md5()
        with open(filename, "rb") as f:
            # Read the file in chunks to handle large files efficiently
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def get_files(self, directory : Path | None = None) -> list[Path]:
        """
        Get a list of files in a directory.

        Args:
            directory: The directory to search. Defaults to self.directory.

        Returns:
            A list of files in the directory which match the file prefix.
        """
        directory = directory or self.directory
        return directory.glob(f'{self.file_prefix}20*.jpg')

    def files_match(self, source_path : Path, destination_path: Path, skip_hash : bool = False) -> bool:
        """
        Check if the MD5 hashes of two files match.

        Args:
            source_file: The source file.
            destination: The target file.
            skip_hash: If True, only compare the file sizes.

        Returns:
            True if the hashes match, False otherwise.
        """
        if not destination_path.exists():
            return False

        # Check the filesize
        if source_path.stat().st_size != destination_path.stat().st_size:
            return False

        if skip_hash:
            return True

        # Check the hashes
        source_hash = self.hash_file(source_path)
        destination_hash = self.hash_file(destination_path)

        return source_hash == destination_hash

    def find_subdir(self, filename: str | Path) -> str:
        """
        Find the subdirectory for a file based on its filename.

        Args:
            filename: The filename to extract the date from.

        Returns:
            The name of the proposed subdirectory.

        Raises:
            ValueError: If the filename does not match the expected format.
        """
        if isinstance(filename, Path):
            filename = filename.name

        if not (match := self.filename_pattern.match(str(filename))):
            raise ValueError(f"Invalid filename format: {filename}")

        # Subdir name
        date_part = match.group(1)
        year = date_part[:4]
        month = date_part[4:6]
        dir_name = f"{year}-{month}"

        return dir_name

    def create_subdir(self, filename : str | Path, parent_directory : Path | None = None) -> Path:
        """
        Create a subdirectory for a file based on its filename.

        Args:
            filename: The filename to extract the date from.
            parent_directory: The parent directory to create the subdirectory in, defaults to self.directory.

        Returns:
            The path to the subdirectory.
        """
        parent_directory = parent_directory or self.directory

        subdir = self.find_subdir(filename)

        return self.mkdir(parent_directory / subdir)

    def mkdir(self, directory: Path) -> Path:
        """
        Create a directory if it does not exist.

        Args:
            directory: The directory to create.

        Returns:
            The directory path.
        """
        if not self.check_dry_run(f'creating directory {directory}'):
            directory.mkdir(exist_ok=True)
            
        return directory

    def delete_file(self, file: Path, use_trash : bool = True) -> bool:
        """
        Delete a file.

        Args:
            file: The file to delete.
            message: An optional message to log.

        Returns:
            True if the file was deleted, False otherwise.

        Raises:
            OneFileException: If an error occurs while deleting the file.
        """
        if use_trash:
            trash_dir = self.directory / '.trash'
            if not self.check_dry_run(f'creating trash directory: {trash_dir}'):
                trash_dir.mkdir(exist_ok=True)
                
            trash_file_path = trash_dir / file.name
            number = 1
            while trash_file_path.exists():
                trash_file_path = trash_dir / f"{file.stem}_{number}{file.suffix}" 

            if not self.check_dry_run(f'moving {file} to trash {trash_file_path}'):
                file.rename(trash_file_path)
        else:
            if not self.check_dry_run(f'deleting file {file}'):
                file.unlink()

        self.append_deleted_file(file)

        return not file.exists()

    def move_file(self, source_path: Path, destination_path: Path, verify : bool = False) -> Path:
        """
        Move a file to a new location.

        Args:
            source: The source file to move.
            destination: The destination path.

        Returns:
            The destination path.
        """
        # Destination must be absolute for Path.rename to be consistent
        if not destination_path.is_absolute():
            logger.debug(f"Making destination path absolute: {destination_path}")
            destination_path = self.directory / destination_path

        # Convert dirs into file paths
        if destination_path.is_dir():
            destination_path = destination_path / source_path.name

        if destination_path.exists():
            raise FileExistsError(f"Destination file already exists: {destination_path}")
        
        if verify:
            source_hash = self.hash_file(source_path)

        if not self.check_dry_run(f'moving {source_path} to {destination_path}'):
            source_path.rename(destination_path)
            self.append_moved_file(destination_path)

            if verify:
                destination_hash = self.hash_file(destination_path)
                if source_hash != destination_hash:
                    logger.critical(f"Checksum mismatch after moving {source_path} to {destination_path}")
                    raise ShouldTerminateException('Checksum mismatch after moving')

        return destination_path

    def copy_file(self, source_path : Path, destination_path : Path, verify : bool = False) -> Path:
        """
        Copy a file to a new location.

        Args:
            source: The source file to copy.
            destination: The destination path.

        Returns:
            The destination path.
        """
        # Destination must be absolute for Path.rename to be consistent
        if not destination_path.is_absolute():
            logger.debug(f"Making destination path absolute: {destination_path}")
            destination_path = self.directory / destination_path

        # Convert dirs into file paths
        if destination_path.is_dir():
            destination_path = destination_path / source_path.name

        if destination_path.exists():
            raise FileExistsError(f"Destination file already exists: {destination_path}")

        if verify:
            source_hash = self.hash_file(source_path)

        if not self.check_dry_run(f'copying {source_path} to {destination_path}'):
            shutil.copy2(source_path, destination_path)

            if verify:
                destination_hash = self.hash_file(destination_path)
                if source_hash != destination_hash:
                    logger.critical(f"Checksum mismatch after copying {source_path} to {destination_path}")
                    raise ShouldTerminateException('Checksum mismatch after copying')
                
        self.append_copied_file(destination_path)
        return destination_path

    def check_dry_run(self, message : str | None = None) -> bool:
        """
        Check if the script is running in dry-run mode.

        Args:
            message: An optional message to log.

        Returns:
            True if running in dry-run mode, False otherwise.
        """
        if self.dry_run:
            logger.info('DRY RUN: Skipped %s', message or 'Operation skipped')
            return True
        return False

    def __hash__(self) -> int:
        return hash(self.directory)