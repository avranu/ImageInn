"""*********************************************************************************************************************
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    METADATA:                                                                                                         *
*                                                                                                                      *
*        File:    meta.py                                                                                              *
*        Project: imageinn                                                                                             *
*        Version: 0.1.0                                                                                                *
*        Created: 2024-09-25                                                                                           *
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
from pathlib import Path

ALLOWED_EXTENSIONS = [
    # Images
    'jpg', 'jpeg', 'tiff', 'webp', 'tif', 'png', #'gif',
    # RAW
    'arw', 'dng', 'nef',
    # Videos
    'mp4', 'mov', 'avi', #'m4a', 'wmv', 'mkv', 'flv', 'webm',
    # Audio
    #'mp3', 'ogg', 'wav',
    # Photo editing
    #'psd', 'svg',
]

STATUS_FILE_NAME = '.upload_status.txt'

IGNORE_DIRS = [
    'Lightroom Catalog',
    'node_modules',
    '.trash',
]

DEFAULT_DB_PATH = Path(__file__).resolve().parents[3] / 'image_search.db'

MAX_RETRIES = 50
SECONDS_PER_RETRY = 15