"""*********************************************************************************************************************
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    METADATA:                                                                                                         *
*                                                                                                                      *
*        File:    utils.py                                                                                             *
*        Project: imageinn                                                                                             *
*        Version: 0.1.0                                                                                                *
*        Created: 2024-10-29                                                                                           *
*        Author:  Jess Mann                                                                                            *
*        Email:   jess.a.mann@gmail.com                                                                                *
*        Copyright (c) 2024 Jess Mann                                                                                  *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    LAST MODIFIED:                                                                                                    *
*                                                                                                                      *
*        2024-10-29     By Jess Mann                                                                                   *
*                                                                                                                      *
*********************************************************************************************************************"""
from __future__ import annotations
from decimal import Decimal

def seconds_to_human(total_seconds: int | float | Decimal) -> str:
    """
    Convert seconds to human readable format
    """
    if not total_seconds:
        return '0 seconds'
    
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{int(days)} day{'s' if days > 1 else ''}")
    if hours:
        parts.append(f"{int(hours)} hour{'s' if hours > 1 else ''}")
    if minutes:
        parts.append(f"{int(minutes)} minute{'s' if minutes > 1 else ''}")
    if seconds:
        parts.append(f"{round(seconds)} second{'s' if seconds > 1 else ''}")
    return ', '.join(parts)