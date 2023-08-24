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
import errno
import os
import re
import sys
import logging, logging.config
from typing import Optional
from tqdm import tqdm

from scripts.lib.choices import Choices
from scripts.lib.path import FilePath, DirPath
from scripts.import_sd.photo import Photo
from scripts.import_sd.photostack import PhotoStack
from scripts.import_sd.workflow import Workflow
from scripts.import_sd.stackcollection import StackCollection
from scripts.import_sd.providers import tiff, merge, align

logger = logging.getLogger(__name__)

class Timeout(Choices):
	"""
	Enum for the different timeouts.
	"""
	HDR = 900			# 15 minutes
	TIFF = 300			# 5 minutes
	ALIGN = 300			# 5 minutes # TODO

class TiffMethods(Choices):
	"""
	Enum for the different methods to use for converting RAW to TIFF.
	"""
	RAWPY = 'rawpy'
	DARKTABLE = 'darktable-cli'

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

	tif_provider : tiff.TiffProvider
	align_provider : align.AlignmentProvider
	hdr_provider : merge.HDRProvider

	def __init__(self, base_path : str | list[str] | FilePath, raw_extension : str = 'arw', onconflict : OnConflict = OnConflict.OVERWRITE, dry_run : bool = False):
		self.base_path 		= base_path
		self.raw_extension 	= raw_extension
		self.dry_run 		= dry_run
		self.onconflict 	= onconflict

		self.tif_provider 	= tiff.DarktableProvider()
		self.align_provider = align.HuginProvider(self.aligned_path)
		self.hdr_provider 	= merge.EnfuseProvider()

	@property
	def hdr_path(self) -> DirPath:
		"""
		The path to the HDR directory.
		"""
		return self.base_path.child('hdr')

	@property
	def tiff_path(self) -> DirPath:
		"""
		The path to the tiff directory.
		"""
		return self.hdr_path.child('tiff')

	@property
	def aligned_path(self) -> DirPath:
		"""
		The path to the aligned directory.
		"""
		return self.hdr_path.child('aligned')

	def run(self) -> bool:
		"""
		Run the workflow.

		Returns:
			bool: Whether the workflow was successful.
		"""
		try:
			result = self.process_brackets()
		finally:
			self.cleanup()

		if result:
			logger.info('HDR workflow completed successfully. %d HDRs created.', len(result))
			return True

		logger.error('HDR workflow failed.')
		return False

	def cleanup(self):
		"""
		Clean up any temporary files created by the workflow.
		"""
		# Remove all _tmp files in both tiff_path and aligned_path
		for directory in [self.tiff_path, self.aligned_path]:
			for file in directory.get_files():
				if file.endswith('_tmp.tif'):
					self.delete(file)
				elif file.endswith('.tif_original'):
					self.delete(file)

			# Remove the directory if it is now empty
			self.rmdir(directory)

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
		job = {}

		'''
		# Multithreading support
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
		'''

		# Determine an output path for each file
		for photo in files:
			# Create a tiff filename
			tiff_name = re.sub(rf'\.{photo.extension}$', '.tif', photo.filename, flags=re.IGNORECASE)
			tiff_path = FilePath([self.tiff_path, tiff_name])

			# Handle conflicts
			if tiff_path.exists():
				tiff_path = self.handle_conflict(tiff_path)
				if tiff_path is None:
					logger.debug('Skipping existing file "%s"', photo.path)
					continue

			# Add _tmp to the filename until it is finished converting
			tmp_tiff_path = tiff_path.append_suffix('_tmp')

			# If the tmp file already exists, delete it
			if tmp_tiff_path.exists():
				logger.debug('Deleting existing tmp file %s', tmp_tiff_path)
				self.delete(tmp_tiff_path)

			job[photo] = tmp_tiff_path

		# Run the conversion
		results = self.tif_provider.run(job)

		return list(results.values())

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

		try:
			logger.critical('Aligning photos of types: %s', [type(photo) for photo in photos])
			aligned_photos = self.align_provider.run(tiff_files)
			logger.critical('Aligned photos return types: %s', [type(photo) for photo in aligned_photos])

		finally:
			# Delete the tiff files
			for tiff_file in tiff_files:
				# Ensure they end in .tif. This is technically unnecessary, but provides an extra layer of safety deleting files.
				if tiff_file.extension not in ['tif', 'tiff']:
					raise ValueError(f'Deleting tiff file {tiff_file}, but it does not end in .tif')

				logger.debug('Deleting %s', tiff_file)
				tiff_file.delete()
				FilePath(tiff_file.path + '_original').delete()

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
			raise ValueError(f'Not enough photos provided to create HDR at {self.hdr_path}')

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

		# If the file already exists, delete it
		if tmp_filepath.exists():
			logger.debug('Deleting existing file "%s"', tmp_filepath)
			self.delete(tmp_filepath)

		hdr = self.hdr_provider.run(photos, tmp_filepath)

		# Ensure the file was created
		if not self.dry_run and not hdr.exists():
			logger.error('Unable to create HDR image at %s', tmp_filepath)
			raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), tmp_filepath)

		# Rename the file
		hdr.rename(filename)

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
			raise ValueError(f'Not enough photos provided in bracket: {photos}')

		if isinstance(photos, PhotoStack):
			photos = photos.get_photos()

		# Determine the final HDR name, so we can figure out if it already exists and handle conflicts early.
		hdrname = self.name_hdr(photos)
		hdrpath = self.hdr_path.file(hdrname)
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
					logger.critical('Attempted to clean up aligned image that was not as expected. This should never happen. FilePath: %s', image.path)
					raise ValueError(f'Attempted to clean up aligned image that was not as expected. This should never happen. FilePath: {image.path}')

				FilePath(image.path + '_original').delete()
				image.delete()

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

		logger.debug('Found %d brackets, containing %d photos.', len(brackets), sum(len(bracket) for bracket in brackets))

		# Due to multithreading limitations in darktable, we can't run more than one darktable-cli process at a time.
		hdrs = []
		for bracket in brackets:
			hdr = self.process_single_bracket(bracket)
			if hdr:
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
				for i in range(100):
					newpath = path.append_suffix(f'_{i:02d}')
					if not newpath.exists():
						return newpath
				raise RuntimeError(f'Unable to find a new filename for {path}')

			case OnConflict.FAIL:
				logger.info('Failing on conflict %s', path)
				raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), path)

			case _:
				raise ValueError(f'Unknown onconflict value {self.onconflict}')

	def name_hdr(self, photos : list[Photo] | PhotoStack, output_dir : Optional[str | list[str] | DirPath] = None, short : bool = False) -> str:
		"""
		Create a new name for an HDR image based on a list of brackets that will be combined.

		Args:
			photos (list[Photo] | PhotoStack): The photos to combine.
			output_dir (str | DirPath, optional): The directory to save the HDR image to.
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
		elif not isinstance(output_dir, DirPath):
			output_dir = DirPath(output_dir)

		# Get the highest ISO
		iso = max(p.iso for p in photos)
		# Get the longest exposure
		ss = max(p.ss for p in photos)
		# Get the smallest brightness
		brightness = min(p.brightness for p in photos)
		# Get the average exposure value
		ev = sum(p.exposure_value for p in photos) / len(photos)

		first = photos[0]

		# Save the short filename no matter what, because we may use it later if the path is too long.
		short_filename = f'{first.ymd}_{first.number}_x{len(photos)}_{ev}EV_hdr.tif'

		if short:
			filename = short_filename
		else:
			filename = f'{first.ymd}_{first.camera}_{first.number}_x{len(photos)}_{brightness}B_{ev}EV_{iso}ISO_{ss}SS_{first.lens}_hdr.tif'

		# Replace spaces in the name with dashes
		filename = filename.replace(' ', '-')

		if short is False:
			path = FilePath([output_dir, filename])
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