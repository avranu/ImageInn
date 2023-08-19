"""
	
	Metadata:
	
		File: workflow.py
		Project: workflows
		Created Date: 11 Aug 2023
		Author: Jess Mann
		Email: jess.a.mann@gmail.com
	
		-----
	
		Last Modified: Sat Aug 19 2023
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

from scripts.import_sd.validator import Validator
from scripts.import_sd.workflow import Workflow

logger = logging.getLogger(__name__)

class RenameWorkflow(Workflow):
	_base_path: str
	raw_extension : str
	dry_run : bool = False

	def __init__(self, base_path : str, raw_extension : str = 'arw', dry_run : bool = False):
		"""
		Args:
			base_path (str): 
				The path to the network location to copy raw files from the SD Card to. 
				NOTE: This destination should be a "Photography" directory, where the files will be organized and renamed.
			raw_extension (str):
				The file extension of the raw files to copy. Defaults to 'arw'.
			dry_run (bool):
				Whether or not to actually copy files. Defaults to False.
		"""
		self.base_path = base_path
		self.raw_extension = raw_extension
		self.dry_run = dry_run

	@property
	def base_path(self) -> str:
		"""
		The path to the network location to copy raw files from the SD Card to.
		"""
		return self._base_path
	
	@base_path.setter
	def base_path(self, base_path: str) -> None:
		"""
		Set the path to the network location to copy raw files from the SD Card to.

		Args:
			base_path (str): The path to the network location to copy raw files from the SD Card to.
		"""
		if not Validator.is_dir(base_path):
			raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), base_path)
		self._base_path = self._normalize_path(base_path)

	def run(self) -> dict[str, str]:
		"""
		Rename files in the directory to the new naming scheme. 
		"""
		# Old format is: 20230805-a7r4-1935--7-10 EV-8.27B-ISO 800-SAMYANG AF 12mm F2.0.arw
		# New format is from self.generate_name()

		results = {}

		#old_format_regex = re.compile(r'^\d{8}-\w+-(\d{3,}|unknown)-.*B-ISO \d+-.*\.arw$', re.IGNORECASE)
		old_format_regex = re.compile(r'^_JAM_\d{4}.arw$', re.IGNORECASE)

		# Verify the paths exist
		if not all([os.path.exists(path) for path in [self.base_path]]):
			logger.info('One or more of the paths provided does not exist: "%s"', self.base_path)
			raise FileNotFoundError('Raw path does not exist.')

		# Find all files in the source_path that match the expected naming scheme
		count = 0
		for root, _, filenames in os.walk(self.base_path):
			for filename in filenames:
				matches = old_format_regex.match(filename)
				if matches:
					old_path = os.path.join(root, filename)
					# Determine the photo number from the old name
					number = matches.group(1)
					new_name = self.generate_name(old_path, properties={'number': number})
					new_path = os.path.join(root, new_name)
					results[old_path] = new_path
					logger.debug('QUEUE: %s -> %s', old_path, new_path)

					# Do not clobber existing files
					if os.path.exists(new_name):
						logger.warning('File already exists, skipping... %s', new_name)
						continue

					# Rename the file
					count += 1
					self.rename(old_path, new_path)

		logger.info('Renamed %d files', count)
		return results

def main():
	"""
	Entry point for the application.
	"""
	# Parse command line arguments
	parser = argparse.ArgumentParser(
		description='Run the Rename workflow.', 
		prog=f'{os.path.basename(sys.argv[0])} {sys.argv[1]}'
	)
	# Ignore the first argument, which is the script name
	parser.add_argument('ignored', nargs='?', help=argparse.SUPPRESS)
	parser.add_argument('path', type=str, help='The path to the network location where the photos are stored.')
	parser.add_argument('--extension', '-e', default="arw", type=str, help='The extension to use for RAW files.')
	parser.add_argument('--dry-run', action='store_true', help='Whether to do a dry run, where no files are actually changed.')
	args = parser.parse_args()

	# Set up logging
	logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler()])
	logger.setLevel(logging.INFO)

	# Copy the SD card
	workflow = RenameWorkflow(args.path, args.extension, args.dry_run)
	result = workflow.run()

	# Exit with the appropriate code
	if result:
		logger.info('Rename successful')
		sys.exit(0)

	logger.error('Rename failed')
	sys.exit(1)

if __name__ == '__main__':
	# Keep terminal open until script finishes and user presses enter
	try:
		main()
	except KeyboardInterrupt:
		pass

	input('Press Enter to exit...')