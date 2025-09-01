"""*********************************************************************************************************************
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    METADATA:                                                                                                         *
*                                                                                                                      *
*        File:    __init__.py                                                                                          *
*        Project: imageinn                                                                                             *
*        Version: 0.1.0                                                                                                *
*        Created: 2024-07-19                                                                                           *
*        Author:  Jess Mann                                                                                            *
*        Email:   jess.a.mann@gmail.com                                                                                *
*        Copyright (c) 2025 Jess Mann                                                                                  *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    LAST MODIFIED:                                                                                                    *
*                                                                                                                      *
*        2024-12-13     By Jess Mann                                                                                   *
*                                                                                                                      *
*********************************************************************************************************************"""
from scripts.processing.meta import (
    DEFAULT_CANVAS_SIZE,
	DEFAULT_MARGIN,
	DEFAULT_BLUR,
	DEFAULT_BRIGHTNESS,
	DEFAULT_CONTRAST,
	DEFAULT_SATURATION,
	DEFAULT_BORDER,
	AdjustmentTypes,
	Formats,
)
from scripts.processing.ig import IGImageProcessor, IGImage
from scripts.processing.bluesky import BlueskyProcessor, BlueskyImage