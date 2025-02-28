"""*********************************************************************************************************************
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    METADATA:                                                                                                         *
*                                                                                                                      *
*        File:    logging.py                                                                                           *
*        Project: imageinn                                                                                             *
*        Version: 0.1.0                                                                                                *
*        Created: 2025-01-09                                                                                           *
*        Author:  Jess Mann                                                                                            *
*        Email:   jess.a.mann@gmail.com                                                                                *
*        Copyright (c) 2025 Jess Mann                                                                                  *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    LAST MODIFIED:                                                                                                    *
*                                                                                                                      *
*        2025-01-09     By Jess Mann                                                                                   *
*                                                                                                                      *
*********************************************************************************************************************"""
import logging
import colorlog

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
