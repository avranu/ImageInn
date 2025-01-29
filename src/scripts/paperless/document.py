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
from pydantic import BaseModel, Field

class CustomField(BaseModel):
    value: Any = None
    field: int

class PaperlessDocument(BaseModel):
    id: int
    correspondent: int | None
    document_type: int | None
    storage_path: int | None
    title: str
    content: str | None
    tags: list[int] = Field(default_factory=list)
    created: datetime
    created_date: date
    modified: datetime | None
    added: datetime
    deleted_at: datetime | None
    archive_serial_number: str | None
    original_file_name: str | None
    archived_file_name: str | None
    owner: int | None
    user_can_change: bool
    is_shared_by_requester: bool
    notes: list[dict[str, Any]] = Field(default_factory=list)
    custom_fields: list[CustomField] = Field(default_factory=list)
    page_count: int | None

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