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
import subprocess
import logging
import time
from typing import Any, Dict, Optional, TypedDict
import exifread, exifread.utils, exifread.tags.exif, exifread.classes

from scripts.import_sd.config import MAX_RETRIES
from scripts.import_sd.operations import CopyOperation
from scripts.import_sd.validator import Validator
from scripts.import_sd.path import FilePath
from scripts.import_sd.photo import Photo
from scripts.import_sd.photostack import PhotoStack
from scripts.import_sd.queue import Queue
from scripts.import_sd.sd import SDCard
from scripts.import_sd.workflow import Workflow
from scripts.import_sd.stackcollection import StackCollection

logger = logging.getLogger(__name__)

class HDRWorkflow(Workflow):
	raw_extension : str
	dry_run : bool = False

	def __init__(self, base_path : str, raw_extension : str = 'arw', dry_run : bool = False):
		self.base_path = base_path
		self.raw_extension = raw_extension
		self.dry_run = dry_run

	def run(self) -> bool:
		self.process_brackets()

	def convert_to_tiff(self, arw_files):
		tiff_files = []
		for arw_file in arw_files:
			tiff_file = arw_file.replace('.arw', '.tif')
			command = ['darktable-cli', arw_file, tiff_file]
			if not self.dry_run:
				subprocess.run(command, check=True)
			tiff_files.append(tiff_file)
		return tiff_files
	
	def align_images(self, photos : list[Photo] | PhotoStack) -> list[Photo]:
		"""
		Use Hugin to align the images.

		Args:
			photos (list[Photo]): The photos to align.

		Returns:
			list[Photo]: The aligned photos.

		Raises:
			ValueError: If no photos are provided.
			FileNotFoundError: If the aligned photos are not created.
		"""
		if not photos:
			raise ValueError('No photos provided')
		
		
		logger.info('Aligning images...')
		# Create the output directory
		output_dir = os.path.join(self.base_path, 'hdr', 'aligned')
		if self.dry_run:
			logger.info(f'Would create directory {output_dir}')
		else:
			os.makedirs(output_dir, exist_ok=True)

		# Convert RAW to tiff
		arw_files = [photo.path for photo in photos]
		tiff_files = self.convert_to_tiff(arw_files)

		# Create the command
		command = ['align_image_stack', '-a', os.path.join(output_dir, 'aligned_'), '-m', '-v', '-C', '-c', '100', '-g', '5', '-p', 'hugin', '-t', '0.3'] + tiff_files

		# Run the command
		logger.debug(f'Running command: {command}')
		if self.dry_run:
			logger.info(f'Would run: {command}')
		else:
			subprocess.run(command, check=True)

		# Create the photos
		aligned_photos = []
		for idx, photo in enumerate(photos):
			# Create the path.
			output_path = os.path.join(output_dir, f'aligned_{idx:04}.tif')
			# Create a new file named {photo.filename}_aligned.{ext}
			filename = re.sub(rf'\.{photo.extension}$', '_aligned.tif', photo.filename)
			aligned_path = os.path.join(output_dir, filename)
			if self.dry_run:
				logger.info(f'Would rename {output_path} to {aligned_path}')
			else:
				os.rename(output_path, aligned_path)

			# Add the photo to the list
			if self.dry_run:
				logger.info(f'Would create Photo object for {aligned_path}')
			else:
				aligned_photos.append(Photo(aligned_path))

		return aligned_photos
	
	def create_hdr(self, photos : list[Photo] | PhotoStack) -> Photo:
		"""
		Use enfuse to create the HDR image.

		Args:
			photos (list[Photo]): The photos to combine.

		Returns:
			Photo: The HDR image.

		Raises:
			ValueError: If no photos are provided.
			FileNotFoundError: If the HDR image is not created.
		"""
		if not photos:
			raise ValueError('No photos provided')
		
		logger.info('Creating HDR...')
		# Create the output directory
		output_dir = os.path.join(self.base_path, 'hdr')

		if self.dry_run:
			logger.info(f'Would create directory {output_dir}')
		else:
			os.makedirs(output_dir, exist_ok=True)

		# Create the command. Name the file after the first photo
		filename = self.name_hdr(photos)
		filepath = os.path.join(output_dir, filename)
		command = ['enfuse', '-o', filepath, '-v', '-C', '-c', '100', '-g', '5', '-p', 'hugin', '-t', '0.3']
		for photo in photos:
			command.append(photo.path)

		# Run the command
		logger.debug(f'Running command: {command}')
		if self.dry_run:
			logger.info(f'Would run: {command}')
		else:
			subprocess.run(command, check=True)

		# Ensure the file was created
		if not self.dry_run and not os.path.exists(filepath):
			logger.error('Unable to create HDR image at %s', filepath)
			raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), filepath)

		if self.dry_run:
			logger.info(f'Would create Photo object for {filepath}')
			return None
		return Photo(filepath)
	
	def process_bracket(self, photos : list[Photo] | PhotoStack) -> Photo:
		"""
		Process a bracket of photos into a single HDR.

		Args:
			photos (list[Photo]): The photos to process.

		Returns:
			Photo: The HDR image.

		Raises:
			ValueError: If no photos are provided.
			FileNotFoundError: If the HDR image is not created.
		"""
		images = self.align_images(photos)
		hdr = self.create_hdr(images)
		
		# Clean up the aligned images
		for image in images:
			# Ensure the filename ends with _aligned.tif
			# This is unnecessary, but we're going to be completely safe
			if not image.filename.endswith('_aligned.tif'):
				logger.critical('Attempted to clean up aligned image that was not as expected. This should never happen. Path: %s', image.path)
				raise ValueError(f'Attempted to clean up aligned image that was not as expected. This should never happen. Path: {image.path}')
			
			if self.dry_run:
				logger.info(f'Would remove {image.path}')
			else:
				os.remove(image.path)

		# Remove the aligned images directory, only if it is completely empty
		try:
			directory = os.path.join(self.base_path, 'hdr', 'aligned')
			if self.dry_run:
				logger.info(f'Would remove directory {directory}')
			else:
				os.rmdir(directory)
		except OSError as e:
			if e.errno != errno.ENOTEMPTY:
				raise e

		return hdr
	
	def process_brackets(self) -> list[Photo]:
		"""
		Process all brackets in the base directory, and returns a list of paths to HDR images.

		Returns:
			list[Photo]: The HDR images.
		"""
		# Get all the brackets in the directory
		brackets = self.find_brackets()

		if not brackets:
			logger.info('No brackets found in %s', self.base_path)
			return []

		# Process each bracket
		hdrs = []
		for bracket in brackets:
			hdr = self.process_bracket(bracket)
			hdrs.append(hdr)

		return hdrs

	def find_brackets(self) -> list[PhotoStack]:
		"""
		Find all brackets in the base directory.
		
		Returns:
			list[PhotoStack]: The brackets.	
		"""
		# Get the list of photos
		photos = self.get_photos()

		if not photos:
			logger.info('No photos found in %s', self.base_path)
			return []

		# Create a new collection of stacks
		stack_collection = StackCollection()

		# Iterate over photos and stack adjascent ones with similar properties (but consistenetly differing exposure bias, or exposure value)
		stack_collection.add_photos(photos)

		logger.info('Created %d stacks from %s total photos', len(stack_collection), len(photos))

		return stack_collection.get_stacks()
	
	def name_hdr(self, photos : list[Photo], output_dir : str = '', short : bool = False) -> str:
		"""
		Create a new name for an HDR image based on a list of brackets that will be combined.

		Args:
			photos (list[Photo]): The photos to combine.
			output_dir (str, optional): The directory to save the HDR image to. 
			short (bool, optional): Whether to use the short filename or the long filename. Defaults to False (long).

		Returns:
			str: The new filename.

		Raises:
			ValueError: If no photos are provided.
		"""
		if not photos:
			raise ValueError('No photos provided')
		
		# Get the highest ISO
		iso = max([p.iso for p in photos])
		# Get the longest exposure
		ss = max([p.ss for p in photos])
		# Get the smallest brightness
		brightness = min([p.brightness for p in photos])
		# Get the average exposure value
		ev = sum([p.exposure_value for p in photos]) / len(photos)
		
		first = photos[0]
		# Save the short filename no matter what, because we may use it later if the path is too long.
		short_filename = f'{first.date.strftime("%Y%m%d")}_{first.number}_x{len(photos)}_{ev}EV_hdr.tif'

		if short:
			filename = short_filename
		else:
			filename = f'{first.date.strftime("%Y%m%d")}_{first.camera}_{first.number}_x{len(photos)}_{brightness}B_{ev}EV_{iso}ISO_{ss}SS_{first.lens}_hdr.tif'
		
		if short is False and output_dir:
			path = os.path.join(output_dir, filename)
			if len(path) > 255:
				logger.info('Filename is too long, shortening it: %s', path)
				filename = short_filename
		
		return filename
	
def main():
	"""
	Entry point for the application.
	"""
	# Parse command line arguments
	parser = argparse.ArgumentParser(
		description='Run the HDR workflow.',
		prog=f'{os.path.basename(sys.argv[0])} {sys.argv[1]}'
	)
	# Ignore the first argument, which is the script name
	parser.add_argument('ignored', nargs='?', help=argparse.SUPPRESS)
	parser.add_argument('path', type=str, help='The path to the directory that contains the photos.')
	parser.add_argument('--extension', '-e', default="arw", type=str, help='The extension to use for RAW files.')
	parser.add_argument('--dry-run', action='store_true', help='Whether to do a dry run, where no files are actually changed.')
	args = parser.parse_args()

	# Set up logging
	logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler()])
	logger.setLevel(logging.INFO)

	# Copy the SD card
	workflow = HDRWorkflow(args.path, args.extension, args.dry_run)
	result = workflow.run()

	# Exit with the appropriate code
	if result:
		logger.info('Create HDR successful')
		sys.exit(0)

	logger.error('Create HDR failed')
	sys.exit(1)

if __name__ == '__main__':
	# Keep terminal open until script finishes and user presses enter
	try:
		main()
	except KeyboardInterrupt:
		pass

	input('Press Enter to exit...')