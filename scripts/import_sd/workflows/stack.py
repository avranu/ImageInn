"""

	Metadata:

		File: workflow.py
		Project: imageinn
		Created Date: 11 Aug 2023
		Author: Jess Mann
		Email: jess.a.mann@gmail.com

		-----

		Last Modified: Wed Aug 23 2023
		Modified By: Jess Mann

		-----

		Copyright (c) 2023 Jess Mann
"""
from __future__ import annotations
import argparse
import os
import sys
import logging
from scripts.import_sd.workflow import Workflow
from scripts.import_sd.stackcollection import StackCollection

"""
from scripts.import_sd.config import MAX_RETRIES
from scripts.import_sd.operations import CopyOperation
from scripts.import_sd.validator import Validator
from scripts.lib.path import Path
from scripts.import_sd.photo import Photo
from scripts.import_sd.queue import Queue
from scripts.import_sd.sd import SDCard
from scripts.import_sd.workflow import Workflow
from scripts.import_sd.stackcollection import StackCollection
"""

logger = logging.getLogger(__name__)

class StackWorkflow(Workflow):
	"""
	Workflow for stacking photos.
	"""
	raw_extension : str
	dry_run : bool = False

	def __init__(self, base_path : str | list[str], raw_extension : str = 'arw', dry_run : bool = False):
		self.base_path = base_path
		self.raw_extension = raw_extension.lower()
		self.dry_run = dry_run

	def run(self) -> bool:
		"""
		Run the workflow.

		Returns:
			bool: Whether the workflow was successful.
		"""
		if self.stack_photos():
			return True
		return False

	def stack_photos(self) -> StackCollection:
		"""
		Stack photos in the base path.

		Returns:
			StackCollection: The collection of stacks.
		"""
		logger.info('Stacking photos in %s', self.base_path)

		# Get the list of photos
		photos = self.get_photos()

		# Create a new collection of stacks
		stack_collection = StackCollection()

		# Iterate over photos and stack adjascent ones with similar properties (but consistenetly differing exposure bias, or exposure value)
		stack_collection.add_photos(photos)

		logger.info('Created %d stacks from %s total photos', len(stack_collection), len(photos))

		return stack_collection.get_stacks()

def main():
	"""
	Entry point for the application.
	"""
	# Parse command line arguments
	parser = argparse.ArgumentParser(
		description='Run the Stack workflow.',
		prog=f'{os.path.basename(sys.argv[0])} {sys.argv[1]}'
	)
	# Ignore the first argument, which is the script name
	parser.add_argument('ignored', nargs='?', help=argparse.SUPPRESS)
	parser.add_argument('path', type=str, help='The path to the location of photos to stack.')
	parser.add_argument('--extension', '-e', default="arw", type=str, help='The extension to use for RAW files.')
	parser.add_argument('--dry-run', action='store_true', help='Whether to do a dry run, where no files are actually changed.')
	args = parser.parse_args()

	# Set up logging
	logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler()])
	logger.setLevel(logging.INFO)

	# Copy the SD card
	workflow = StackWorkflow(args.path, args.extension, args.dry_run)
	result = workflow.run()

	# Exit with the appropriate code
	if result:
		logger.info('Stack successful')
		sys.exit(0)

	logger.error('Stack failed')
	sys.exit(1)

if __name__ == '__main__':
	# Keep terminal open until script finishes and user presses enter
	try:
		main()
	except KeyboardInterrupt:
		pass

	input('Press Enter to exit...')