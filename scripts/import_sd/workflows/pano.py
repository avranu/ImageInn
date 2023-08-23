"""

	Metadata:

		File: workflow.py
		Project: workflows
		Created Date: 11 Aug 2023
		Author: Jess Mann
		Email: jess.a.mann@gmail.com

		-----

		Last Modified: Tue Aug 22 2023
		Modified By: Jess Mann

		-----

		Copyright (c) 2023 Jess Mann
"""
from __future__ import annotations
import argparse
import datetime
from enum import Enum
import errno
import os
import re
import sys
import logging
import time
from typing import Any, Dict, Optional, TypedDict
import exifread, exifread.utils, exifread.tags.exif, exifread.classes

from scripts.import_sd.config import MAX_RETRIES
from scripts.import_sd.operations import CopyOperation
from scripts.import_sd.validator import Validator
from scripts.lib.path import Path
from scripts.import_sd.photo import Photo
from scripts.import_sd.queue import Queue
from scripts.import_sd.sd import SDCard
from scripts.import_sd.workflow import Workflow

logger = logging.getLogger(__name__)

class PanoramaWorkflow(Workflow):
	raw_extension : str
	dry_run : bool = False

	def __init__(self, base_path : str, raw_extension : str = 'arw', dry_run : bool = False):
		self.base_path = base_path
		self.raw_extension = raw_extension
		self.dry_run = dry_run

	def run(self) -> bool:
		raise NotImplementedError()

def main():
	"""
	Entry point for the application.
	"""
	# Parse command line arguments
	parser = argparse.ArgumentParser(
		description='Run this workflow action.',
		prog=f'{os.path.basename(sys.argv[0])} {sys.argv[1]}'
	)
	# Ignore the first argument, which is the script name
	parser.add_argument('ignored', nargs='?', help=argparse.SUPPRESS)
	parser.add_argument('--base-path', '-r', default="R:/", type=str, help='The path to the network location to copy RAWs from the SD card to.')
	parser.add_argument('--extension', '-e', default="arw", type=str, help='The extension to use for RAW files.')
	parser.add_argument('--dry-run', action='store_true', help='Whether to do a dry run, where no files are actually changed.')
	args = parser.parse_args()

	# Set up logging
	logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler()])
	logger.setLevel(logging.INFO)

	# Copy the SD card
	workflow = PanoramaWorkflow(args.base_path, args.extension, args.dry_run)
	result = workflow.run()

	# Exit with the appropriate code
	if result:
		logger.info('Create pano successful')
		sys.exit(0)

	logger.error('Create pano failed')
	sys.exit(1)

if __name__ == '__main__':
	# Keep terminal open until script finishes and user presses enter
	try:
		main()
	except KeyboardInterrupt:
		pass

	input('Press Enter to exit...')