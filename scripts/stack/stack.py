"""

	Metadata:

		File: stack.py
		Project: stack
		Created Date: 01 Apr 2023
		Author: Jess Mann
		Email: jess.a.mann@gmail.com

		-----

		Last Modified: Wed Aug 23 2023
		Modified By: Jess Mann

		-----

		Copyright (c) 2023 Jess Mann
"""

from __future__ import annotations
import shutil
from typing import List, Dict, Optional, Tuple
import os
from datetime import datetime, timedelta
from typing import Optional
import exifread
import yaml
import argparse
import logging
import logging.config
from tqdm import tqdm
from enum import Enum

from scripts.lib.path import FilePath, DirPath

logger = logging.getLogger(__name__)

class ExifAttribute(Enum):
	TIMESTAMP = "EXIF DateTimeOriginal"
	EXPOSURE_BIAS = "EXIF ExposureBiasValue"
	FOCAL_LENGTH = "EXIF FocalLength"
	ISO = "EXIF ISOSpeedRatings"
	APERTURE = "EXIF FNumber"
	SHUTTER_SPEED = "EXIF ShutterSpeedValue"
	CAMERA_MAKE = "Image Make"
	CAMERA_MODEL = "Image Model"
	METERING_MODE = "EXIF MeteringMode"
	FLASH = "EXIF Flash"
	WHITE_BALANCE = "EXIF WhiteBalance"
	EXPOSURE_MODE = "EXIF ExposureMode"
	COLOR_SPACE = "EXIF ColorSpace"
	X_RESOLUTION = "EXIF XResolution"
	Y_RESOLUTION = "EXIF YResolution"
	IMAGE_WIDTH = "EXIF ExifImageWidth"
	IMAGE_HEIGHT = "EXIF ExifImageLength"
	IMAGE_ORIENTATION = "Image Orientation"
	IMAGE_RESOLUTION_UNIT = "EXIF ResolutionUnit"
	IMAGE_X_RESOLUTION = "EXIF XResolution"
	IMAGE_Y_RESOLUTION = "EXIF YResolution"
	GPS_LATITUDE = "EXIF GPSLatitude"
	GPS_LONGITUDE = "EXIF GPSLongitude"
	GPS_ALTITUDE = "EXIF GPSAltitude"

class Stack:
	"""
	A class for finding image stacks in a folder and writing XMP metadata. This is intended to be run before importing images into Lightroom.

	Attributes
		folder_path : str
			The path to the folder containing the images.
		file_prefix : str
			The prefix used for the image file names.

	Methods
		find_stacks()
			Finds image stacks in the folder and writes XMP metadata.
	"""

	_config : dict = dict()
	_folder_path: DirPath
	_file_prefix: str = ''
	_file_suffix: str = '.NEF'
	_verbose: bool = False

	def __init__(self, options : dict = dict()):
		self._load_config(options)

	@property
	def folder_path(self) -> str:
		return self._folder_path

	@property
	def file_prefix(self) -> str:
		return self._file_prefix

	@property
	def file_suffix(self) -> str:
		return self._file_suffix

	@property
	def verbose(self) -> bool:
		return self._verbose

	@property
	def config(self) -> dict:
		return self._config

	@property
	def max_stack_size(self) -> int:
		"""
		Returns the maximum number of images in a stack.
		"""
		return self.config.get('max_stack_size', 3)

	def get_path(self, path : str) -> DirPath:
		"""
		Returns the path to a directory in the folder.

		Args:
			path : str
				The path to get, within the context of the base path.
		"""
		return os.path.join(self.config['paths']['base'], path)

	def get_path_by_name(self, name : str) -> str:
		"""
		Returns the path to a directory in the folder.

		Args:
			name : str
				The name of the path to get, as defined in the config file.
		"""
		return self.get_path(self.config['paths'][name])

	def get_template_path(self, template_name : str) -> str:
		"""
		Returns the path to a template file.

		Args:
			template_name : str
				The name of the template to get, as defined in the config file.
		"""
		return os.path.join( self.get_path_by_name('templates'), self.config['templates'][template_name] )

	def _load_config(self, options : dict = dict()) -> None:
		"""
		Loads the configuration options from the YAML file.

		Args:
			options : dict
				Any options to override the configuration file.

		Returns:
			None
		"""
		config_file = options.get('config', '/home/jess/personal/lightroom/import/config/base.yaml')
		print('Loading configuration at %s', config_file)
		with open(options.get('config', config_file), "r") as f:
			config = yaml.safe_load(f)
			self._config = config

		# Configure the logging module with the loaded configuration
		logging.config.dictConfig(config['logging'])

		self._folder_path = self.get_path( options.get('folder', config["paths"]["images"]) )
		self._file_prefix = options.get('prefix', config["templates"]["image"]["prefix"])
		self._file_suffix = options.get('suffix', config["templates"]["image"]["suffix"])
		self._verbose = options.get('verbose', config.get("verbose", False))

		if self.verbose:
			logger.setLevel(logging.DEBUG)

		logger.debug('Config loaded: %s, %s, %s, %s', self.folder_path, self.file_prefix, self.file_suffix, self.verbose)

	def read_exif_data(self, file_path: str) -> Dict[str, exifread.ExifTag]:
		"""
		Reads the EXIF data from an image file.

		Args:
			file_path : str
				The path to the image file.

		Returns:
			Dict[str, exifread.ExifTag]:
				A dictionary of EXIF tags.
		"""
		logger.debug('Reading EXIF data from %s', file_path)
		try:
			with open(file_path, "rb") as f:
				tags = exifread.process_file(f, details=False)
			return tags
		except Exception as e:
			logger.error("Error reading EXIF data from %s: %s", file_path, e)
			return {}

	def get_image_exif_attribute(self, attribute: ExifAttribute, file_path: str) -> Optional[float]:
		"""
		Gets an EXIF attribute from the EXIF data for an image file.

		Args:
			attribute: ExifAttribute
				The EXIF attribute to retrieve.
			file_path : str
				The path to the image file.

		Returns:
			Optional[float]:
				The EXIF attribute from the EXIF data, or None if it could not be read.
		"""
		tags = self.read_exif_data(file_path)
		return self.get_image_exif_attribute_from_tags(attribute, tags)

	def get_image_exif_attribute_from_tags(self, attribute: ExifAttribute, tags: Dict[str, exifread.ExifTag]) -> Optional[float]:
		"""
		Gets an EXIF attribute from the EXIF data for an image file.

		Args:
			attribute: ExifAttribute
				The EXIF attribute to retrieve.
			tags : Dict[str, exifread.ExifTag]
				The EXIF tags.

		Returns:
			Optional[float]:
				The EXIF attribute from the EXIF data, or None if it could not be read.
		"""
		if attribute.value not in tags:
			return None

		# Handle special cases
		if attribute == ExifAttribute.TIMESTAMP:
			logger.debug('Returning timestamp for %s', tags[attribute.value])
			return datetime.strptime(str(tags[attribute.value]), "%Y:%m:%d %H:%M:%S")

		# Default case
		logger.debug('Returning %s for %s', tags[attribute.value].values[0], tags[attribute.value])
		return float(tags[attribute.value].values[0])

	def get_images(self, folder_path: str = None) -> List[os.DirEntry[str]]:
		"""
		Gets a list of images in the folder.

		Args:
			folder_path : str
				The path to the folder containing the images.

		Returns:
			List[Image]:
				A list of Image objects.
		"""
		folder_path = folder_path or self.folder_path
		logger.debug('Getting images from %s', folder_path)
		files = []
		for file_name in os.listdir(folder_path):
			# Open all directories within this base directory and traverse each one looking for files that match the prefix and suffix
			if os.path.isdir(os.path.join(folder_path, file_name)):
				# Skip directories starting with an underscore
				if file_name.startswith("_"):
					logger.debug('Skipping subdirectory beginning with "_": %s', file_name)
					continue

				# Skip hidden directories
				if file_name.startswith("."):
					logger.debug('Skipping subdirectory beginning with ".": %s', file_name)
					continue

				logger.debug('Adding images from subdirectory: %s', file_name)
				files.extend(self.get_images(os.path.join(folder_path, file_name)))
			else:
				if file_name.startswith(self.file_prefix) and file_name.endswith(self.file_suffix):
					logger.debug('Adding image: %s', file_name)
					files.append(os.path.join(folder_path, file_name))

		logger.debug('Found %d images', len(files))
		return files

	def group_images_by_date_time(self, file_list: List[os.DirEntry[str]]) -> Dict[str, List[os.DirEntry[str]]]:
		"""
		Groups images by their date and time.

		Args:
			file_list : List[os.DirEntry[str]]
				A list of file paths.

		Returns:
			A dictionary with the date and time as the key and a list of file paths as the value.
		"""
		# Create a dictionary to store the images by date/time
		images_by_date_time = {}
		logger.debug('Attempting to group images by date')

		# Loop through the files in the list
		for file_entry in file_list:
			try:
				# Get the EXIF data for the file
				exif_data = self.read_exif_data(file_entry)
				# Get the date/time from the EXIF data
				date_time = exif_data["EXIF DateTimeOriginal"]
				# Store the file in the dictionary using the date/time as the key
				images_by_date_time.setdefault(str(date_time), []).append(file_entry)

			# Catch any errors thrown by the EXIF functions
			except KeyError as e:
				# Log the error
				logger.debug("Failed to read EXIF data for %s: %s", file_entry.path, e)

		logger.debug('Found %d images grouped by date/time', len(images_by_date_time))
		# Return the dictionary of images
		return images_by_date_time

	def find_brackets(self, file_list: Optional[List[os.DirEntry[str]]] = None) -> List[List[os.DirEntry[str]]]:
		"""
		Finds bracketed images in a list of files.

		Args:
			file_list : List[os.DirEntry[str]]
				A list of file paths.

		Returns:
			List[Image]:
				A list of Image objects.
		"""
		# Create a list to store the bracketed images
		brackets = []

		# Get the list of images if one was not passed in
		file_list = file_list or self.get_images()

		# Group the images by date/time
		images_by_date_time = self.group_images_by_date_time(file_list)

		# Loop through the images grouped by date/time
		for date_time, image_list in images_by_date_time.items():
			# If there are more than one image in the list, they are bracketed
			if len(image_list) > 1:
				bracket = []
				# Loop through the images in the list
				for image in image_list:
					# Add the image to the list of bracketed images
					bracket.append(image)
				brackets.append(bracket)

		# Return the list of bracketed images
		logger.debug('Found %d brackets', len(brackets))
		return brackets

	def echo_bracketed_images(self, image_list: Optional[List[os.DirEntry[str]]] = None) -> None:
		"""
		Prints a list of bracketed images in a list of files.

		Args:
			image_list : List[PIL.Image.Image]
				A list of images.
		"""
		# Group the images by their bracket
		brackets = self.find_brackets(image_list)

		for i, bracket in enumerate(brackets):
			for image in bracket:
				tags = self.read_exif_data(image)
				date = self.get_image_exif_attribute_from_tags(ExifAttribute.TIMESTAMP, tags)
				bias = self.get_image_exif_attribute_from_tags(ExifAttribute.EXPOSURE_BIAS, tags)
				print(f'{i} - {image} [Date: {date}] [Bias: {bias}] - {image}')

	def move_brackets_to_subfolders(self, image_list: Optional[List[os.DirEntry[str]]] = None) -> int:
		"""
		Moves bracketed images to subfolders.

		Args:
			image_list : List[PIL.Image.Image]
				A list of images.

		Returns:
			int:
				The number of images moved.
		"""
		# Group the images by their bracket
		brackets = self.find_brackets(image_list)
		logger.debug('Moving %d brackets to subfolders.', len(brackets))
		count : int = 0

		for i, bracket in enumerate(brackets):
			# Create a subfolder for the bracket
			subfolder = os.path.join(self.folder_path, f'bracket_{i}')
			# create the subfolder if it doesn't exist
			if not os.path.exists(subfolder):
				logger.debug('Making new bracket folder: %s', subfolder)
				os.makedirs(subfolder)

			# Move the images to the subfolder
			for image in bracket:
				shutil.move(image, subfolder)
				count += 1

		logger.info('Moved %d images to subfolders.', count)
		return count

if __name__ == '__main__':
	"""
	Main function for the script. Handles command line arguments and calls the Stack class.
	"""
	parser = argparse.ArgumentParser(description='Stack bracketed photos, and write XMP metadata to indicate that they are part of a stack.')
	parser.add_argument('-c', '--config', type=str, default='/home/jess/personal/lightroom/import/config/base.yaml', help='path to YAML configuration file')
	parser.add_argument('-p', '--prefix', type=str, default='JAM', help='file name prefix for images to stack')
	parser.add_argument('-s', '--suffix', type=str, default='.NEF', help='file name suffix for images to stack')
	parser.add_argument('-f', '--folder', type=str, default='images', help='path to folder containing images to stack')
	parser.add_argument('-v', '--verbose', action='store_true', help='print verbose output')
	args = parser.parse_args()

	print('Starting bracket stacking.')

	stack = Stack(vars(args))

	images = stack.move_brackets_to_subfolders()
	#stack.echo_bracketed_images()

	logger.debug('Script finished: %d images moved to subfolders.', images)