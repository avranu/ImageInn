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
import errno
import os
import re
import subprocess
import sys
import logging, logging.config
import time
from typing import Any, Dict, Optional, TypedDict
import exifread, exifread.utils, exifread.tags.exif, exifread.classes
from tqdm import tqdm

import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, TimeoutError as ConcurrentTimeoutError

from scripts.lib.choices import Choices
from scripts.import_sd.config import MAX_RETRIES
from scripts.import_sd.path import FilePath
from scripts.import_sd.photo import Photo
from scripts.import_sd.photostack import PhotoStack
from scripts.import_sd.workflow import Workflow
from scripts.import_sd.stackcollection import StackCollection

logger = logging.getLogger(__name__)

class Timeout(Choices):
	"""
	Enum for the different timeouts.
	"""
	HDR = 900			# 15 minutes
	TIFF = 300			# 5 minutes
	ALIGN = 300			# 5 minutes # TODO

MAX_THREADS = 4

class OnConflict(Choices):
	"""
	Enum for the different ways to handle conflicts.
	"""
	OVERWRITE = 'overwrite'
	RENAME = 'rename'
	SKIP = 'skip'
	FAIL = 'fail'

class HDRWorkflow(Workflow):
	"""
	Workflow for creating HDR photos from brakets found within imported photos.

	Args:
		base_path (str): The base path to the imported photos.
		raw_extension (str): The extension of the raw files.
		overwrite_temporary_files (bool): Whether to overwrite temporary files.
		dry_run (bool): Whether to run the workflow in dry run mode
	"""
	raw_extension : str
	dry_run : bool
	onconflict : OnConflict

	def __init__(self, base_path : str, raw_extension : str = 'arw', onconflict : OnConflict = OnConflict.OVERWRITE, dry_run : bool = False):
		self.base_path 		= base_path
		self.raw_extension 	= raw_extension
		self.dry_run 		= dry_run
		self.onconflict 	= onconflict

	@property
	def hdr_path(self) -> FilePath:
		"""
		The path to the HDR directory.
		"""
		return FilePath([self.base_path, 'hdr'])

	@property
	def tiff_path(self) -> str:
		"""
		The path to the tiff directory.
		"""
		return FilePath([self.hdr_path, 'tiff'])

	@property
	def aligned_path(self) -> str:
		"""
		The path to the aligned directory.
		"""
		return FilePath([self.hdr_path, 'aligned'])

	def run(self) -> bool:
		"""
		Run the workflow.

		Returns:
			bool: Whether the workflow was successful.
		"""
		try:
			result = self.process_brackets()
		finally:
			# Clean up empty directories
			for directory in [self.tiff_path, self.aligned_path]:
				self.rmdir(directory)

		if result:
			logger.info('HDR workflow completed successfully. %d HDRs created.', len(result))
			return True

		logger.error('HDR workflow failed.')
		return False

	def convert_to_tiff(self, files : list[Photo]) -> list[Photo]:
		"""
		Convert an ARW file to a TIFF file.

		Args:
			files (list[Photo]): The list of files to convert.

		Returns:
			list[Photo]: The list of converted files.

		Raises:
			FileNotFoundError: If the converted file cannot be found.
			FileFoundError: If self.onconflict is set to "fail" and the tif image already exists.
		"""
		# ImageMagick
		#tiff_files = self._subprocess_tif('convert', files)

		# Darktable
		tiff_files = self._subprocess_tif('darktable-cli', files)

		return tiff_files

	def _subprocess_single_tif(self, photo : Photo, exe : str) -> Photo:
		"""
		Convert a single raw photo to a TIFF file.

		Args:
			photo (Photo): The photo to convert.
			exe (str): The executable to use.

		Returns:
			Photo: The converted photo.
		"""
		# Create a tiff filename
		tiff_name = re.sub(rf'\.{photo.extension}$', '.tif', photo.filename, flags=re.IGNORECASE)
		tiff_path = FilePath([self.tiff_path, tiff_name])

		# Check if the file already exists
		if tiff_path.exists():
			tiff_path = self.handle_conflict(tiff_path)
			if not tiff_path:
				logger.debug('Skipping existing file "%s"', photo.path)
				return None

		# Add _tmp to the filename until it is finished converting
		tmp_tiff_path = tiff_path.append_suffix('_tmp')

		# If the tmp file already exists, delete it
		if tmp_tiff_path.exists():
			logger.debug('Deleting existing tmp file %s', tmp_tiff_path)
			self.delete(tmp_tiff_path)

		'''
		# darktable-cli doesn't like backslashes for the tiff path
		tiff_path_escaped = tmp_tiff_path
		if exe == 'darktable-cli':
			logger.debug('Replacing backslashes with forward slashes for darktable in %s', tmp_tiff_path)
			tiff_path_escaped = FilePath(tmp_tiff_path.replace('\\', '/'))
		'''


		for i in range(MAX_RETRIES):
			# Use the appropriate exe to convert the file
			logger.debug('Creating tiff file %s from %s using %s', tmp_tiff_path, photo.path, exe)
			output, error = self.subprocess([exe, photo.path, tmp_tiff_path.path], check=False)

			# DB still locked from last darktable process
			if re.search(r'the database lock file', error, re.IGNORECASE):
				# Wait a few seconds, then try again.
				logger.info('Database lock file detected. Waiting 5 seconds and trying again. (%d/%d)', i+1, MAX_RETRIES)
				time.sleep(5)
				continue

			# Otherwise, no need to loop more
			break

		# Check that it exists
		if not tmp_tiff_path.exists():
			logger.error('Could not find %s after conversion from %s using %s', tmp_tiff_path, photo.path, exe)
			logger.error('Output: %s', output)
			logger.error('Error: %s', error)
			raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), tmp_tiff_path)

		# Copy EXIF data using ExifTool
		logger.debug('Copying exif data from %s to %s', photo.path, tmp_tiff_path)
		self.subprocess(['exiftool', '-TagsFromFile', photo.path, '-all', tmp_tiff_path])

		# Rename the file to remove _tmp
		self.rename(tmp_tiff_path, tiff_path)

		# Return a photo object (ensuring the path exists) without the _tmp suffix.
		return Photo(tiff_path)

	def _subprocess_tif(self, exe: str, files: list[Photo]) -> list[Photo]:
		"""
		Convert a list of raw photos to TIFF files using multithreading and timeouts.

		Args:
			exe (str): The executable to use.
			files (list[Photo]): The photos to convert.

		Returns:
			list[Photo]: The converted photos.
		"""
		# Darktable cannot be run in parallel, so we need to run it sequentially.
		# -- This can apparently be addressed with the library param: darktable-cli --library /path/to/library.db <input file> <output file>
		# -- update: this does not appear to be true.
		results = []
		for photo in files:
			tif = self._subprocess_single_tif(photo, exe)
			results.append(tif)
			# Wait for cleanup
			time.sleep(1)
		return results

		with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
			futures = [executor.submit(self._subprocess_single_tif, photo, exe) for photo in files]
			tiff_files = []
			for future in tqdm(concurrent.futures.as_completed(futures), desc="Converting RAW to TIFF...", total=len(files), ncols=100):
				try:
					tiff_file = future.result(timeout=Timeout.TIFF)
					if tiff_file:
						tiff_files.append(tiff_file)
				except ConcurrentTimeoutError:
					logger.error("Conversion to TIFF timed out.")

			return tiff_files

	def align_images(self, photos : list[Photo] | PhotoStack) -> list[Photo]:
		"""
		Use Hugin to align the images.

		Args:
			photos (list[Photo]): The photos to align.

		Returns:
			list[Photo]: The aligned photos. If any of the photos cannot be aligned, an empty list will be returned.

		Raises:
			ValueError: If no photos are provided.
			FileNotFoundError: If the aligned photos are not created.
			FileFoundError: If self.onconflict is set to "fail" and the aligned image already exists.
		"""
		if not photos:
			raise ValueError('No photos provided')

		logger.debug('Aligning images...')

		# Create the output directory
		self.mkdir(self.aligned_path)

		# Convert RAW to tiff
		tiff_files = self.convert_to_tiff(photos)
		if not tiff_files:
			logger.error('Could not create any tiff files')
			return []
		if len(tiff_files) != len(photos):
			logger.error('Could not convert all photos to TIFF. Converted %d/%d photos', len(tiff_files), len(photos))
			return []

		aligned_photos : list[Photo] = []

		try:
			# TODO conflicts
			# Create the command
			command = ['align_image_stack', '-a', os.path.join(self.aligned_path, 'aligned_tmp_'), '-m', '-v', '-C', '-c', '100', '-g', '5', '-p', 'hugin.out', '-t', '0.3']
			for tiff in tiff_files:
				command.append(tiff.path)
			self.subprocess(command)

			# Create the photos
			for idx, photo in tqdm(enumerate(photos), desc="Aligning Images...", ncols=100):
				# Create the path.
				output_path = FilePath([self.aligned_path, f'aligned_{idx:04}.tif'])
				# Create a new file named {photo.filename}_aligned.{ext}
				filename = re.sub(rf'\.{photo.extension}$', '_aligned.tif', photo.filename)
				aligned_path = FilePath([self.aligned_path, filename])
				self.rename(output_path, aligned_path)

				# Copy EXIF data using ExifTool
				logger.debug('Copying exif data from %s to %s', photo.path, aligned_path)
				self.subprocess(['exiftool', '-TagsFromFile', photo.path, '-all', aligned_path])

				# Rename the file to remove _tmp
				clean_path = FilePath(re.sub(r'_tmp_', '_', aligned_path))
				self.rename(aligned_path, clean_path)

				# Add the photo to the list
				aligned_photo = self.get_photo(clean_path)
				aligned_photos.append(aligned_photo)

		except subprocess.CalledProcessError as e:
			logger.error('Could not align images -> %s', e)
			# Clean up aligned photos we created
			for aligned_photo in aligned_photos:
				self.delete(aligned_photo.path)
			return []

		finally:
			# Delete the tiff files
			for tiff in tiff_files:
				# Ensure they end in .tif. This is technically unnecessary, but provides an extra layer of safety deleting files.
				if not tiff.path.endswith('.tif'):
					raise ValueError(f'Deleting tiff file {tiff.path}, but it does not end in .tif')

				logger.debug('Deleting %s', tiff.path)
				self.delete(tiff.path)
				self.delete(tiff.path + '_original')

			# TODO: Remove any _tmp_ files that were created and not cleaned up. (Make sure to consider multithreading)

		return aligned_photos

	def create_hdr(self, photos : list[Photo] | PhotoStack, filename : Optional[Photo] = None) -> Photo | None:
		"""
		Use enfuse to create the HDR image.

		Args:
			photos (list[Photo]): The photos to combine.

		Returns:
			Photo: The HDR image.

		Raises:
			ValueError: If no photos are provided.
			FileNotFoundError: If the HDR image is not created.
			FileFoundError: If self.onconflict is set to "fail" and the HDR image already exists.
		"""
		if not photos or len(photos) < 2:
			raise ValueError('Not enough photos provided to create HDR at %s', self.hdr_path)

		logger.debug('Creating HDR...')

		# Create the output directory
		self.mkdir(self.hdr_path)

		# Name the file after the first photo
		if filename is None:
			filename = self.name_hdr(photos)
		filepath = FilePath([self.hdr_path, filename])

		# Handle conflicts
		if filepath.exists():
			filepath = self.handle_conflict(filepath)
			if filepath is None:
				logger.debug('Skipping existing file "%s"', filepath)
				return None

		# Add ".tmp" to the end of the filename until it is finished
		tmp_filepath = filepath.append_suffix('_tmp')
		tmp_filename = tmp_filepath.filename

		# If the file already exists, delete it
		if os.path.exists(tmp_filepath):
			logger.debug('Deleting existing file "%s"', tmp_filepath)
			self.delete(tmp_filepath)

		# Create the command
		command = ['enfuse', '-o', tmp_filepath, '-v']
		for photo in photos:
			command.append(photo.path)

		# Run the command
		try:
			self.subprocess(command)
		except subprocess.CalledProcessError as e:
			logger.error('Failed to create HDR image at %s -> %s', tmp_filepath, e)
			return None

		# Ensure the file was created
		if not self.dry_run and not os.path.exists(tmp_filepath):
			logger.error('Unable to create HDR image at %s', tmp_filepath)
			raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), tmp_filepath)

		# Rename the file
		self.rename(tmp_filepath, filepath)

		return self.get_photo(filepath)

	def process_single_bracket(self, photos : list[Photo] | PhotoStack) -> Photo | None:
		"""
		Process a bracket of photos into a single HDR.

		Args:
			photos (list[Photo]): The photos to process.

		Returns:
			Photo | None: The HDR image.

		Raises:
			ValueError: If no photos are provided.
			FileNotFoundError: If the HDR image is not created.
		"""
		if not photos or len(photos) < 2:
			raise ValueError('Not enough photos provided in bracket: %s', photos)

		# Determine the final HDR name, so we can figure out if it already exists and handle conflicts early.
		hdrname = self.name_hdr(photos)
		hdrpath = FilePath([self.hdr_path, hdrname])
		if hdrpath.exists():
			newpath = self.handle_conflict(hdrpath)
			if not newpath:
				logger.debug('Skipping bracket, because HDR already exists: "%s"', hdrpath)
				return self.get_photo(hdrpath)

			hdrpath = newpath

		images = self.align_images(photos)

		if not images or len(images) != len(photos):
			logger.error('Not enough aligned images were created, cannot create HDR. Found %d, expected %d', len(images), len(photos))
			return None

		try:
			hdr = self.create_hdr(images, hdrpath)
		finally:
			# Clean up the aligned images
			for image in tqdm(images, desc="Cleaning up aligned images...", ncols=100):
				# Ensure the filename ends with _aligned.tif
				# This is unnecessary, but we're going to be completely safe
				if not image.filename.endswith('_aligned.tif'):
					logger.critical('Attempted to clean up aligned image that was not as expected. This should never happen. Path: %s', image.path)
					raise ValueError(f'Attempted to clean up aligned image that was not as expected. This should never happen. Path: {image.path}')

				self.delete(image.path)
				self.delete(image.path + '_original')

			# TODO: Remove any _tmp_ files that were created and not cleaned up. (Make sure to consider multithreading)

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

		logger.debug('Found %d brackets, containing %d photos.', len(brackets), sum([len(bracket) for bracket in brackets]))

		# Due to multithreading limitations in darktable, we can't run more than one darktable-cli process at a time.
		hdrs = []
		for bracket in brackets:
			hdr = self.process_single_bracket(bracket)
			hdrs.append(hdr)

		'''
		# Process each bracket using multithreading
		with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
			futures = [executor.submit(self.process_single_bracket, bracket) for bracket in brackets]
			hdrs = []
			for future in tqdm(concurrent.futures.as_completed(futures), desc="Processing brackets...", total=len(brackets), ncols=100):
				try:
					hdr = future.result(timeout=Timeout.HDR)
					if hdr:
						logger.debug('Appending HDR image at %s', hdr.path)
						hdrs.append(hdr)
					else:
						logger.debug('HDR image was not created.')
				except ConcurrentTimeoutError:
					logger.error("Processing bracket timed out. Skipping this HDR.")
		'''

		logger.debug('Created %d HDR images', len(hdrs))

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

	def handle_conflict(self, path : Photo) -> FilePath | None:
		"""
		Handle a collision, where a temporary photo is being written to a location where a file already exists.

		The behavior of this operation will depend on the value of {self.onconflict}.

		Args:
			path (Photo): The path to the file that already exists.

		Returns:
			FilePath: The new path to write to. None if the file should be skipped.

		Raises:
			ValueError: If {self.onconflict} is not a valid value.
			FileExistsError: If {self.onconflict} is set to OnConflict.FAIL.
			RuntimeError: If a filename to use cannot be found.
		"""
		# First, ensure there is actually a conflict
		if not path.exists():
			return path

		match self.onconflict:
			case OnConflict.SKIP:
				logger.info('Skipping %s', path)
				return None

			case OnConflict.OVERWRITE:
				logger.info('Overwriting %s', path)
				# Remove the offending file
				self.delete(path)
				return path

			case OnConflict.RENAME:
				logger.info('Renaming %s', path)
				newpath = path
				for i in range(1, 100):
					newpath = path.filename.replace(f'.{path.extension}', f'_{i:02d}.{path.extension}')
					if not os.path.exists(newpath):
						return FilePath(newpath)
				raise RuntimeError('Unable to find a new filename for %s', path)

			case OnConflict.FAIL:
				logger.info('Failing on conflict %s', path)
				raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), path)

			case _:
				raise ValueError(f'Unknown onconflict value {self.onconflict}')

	def name_hdr(self, photos : list[Photo] | PhotoStack, output_dir : Optional[str] = None, short : bool = False) -> str:
		"""
		Create a new name for an HDR image based on a list of brackets that will be combined.

		Args:
			photos (list[Photo] | PhotoStack): The photos to combine.
			output_dir (str, optional): The directory to save the HDR image to.
			short (bool, optional): Whether to use the short filename or the long filename. Defaults to False (long).

		Returns:
			str: The new filename.

		Raises:
			ValueError: If no photos are provided.
		"""
		if not photos:
			raise ValueError('No photos provided')

		if not output_dir:
			output_dir = self.hdr_path

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

		# Replace spaces in the name with dashes
		filename = filename.replace(' ', '-')

		if short is False:
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
		description	= 'Run the HDR workflow.',
		prog		= f'{os.path.basename(sys.argv[0])} {sys.argv[1]}'
	)
	# Ignore the first argument, which is the script name
	parser.add_argument('ignored', 				nargs = '?', 					help = argparse.SUPPRESS)
	parser.add_argument('path', 				type = str, 				 	help = 'The path to the directory that contains the photos.')
	parser.add_argument('--extension', '-e', 	type = str, default = "arw",	help = 'The extension to use for RAW files.')
	parser.add_argument('--onconflict', '-c', 	type = str,
		     									default = OnConflict.OVERWRITE,
		     									choices = OnConflict.values(),	help = '''How to handle temporary files that already exist.
																						  This will not alter original RAW files. Only files that this process
																						  created in a previous run.''')
	parser.add_argument('--dry-run', 			action = 'store_true', 			help = 'Whether to do a dry run, where no files are actually changed.')

	# Parse the arguments passed in from the user
	args = parser.parse_args()

	# Copy the SD card
	workflow = HDRWorkflow(args.path, args.extension, args.onconflict, args.dry_run)
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