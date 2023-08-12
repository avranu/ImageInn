from __future__ import annotations
import datetime
from enum import Enum
import errno
import os
import re
import logging
from typing import Any, Dict, Optional, TypedDict
import exifread, exifread.utils, exifread.tags.exif, exifread.classes
from scripts.import_sd.exif import ExifTag
from scripts.import_sd.validator import Validator

logger = logging.getLogger(__name__)

class Photo:
	"""
	Allows us to interact with sd cards mounted to the server this code is running on.
	"""
	_path: str

	def __init__(self, path : str):
		"""
		Args:
			path (str): The path to the photo.
		"""
		self.path = path

	@property
	def path(self) -> str:
		"""
		The path to the photo.
		"""
		return self._path
	
	@path.setter
	def path(self, value : str):
		"""
		The path to the photo.
		"""
		if not os.path.exists(value):
			raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), value)
		
		if not os.path.isfile(value):
			raise ValueError('Path must be a file')
		
		self._path = value
	
	@property
	def aperture(self) -> float:
		"""
		Get the aperture from the EXIF data of the given file.

		Returns:
			float: The aperture (as a float, not a ratio)

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> photo.aperture
			'2.8'
		"""
		result = self.attr(self.path, ExifTag.APERTURE)
		# Round up, always
		return round(result, 2)
	
	@property
	def brightness(self) -> float:
		"""
		Get the brightness value from the EXIF data of the given file.

		Returns:
			str: The brightness value.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> photo.brightness
			'-8.27'
		"""
		result = self.attr(self.path, ExifTag.BRIGHTNESS)

		# Round up the 2nd decimal place. Always round up, never down. 
		return round(result, 2)
	
	@property
	def camera(self) -> str:
		"""
		Get the camera model from the EXIF data of the given file.

		Returns:
			str: The camera model.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> photo.camera
			'a7r4'
		"""
		return self.attr(self.path, ExifTag.CAMERA)
	
	@property
	def date(self) -> datetime:
		"""
		Get the date from the EXIF data of the given file.

		Returns:
			datetime: The date.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> photo.date
			'2020-01-01 12:00:00'
		"""
		value = self.attr(self.path, ExifTag.DATE)
		return datetime.datetime.strptime(value, '%Y:%m:%d %H:%M:%S')
	
	@property
	def dimensions(self) -> Dict[str, int]:
		"""
		Get the dimensions from the EXIF data of the given file.

		Returns:
			dict: The dimensions.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> photo.dimensions
			{'height': 4000, 'width': 6000}
		"""
		value = self.attr(self.path, ExifTag.DIMENSIONS)
		return {
			'height': value[0],
			'width': value[1]
		}

	@property
	def exposure_bias(self) -> float:
		"""
		Get the exposure bias from the EXIF data of the given file.

		Returns:
			str: The exposure bias.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> photo.exposure_bias
			'-2 7'
		"""
		result = self.attr(self.path, ExifTag.EXPOSURE_BIAS)
		# Round up the 2nd decimal place, always
		return round(result, 2)
	

	@property
	def exposure_mode(self) -> str:
		"""
		Get the exposure mode from the EXIF data of the given file.

		Returns:
			str: The exposure mode.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')

		"""
		return self.attr(self.path, ExifTag.EXPOSURE_MODE)

	@property
	def exposure_program(self) -> str:
		"""
		Get the exposure program from the EXIF data of the given file.

		Returns:
			str: The exposure program.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')

		"""
		return self.attr(self.path, ExifTag.EXPOSURE_PROGRAM)

	@property
	def exposure_time(self) -> float:
		"""
		Get the exposure time from the EXIF data of the given file.

		Returns:
			float: The exposure time (as a float, not a ratio)

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> photo.exposure_time
			'0.0125'
		"""
		result = self.attr(self.path, ExifTag.EXPOSURE_TIME)
		# Round up the 10th decimal place, always
		return round(result, 10)
	
	@property
	def f(self) -> float:
		"""
		Get the f-number from the EXIF data of the given file.

		Returns:
			float: The f-number (as a float, not a ratio)

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> photo.f_number
			'2.8'
		"""
		result = self.attr(self.path, ExifTag.F)
		# Round up, always
		return round(result, 2)

	@property
	def flash(self) -> bool:
		"""
		Get the flash status from the EXIF data of the given file.

		Returns:
			bool: True if flash was used, False otherwise.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			True
		"""
		return self.attr(self.path, ExifTag.FLASH)
	
	@property
	def focal_length(self) -> float:
		"""
		Get the focal length from the EXIF data of the given file.

		Returns:
			float: The focal length (as a float, not a ratio)

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> photo.focal_length
			'2.8'
		"""
		result = self.attr(self.path, ExifTag.FOCAL_LENGTH)
		# Round up, always
		return round(result, 2)
	
	@property
	def height(self) -> int:
		"""
		Get the height from the EXIF data of the given file.

		Returns:
			int: The height.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> photo.height
			4000
		"""
		return self.attr(self.path, ExifTag.HEIGHT)

	@property
	def iso(self) -> int:
		"""
		Get the ISO from the EXIF data of the given file.

		Returns:
			int: The ISO.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> photo.iso
			'100'
		"""
		return self.attr(self.path, ExifTag.ISO)
	
	@property
	def landscape(self) -> bool:
		"""
		Get the landscape status from the EXIF data of the given file.

		Returns:
			bool: True if landscape, False otherwise.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			True
		"""
		return self.orientation == 'Landscape'
	
	@property
	def portrait(self) -> bool:
		"""
		Get the portrait status from the EXIF data of the given file.

		Returns:
			bool: True if portrait, False otherwise.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			False
		"""
		return self.orientation == 'Portrait'

	@property
	def lens(self) -> str:
		"""
		Get the lens from the EXIF data of the given file.

		Returns:
			str: The lens.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> photo.lens
			'FE 35mm F1.8'
		"""
		return self.attr(self.path, ExifTag.LENS)
	
	@property
	def metering_mode(self) -> str:
		"""
		Get the metering mode from the EXIF data of the given file.

		Returns:
			str: The metering mode.
		"""
		return self.attr(self.path, ExifTag.METERING_MODE)
	
	@property
	def megapixels(self) -> float:
		"""
		Get the megapixels from the EXIF data of the given file.

		Returns:
			float: The megapixels.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> photo.megapixels
			'24.2'
		"""
		return self.attr(self.path, ExifTag.MEGAPIXELS)
	
	@property
	def orientation(self) -> str:
		"""
		Get the orientation from the EXIF data of the given file.

		Returns:
			str: The orientation.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
		"""
		return self.attr(self.path, ExifTag.ORIENTATION)

	@property
	def ss(self) -> float:
		"""
		Get the shutter speed from the EXIF data of the given file.

		Returns:
			float: The shutter speed (as a float, not a ratio)

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> photo.shutter_speed
			'0.0125'
		"""
		result = self.attr(self.path, ExifTag.SS)
		# Round up the 10th decimal place, always
		return round(result, 10)

	@property
	def size(self) -> int:
		"""
		Get the size from the EXIF data of the given file.

		Returns:
			int: The size.
		"""
		return self.attr(self.path, ExifTag.SIZE)
	
	@property
	def temperature(self) -> str:
		"""
		Get the temperature from the EXIF data of the given file.

		Returns:
			str: The temperature.
		"""
		return self.attr(self.path, ExifTag.TEMPERATURE)
	
	@property
	def wb(self) -> str:
		"""
		Get the white balance from the EXIF data of the given file.

		Returns:
			str: The white balance.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
		"""
		return self.attr(self.path, ExifTag.WB)
	
	@property
	def wb_mode(self) -> str:
		"""
		Get the white balance mode from the EXIF data of the given file.

		Returns:
			str: The white balance mode.
		"""
		return self.attr(self.path, ExifTag.WB_MODE)
	
	@property
	def width(self) -> int:
		"""
		Get the width from the EXIF data of the given file.

		Returns:
			int: The width.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> photo.width
			6000
		"""
		return self.attr(self.path, ExifTag.WIDTH)
	
	def resolution(self) -> str:
		"""
		Get the resolution from the EXIF data of the given file.

		Returns:
			str: The resolution.
		"""
		return self.attr(self.path, ExifTag.RESOLUTION)
	
	@property
	def number(self) -> str:
		"""
		Get the filename number suffix from the given file. The number suffix is any number of digits at the end of the filename.

		Returns:
			str: The filename number suffix.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/JAM_1234.arw')
			>>> photo.number_suffix
			'1234'
		"""
		matches = re.search(r'(\d+)(\.[a-zA-Z]{1,5})?$', self.path)
		if matches is None:
			return None
		return int(matches.group(1))
	
	@property
	def extension(self) -> str:
		"""
		Get the file extension from the given file.

		Returns:
			str: The file extension.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/JAM_1234.arw')
			>>> photo.extension
			'arw'
		"""
		# If there is no decimal, then there is no extension
		if '.' not in self.path:
			return ""

		return self.path.lower().split('.')[-1]
	
	def attr(self, key : ExifTag) -> str | float | int:
		"""
		Get the EXIF data from the given file.

		Args:
			key (str): The key to get the EXIF data for.

		Returns:
			str | float | int: The EXIF data.

		Examples:
			>>> get_exif_data(ExifTag.EXPOSURE_TIME)
			{'EXIF ExposureTime': (1, 100)}
		"""
		with open(self.path, 'rb') as image_file:
			tags = exifread.process_file(image_file, details=False)

		# Convert from ASCII and Signed Ratio to string and float
		# address problems such as "AssertionError: (0x0110) ASCII=ILCE-7RM4 @ 340 != 'ILCE-7MR4'"
		value = tags[key]
		if isinstance(value, exifread.utils.Ratio):
			return value.decimal()
		if isinstance(value, exifread.classes.IfdTag):
			# If field type is an int, return an int
			if value.field_type in [3, 4, 8, 9]:
				return int(value.values[0])
			# If field type is a float, return a float
			if value.field_type in [11, 12]:
				return float(value.values[0])
			# If field type is a ratio or signed ratio, perform the division and reeturn a float
			if value.field_type in [5, 10]:
				return value.values[0].num / value.values[0].den
			return value.printable
		if isinstance(value, bytes):
			return value.decode('utf-8')
		if value is None:
			return None
    
		return exifread.utils.make_string(value)
	
	def is_jpg(self) -> bool:
		"""
		Checks if the given file is a JPG.

		Returns:
			bool: True if the file is a JPG, False otherwise.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.jpg')
			>>> photo.is_jpg()
			True
		"""
		return self.extension == 'jpg' or self.extension == 'jpeg'
	
	def exists(self) -> bool:
		"""
		Checks if the given file exists.

		Returns:
			bool: True if the file exists, False otherwise.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> photo.exists()
			True
		"""
		return os.path.exists(self.path)
	
	def matches(self, photo : Photo) -> bool:
		"""
		Compares the given photo to this photo.

		Args:
			photo (Photo): The photo to compare to.

		Returns:
			bool: True if the photo checksums are equal, False otherwise.

		Examples:
			>>> photo1 = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> photo2 = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> photo1.compare(photo2)
			True
		"""
		# Both must exist
		if not self.exists() or not photo.exists():
			return False
		
		return Validator.compare_checksums(self.path, photo.path)
	
	def __str__(self):
		return self.path