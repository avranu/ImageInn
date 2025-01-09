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

from enum import Enum
from pathlib import Path
from typing import Iterator, Self

import sqlalchemy.exc
from sqlalchemy import create_engine, Column, String, Float, Integer, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, Query

from scripts import setup_logging

logger = setup_logging()

# When version increases, directories will be reprocessed even if their last modified time hasn't changed.
VERSION = 3

class StatusOptions(Enum):
    UPLOADED = 'uploaded'
    SKIPPED = 'skipped'
    DUPLICATE = 'duplicate'
    ERROR = 'error'

Base = declarative_base()

class DbManager:
    """
    A class to manage the database connection and session.
    """
    _sessionmaker: sessionmaker | None = None

    @classmethod
    def initialize_db(cls):
        """
        Initialize the database and create the tables.
        """
        project_root = Path(__file__).parent.parent.parent.parent
        db_path = project_root / 'file_status.db'
        engine = create_engine(f'sqlite:///{db_path}', pool_size=10, max_overflow=20)
        Base.metadata.create_all(engine)
        cls._sessionmaker = sessionmaker(bind=engine)

        file_records = FileStatus.count_records()
        directory_records = DirectoryStatus.count_records()
        logger.info(f"Database initialized with {file_records} file records and {directory_records} directory records.")

    @classmethod
    def get_session(cls) -> Session:
        if cls._sessionmaker is None:
            raise ValueError("Database not initialized.")
        return cls._sessionmaker()

class FileStatus(Base):
    __tablename__ = 'upload_status'
    
    id = Column(Integer, primary_key=True)
    directory = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    status = Column(SQLEnum(StatusOptions), nullable=False, default=StatusOptions.SKIPPED)
    file_hash = Column(String, nullable=True)
    last_processed_time = Column(Float, nullable=False, default=0.0)
    version = Column(Integer, nullable=False, default=-1)
        
    @classmethod
    def get_status(cls, file_path : Path) -> StatusOptions | None:
        directory = file_path.parent
        filename = file_path.name
        
        session = DbManager.get_session()
        try:
            record = (session.query(FileStatus)
                             .filter_by(directory=str(directory), filename=filename)
                             .first())
            return record.status if record else None
        finally:
            session.close()

    @classmethod
    def update_status(cls, file_path : Path, status: StatusOptions):
        directory = file_path.parent.absolute()
        filename = file_path.name

        # We need directory to exist and be a directory
        if not directory.exists():
            raise FileNotFoundError(f"Directory {directory} does not exist.")

        session = DbManager.get_session()
        try:
            record = (session.query(FileStatus)
                             .filter_by(directory=str(directory), filename=filename)
                             .first())

            last_processed_time = directory.stat().st_mtime
            if record is None:
                record = FileStatus(
                    directory=str(directory),
                    filename=filename,
                    status=status,
                    last_processed_time=last_processed_time,
                    version=VERSION
                )
                session.add(record)
            else:
                # If updating to SKIPPED, do not overwrite an existing status
                if status in [StatusOptions.SKIPPED, StatusOptions.DUPLICATE]:
                    return
                
                record.status = status
                record.last_processed_time = last_processed_time
                record.version = VERSION
            session.commit()
        except sqlalchemy.exc.SQLAlchemyError as e:
            logger.error("Error updating status: %s", e)
            session.rollback()
        finally:
            session.close()

    @classmethod
    def upload_success(cls, file_path : Path):
        cls.update_status(file_path, StatusOptions.UPLOADED)

    @classmethod
    def upload_error(cls, file_path : Path):
        cls.update_status(file_path, StatusOptions.ERROR)

    @classmethod
    def upload_skipped(cls, file_path : Path):
        cls.update_status(file_path, StatusOptions.SKIPPED)

    @classmethod
    def was_successful(cls, file_path : Path) -> bool:
        s = cls.get_status(file_path)
        return s in [StatusOptions.DUPLICATE, StatusOptions.UPLOADED]

    @classmethod
    def was_failed(cls, file_path : Path) -> bool:
        return cls.get_status(file_path) == StatusOptions.ERROR

    @classmethod
    def was_skipped(cls, file_path : Path) -> bool:
        return cls.get_status(file_path) == StatusOptions.SKIPPED

    @classmethod
    def get_all(cls, directory: Path) -> Iterator[tuple[str, StatusOptions]]:
        """
        Iterate over all files and their status for a given directory.
        """
        session = DbManager.get_session()
        try:
            records = (session.query(FileStatus)
                              .filter_by(directory=str(directory))
                              .all())
            for r in records:
                yield (r.filename, r.status)
        finally:
            session.close()

    @classmethod
    def get_all_status(cls, directory: Path, status: StatusOptions) -> Iterator[str]:
        """
        Iterate over all files with a given status in the specified directory.
        """
        session = DbManager.get_session()
        try:
            records = (session.query(FileStatus)
                              .filter_by(directory=str(directory), status=status)
                              .all())
            for r in records:
                yield r.filename
        finally:
            session.close()

    @classmethod
    def delete_status(cls, file_path : Path):
        """
        Delete the status of a file.
        """
        directory = file_path.parent
        filename = file_path.name
        
        session = DbManager.get_session()
        try:
            session.query(FileStatus).filter_by(
                directory=str(directory),
                filename=filename
            ).delete()
            session.commit()
        except sqlalchemy.exc.SQLAlchemyError as e:
            logger.error("Error deleting status: %s", e)
            session.rollback()
        finally:
            session.close()

    @classmethod
    def count(cls, directory: Path) -> int:
        """
        Get the number of files tracked in the specified directory.
        """
        session = DbManager.get_session()
        try:
            return (session.query(FileStatus)
                          .filter_by(directory=str(directory))
                          .count())
        finally:
            session.close()

    @classmethod
    def count_records(cls) -> int:
        """
        Get the number of records in the database.
        """
        session = DbManager.get_session()
        try:
            return session.query(FileStatus).count()
        finally:
            session.close()

class DirectoryStatus(Base):
    __tablename__ = 'directory_status'
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True)
    directory = Column(String, nullable=False)
    globs = Column(String, nullable=True)
    file_count = Column(Integer, nullable=False, default=0)
    last_modified_time = Column(Float, nullable=False, default=0.0)
    version = Column(Integer, nullable=False, default=-1)

    _sessionmaker: sessionmaker | None = None

    @classmethod
    def get_queryset(cls, session : Session) -> Query[Self]:
        return session.query(DirectoryStatus)

    @classmethod
    def query(cls, session : Session, directory : Path | None = None, globs : str | list[str] | None = None) -> Query[Self]:
        q = cls.get_queryset(session)
        if directory:
            q = q.filter_by(directory=str(directory))
            
        # TODO: Likely a bug here, in the event of globs = None returning records with any glob value
        # ...instead of the expected behavior of returning records with no glob value
        # TODO: Another bug exists with the ordering of the list. If the list is not sorted, the query will sometimes fail.
        if globs:
            if isinstance(globs, list):
                globs = ",".join(globs)
            q = q.filter_by(globs=globs)
        return q

    @classmethod
    def get_directory_status(cls, directory: Path, globs: str | list[str] | None = None) -> DirectoryStatus | None:
        session = DbManager.get_session()
        try:
            return (cls.query(session, directory, globs).first())
        finally:
            session.close()

    @classmethod
    def update(cls, directory: Path, file_count: int, last_modified_time : float | None = None, globs: str | list[str] | None = None):
        """
        Update or create the directory status record with the current file_count,
        the directory's last modified time, and the current VERSION.
        """
        directory = directory.absolute()
        session = DbManager.get_session()

        # Convert list of globs into a str
        if globs and isinstance(globs, list):
            globs = ",".join(globs)
        
        try:
            record = (cls.query(session, directory, globs).first())

            if not last_modified_time:
                if not directory.exists():
                    raise FileNotFoundError(f"Directory {directory} does not exist, and no last mod time provided.")
                last_modified_time = directory.stat().st_mtime

            if record is None:
                record = DirectoryStatus(
                    directory=str(directory),
                    file_count=file_count,
                    last_modified_time=last_modified_time,
                    version=VERSION,
                    globs=globs
                )
                session.add(record)
            else:
                record.file_count = file_count
                record.last_modified_time = last_modified_time
                record.version = VERSION
            session.commit()
        except sqlalchemy.exc.SQLAlchemyError as e:
            logger.error("Error updating directory status: %s", e)
            session.rollback()
        finally:
            session.close()

    @classmethod
    def has_directory_changed(cls, directory: Path, file_count: int, last_modified_time : float | None = None, globs : str | list[str] | None = None) -> bool:
        """
        Determine if we can skip processing a directory. We skip if:
          - The directory status exists,
          - The stored file_count matches the given file_count,
          - The directory's last_modified_time matches the stored one,
          - The stored version matches the current VERSION.

        If all these conditions are met, it means the directory has not changed
        since the last processing, and our version hasn't changed, so we can skip.
        """
        session = DbManager.get_session()
        try:
            record = (cls.query(session, directory, globs).first())

            if record is None:
                # No record means we have never processed this directory before
                return False

            if not last_modified_time:
                if not directory.exists():
                    raise FileNotFoundError(f"Directory {directory} does not exist, and no last mod time provided.")
                last_modified_time = directory.stat().st_mtime
            return (
                record.file_count == file_count
                and record.last_modified_time == last_modified_time
                and record.version == VERSION
            )
        finally:
            session.close()

    @classmethod
    def delete_directory_status(cls, directory: Path, globs: str | list[str] | None = None):
        """
        Delete the directory status record if it exists.
        """
        session = DbManager.get_session()
        try:
            cls.query(session, directory, globs).delete()
            session.commit()
        except sqlalchemy.exc.SQLAlchemyError as e:
            logger.error("Error deleting directory status: %s", e)
            session.rollback()
        finally:
            session.close()

    @classmethod
    def count_records(cls) -> int:
        """
        Get the number of records in the database.
        """
        session = DbManager.get_session()
        try:
            return cls.get_queryset(session).count()
        finally:
            session.close()

# Initialize the database at app start
DbManager.initialize_db()