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
*        Created: 2024-04-30                                                                                           *
*        Author:  Jess Mann                                                                                            *
*        Email:   jess.a.mann@gmail.com                                                                                *
*        Copyright (c) 2024 Jess Mann                                                                                  *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    LAST MODIFIED:                                                                                                    *
*                                                                                                                      *
*        2024-12-12     By Jess Mann                                                                                   *
*                                                                                                                      *
*********************************************************************************************************************"""
from __future__ import annotations
import colorlog
import logging

SUPPRESS_INFO = False

def setup_logging() -> logging.Logger:
	logging.basicConfig(level=logging.INFO)

	# Define a custom formatter class to supress info level names
	class CustomFormatter(colorlog.ColoredFormatter):

		def format(self, record):
			if SUPPRESS_INFO and record.levelno == logging.INFO:
				# Exclude the level name for INFO messages
				self._style._fmt = '%(message)s'
			else:
				# Include the level name for other levels
				self._style._fmt = '(%(log_color)s%(levelname)s%(reset)s) %(message)s'
			return super().format(record)

	# Configure colored logging with the custom formatter
	handler = colorlog.StreamHandler()
	handler.setFormatter(CustomFormatter(
	    # Initial format string (will be overridden in the formatter)
	    '',
	    log_colors={
	        'DEBUG': 'green',
	        'INFO': 'blue',
	        'WARNING': 'yellow',
	        'ERROR': 'red',
	        'CRITICAL': 'red,bg_white',
	    }))

	root_logger = logging.getLogger()
	root_logger.handlers = []  # Clear existing handlers
	root_logger.addHandler(handler)
	root_logger.setLevel(logging.INFO)

	return root_logger
