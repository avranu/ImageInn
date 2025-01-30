"""*********************************************************************************************************************
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    METADATA:                                                                                                         *
*                                                                                                                      *
*        File:    document.py                                                                                          *
*        Project: imageinn                                                                                             *
*        Version: 0.1.0                                                                                                *
*        Created: 2025-01-29                                                                                           *
*        Author:  Jess Mann                                                                                            *
*        Email:   jess.a.mann@gmail.com                                                                                *
*        Copyright (c) 2025 Jess Mann                                                                                  *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    LAST MODIFIED:                                                                                                    *
*                                                                                                                      *
*        2025-01-29     By Jess Mann                                                                                   *
*                                                                                                                      *
*********************************************************************************************************************"""
from __future__ import annotations

from datetime import datetime, date
from typing import Any
from pydantic import BaseModel, Field, field_validator, ConfigDict
import dateparser
import logging

logger = logging.getLogger(__name__)

class CustomField(BaseModel):
    value: Any = None
    field: int

class PaperlessDocument(BaseModel):
    id: int
    correspondent: int | None = None
    document_type: int | None = None
    storage_path: int | None = None
    title: str
    content: str | None = None
    tags: list[int] = Field(default_factory=list)
    created: datetime | None = None
    created_date: date | datetime | None
    modified: datetime | None = None
    added: datetime | None = None
    deleted_at: datetime | None = None
    archive_serial_number: int | str | None = None
    original_file_name: str | None = None
    archived_file_name: str | None = None
    owner: int | None = None
    user_can_change: bool | None = None
    is_shared_by_requester: bool | None = None
    notes: list[dict[str, Any]] = Field(default_factory=list)
    custom_fields: list[CustomField] = Field(default_factory=list)
    page_count: int | None = None

    model_config = ConfigDict(arbitrary_types_allowed = True, extra="ignore")


    @field_validator("created_date", mode="before")
    def validate_created_date(cls, v: date | datetime | str | None) -> date | None:
        if isinstance(v, datetime):
            return v.date()
        elif isinstance(v, str):
            if parsed := dateparser.parse(v):
                return parsed.date()
            
            logger.error("Could not parse date")
            return None
        
        return v

    @field_validator("created", "modified", "added", "deleted_at", mode="before")
    def parse_datetime(cls, v: str | datetime | None) -> datetime | None:
        if isinstance(v, datetime) or v is None:
            return v
        
        if isinstance(v, str):
            parsed = dateparser.parse(v)
            if parsed:
                return parsed
            
            logger.error(f"Could not parse datetime: {v}")
            return None
        
        logger.error(f"Invalid datetime value: {v}")
        return None

    def get_corrected_date(self) -> date:
        """
        """
        # Check if the original filename is PXL_YYYYMMDD_*
        if self.original_file_name.startswith("PXL_"):
            date_str = self.original_file_name[4:12]
            try:
                taken_date = datetime.strptime(date_str, "%Y%m%d").date()
                # If the taken_date is earlier than the current document date, return the taken date
                if taken_date < self.created_date:
                    return taken_date
            except ValueError:
                pass

        # No correction found
        return self.created_date