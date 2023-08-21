"""

	Metadata:

		File: photo.py
		Project: import_sd
		Created Date: 11 Aug 2023
		Author: Jess Mann
		Email: jess.a.mann@gmail.com

		-----

		Last Modified: Mon Aug 21 2023
		Modified By: Jess Mann

		-----

		Copyright (c) 2023 Jess Mann
"""
from __future__ import annotations
import datetime
from enum import Enum
import errno
import math
import math
import os
import re
import logging
from decimal import Decimal
from typing import Any, Dict, Optional, TypedDict
import exifread, exifread.utils, exifread.tags.exif, exifread.classes
from .exif import ExifTag
from .validator import Validator
from .path import FilePath

logger = logging.getLogger(__name__)

class Photo(FilePath):
	"""
	Allows us to interact with sd cards mounted to the server this code is running on.
	"""
	_path : str
	_number : int

	def __init__(self, path : list[str] | str, number : Optional[int] = None):
		"""
		Initialise the photo object.

		Args:
			path (str): The path to the photo.
			number (int, optional): The number of the photo. Defaults to None.
		"""
		super().__init__(path)
		self._number = number

	@property
	def path(self) -> str:
		"""
		The path to the photo.
		"""
		return self._path

	@path.setter
	def path(self, value : list[str] | str):
		"""
		The path to the photo, which must already exist.
		"""
		if isinstance(value, str):
			# Cast to string to convert FilePath() to string
			joined_path = str(value)
		else:
			joined_path = os.path.join(*value)

		self._path = os.path.normpath(joined_path)

		self.validate()

	def validate(self) -> bool:
		"""
		Whether the photo is valid or not.

		This MUST return True. If the path is not valid, it will raise an exception to indicate why.

		Returns:
			bool: True if the photo is valid. Raises exception otherwise.

		Raises:
			FileNotFoundError: If the path does not exist.
			ValueError: If the path is not a file.
		"""
		if not isinstance(self.path, str):
			logger.info('Path is not a string: %s. It is %s', self.path, type(self.path).__name__)
			raise TypeError('Path must be a string. It is currently a %s' % type(self.path).__name__)
		
		if not os.path.exists(self.path):
			logger.info('Path does not exist: %s', self.path)
			raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), self.path)

		if not os.path.isfile(self.path):
			logger.info('Path is not a file: %s', self.path)
			raise ValueError('Path must be a file')

		return True

	@property
	def aperture(self) -> Decimal | None:
		"""
		Get the aperture from the EXIF data of the given file.

		Returns:
			Decimal: The aperture (as a Decimal, not a ratio)

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> photo.aperture
			'2.8'
		"""
		result = self.attr(ExifTag.APERTURE)
		if not result:
			return None
		# Round up, always
		return round(result, 2)

	@property
	def brightness(self) -> Decimal | None:
		"""
		Get the brightness value from the EXIF data of the given file.

		Returns:
			str: The brightness value.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> photo.brightness
			'-8.27'
		"""
		result = self.attr(ExifTag.BRIGHTNESS)
		if not result:
			return None

		# Round up the 2nd decimal place. Always round up, never down.
		return round(result, 2)

	@property
	def b(self) -> Decimal | None:
		return self.brightness

	@property
	def camera(self) -> str | None:
		"""
		Get the camera model from the EXIF data of the given file.

		Returns:
			str: The camera model.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> photo.camera
			'a7r4'
		"""
		return self.attr(ExifTag.CAMERA)

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
		value = self.attr(ExifTag.DATE)
		if not value:
			return None
		return datetime.datetime.strptime(value, '%Y:%m:%d %H:%M:%S')

	@property
	def dimensions(self) -> Dict[str, int] | None:
		"""
		Get the dimensions from the EXIF data of the given file.

		Returns:
			dict: The dimensions.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> photo.dimensions
			{'height': 4000, 'width': 6000}
		"""
		value = self.attr(ExifTag.DIMENSIONS)
		if not value:
			return None
		return {
			'height': value[0],
			'width': value[1]
		}

	@property
	def exposure_bias(self) -> Decimal | None:
		"""
		Get the exposure bias from the EXIF data of the given file.

		Returns:
			str: The exposure bias.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> photo.exposure_bias
			'-2 7'
		"""
		result = self.attr(ExifTag.EXPOSURE_BIAS)
		if not result:
			return None

		# Round up the 2nd decimal place, always
		return round(result, 2)

	@property
	def eb(self) -> Decimal | None:
		return self.exposure_bias

	@property
	def exposure_value(self) -> Decimal | None:
		"""
		Calculate the exposure value using EXIF data from the photo

		Returns:
			Decimal: The exposure value.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> photo.exposure_value
			'-8.27'
		"""
		aperture = self.aperture
		shutter_speed = self.ss
		iso = self.iso
		if not aperture or not shutter_speed or not iso:
			return None

		result = math.log2((aperture ** 2) / shutter_speed * iso)
		result = Decimal(result)
		return round(result, 2)

	@property
	def ev(self) -> Decimal | None:
		return self.exposure_value

	@property
	def exposure_mode(self) -> str | None:
		"""
		Get the exposure mode from the EXIF data of the given file.

		Returns:
			str: The exposure mode.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')

		"""
		return self.attr(ExifTag.EXPOSURE_MODE)

	@property
	def exposure_program(self) -> str | None:
		"""
		Get the exposure program from the EXIF data of the given file.

		Returns:
			str: The exposure program.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')

		"""
		return self.attr(ExifTag.EXPOSURE_PROGRAM)

	@property
	def exposure_time(self) -> Decimal | None:
		"""
		Get the exposure time from the EXIF data of the given file.

		Returns:
			Decimal: The exposure time (as a Decimal, not a ratio)

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> photo.exposure_time
			'0.0125'
		"""
		result = self.attr(ExifTag.EXPOSURE_TIME)
		if not result:
			return None
		# Round up the 10th decimal place, always
		return round(result, 10)

	@property
	def f(self) -> Decimal | None:
		"""
		Get the f-number from the EXIF data of the given file.

		Returns:
			Decimal: The f-number (as a Decimal, not a ratio)

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> photo.f_number
			'2.8'
		"""
		result = self.attr(ExifTag.F)
		if not result:
			return None
		# Round up, always
		return round(result, 2)

	@property
	def flash(self) -> bool | None:
		"""
		Get the flash status from the EXIF data of the given file.

		Returns:
			bool: True if flash was used, False otherwise.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			True
		"""
		return self.attr(ExifTag.FLASH)

	@property
	def focal_length(self) -> Decimal | None:
		"""
		Get the focal length from the EXIF data of the given file.

		Returns:
			Decimal: The focal length (as a Decimal, not a ratio)

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> photo.focal_length
			'2.8'
		"""
		result = self.attr(ExifTag.FOCAL_LENGTH)
		if not result:
			return None
		# Round up, always
		return round(result, 2)

	@property
	def height(self) -> int | None:
		"""
		Get the height from the EXIF data of the given file.

		Returns:
			int: The height.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> photo.height
			4000
		"""
		return self.attr(ExifTag.HEIGHT)

	@property
	def iso(self) -> int | None:
		"""
		Get the ISO from the EXIF data of the given file.

		Returns:
			int: The ISO.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> photo.iso
			'100'
		"""
		return self.attr(ExifTag.ISO)

	@property
	def landscape(self) -> bool | None:
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
	def portrait(self) -> bool | None:
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
	def lens(self) -> str | None:
		"""
		Get the lens from the EXIF data of the given file.

		Returns:
			str: The lens.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> photo.lens
			'FE 35mm F1.8'
		"""
		return self.attr(ExifTag.LENS)

	@property
	def metering_mode(self) -> str | None:
		"""
		Get the metering mode from the EXIF data of the given file.

		Returns:
			str: The metering mode.
		"""
		return self.attr(ExifTag.METERING_MODE)

	@property
	def megapixels(self) -> Decimal | None:
		"""
		Get the megapixels from the EXIF data of the given file.

		Returns:
			Decimal: The megapixels.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> photo.megapixels
			'24.2'
		"""
		return self.attr(ExifTag.MEGAPIXELS)

	@property
	def orientation(self) -> str | None:
		"""
		Get the orientation from the EXIF data of the given file.

		Returns:
			str: The orientation.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
		"""
		return self.attr(ExifTag.ORIENTATION)

	@property
	def ss(self) -> Decimal | None:
		"""
		Get the shutter speed from the EXIF data of the given file.

		Returns:
			Decimal: The shutter speed (as a Decimal, not a ratio)

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> photo.shutter_speed
			'0.0125'
		"""
		result = self.attr(ExifTag.SS)

		if not result:
			return None

		# Round up the 4th decimal place, always
		return round(result, 4)

	@property
	def size(self) -> int | None:
		"""
		Get the size from the EXIF data of the given file.

		Returns:
			int: The size.
		"""
		return self.attr(ExifTag.SIZE)

	@property
	def temperature(self) -> str | None:
		"""
		Get the temperature from the EXIF data of the given file.

		Returns:
			str: The temperature.
		"""
		return self.attr(ExifTag.TEMPERATURE)

	@property
	def wb(self) -> str | None:
		"""
		Get the white balance from the EXIF data of the given file.

		Returns:
			str: The white balance.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
		"""
		return self.attr(ExifTag.WB)

	@property
	def wb_mode(self) -> str | None:
		"""
		Get the white balance mode from the EXIF data of the given file.

		Returns:
			str: The white balance mode.
		"""
		return self.attr(ExifTag.WB_MODE)

	@property
	def width(self) -> int | None:
		"""
		Get the width from the EXIF data of the given file.

		Returns:
			int: The width.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/IMG_1234.arw')
			>>> photo.width
			6000
		"""
		return self.attr(ExifTag.WIDTH)

	@property
	def resolution(self) -> str | None:
		"""
		Get the resolution from the EXIF data of the given file.

		Returns:
			str: The resolution.
		"""
		return self.attr(ExifTag.RESOLUTION)

	@property
	def number(self) -> int:
		"""
		Get the photo number. If it is not set manually, it will be the filename number suffix.

		The number suffix is any number of digits at the end of the filename.

		Returns:
			str: The filename number suffix.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/JAM_1234_1.arw', number='5678')
			>>> photo.number
			5678
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/JAM_1234.arw')
			>>> photo.number
			1234
		"""
		if self._number:
			return self._number

		# Start with the standard RAW format from a DSLR
		matches = re.search(r'^_?[a-z0-9]+_(\d+)(\.[a-zA-Z]{1,5})?$', os.path.basename(self.path), re.IGNORECASE)
		if not matches:
			# Try our custom format
			matches = re.search(r'^\d{8}_[a-z0-9-]+_(\d+)', os.path.basename(self.path), re.IGNORECASE)
			if not matches:
				return None

		return int(matches.group(1))

	@number.setter
	def number(self, value: int):
		"""
		Set the photo number.

		Args:
			value (int): The photo number.
		"""
		self._number = value

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

	@property
	def checksum(self) -> str:
		"""
		Get the checksum of this file.

		Returns:
			str: The checksum.

		Examples:
			>>> photo = Photo('/media/pi/SD_CARD/DCIM/100MSDCF/JAM_1234.arw')
			>>> photo.checksum
			'8f3d1d8a'
		"""
		return Validator.calculate_checksum(self.path)

	def attr(self, key : ExifTag) -> str | Decimal | int | None:
		"""
		Get the EXIF data from the given file.

		Args:
			key (str): The key to get the EXIF data for.

		Returns:
			str | Decimal | int: The EXIF data.

		Examples:
			>>> get_exif_data(ExifTag.EXPOSURE_TIME)
			{'EXIF ExposureTime': (1, 100)}
		"""
		try:
			with open(self.path, 'rb') as image_file:
				tags = exifread.process_file(image_file, details=False)

			# Convert from ASCII and Signed Ratio to string and Decimal
			# address problems such as "AssertionError: (0x0110) ASCII=ILCE-7RM4 @ 340 != 'ILCE-7MR4'"
			value = tags[key]
			if isinstance(value, exifread.utils.Ratio):
				return Decimal(value.decimal())
			if isinstance(value, exifread.classes.IfdTag):
				# If field type is an int, return an int
				if value.field_type in [3, 4, 8, 9]:
					return int(value.values[0])
				# If field type is a Decimal, return a Decimal
				if value.field_type in [11, 12]:
					return Decimal(value.values[0])
				# If field type is a ratio or signed ratio, perform the division and reeturn a Decimal
				if value.field_type in [5, 10]:
					return Decimal(value.values[0].num) / Decimal(value.values[0].den)
				return value.printable
			if isinstance(value, bytes):
				result = value.decode('utf-8')
				if isinstance(result, float):
					return Decimal(result)
				return result

			if value is None:
				return None

			return exifread.utils.make_string(value)
		except KeyError:
			logger.warning('Unable to find attribute %s in %s', key, self.path)
			logger.warning('Tags are %s', tags)
			return None

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

	def __str__(self):
		return self.path


class FakePhoto(Photo):
	"""
	This is used to mock a photo for testing purposes and dry runs.
	"""

	@property
	def path(self) -> str:
		"""
		The path to the photo.
		"""
		return self._path

	@path.setter
	def path(self, value: str):
		"""
		The path to the photo, which NORMALLY must already exist. For a fake photo, it does not need to exist.
		"""
		self._path = os.path.normpath(value)

	@property
	def ss(self) -> Decimal:
		"""
		The FAKE shutter speed of the photo.
		"""
		return Decimal(0.01)

	@property
	def iso(self) -> int:
		"""
		The FAKE ISO of the photo.
		"""
		return 100

	@property
	def aperture(self) -> Decimal:
		"""
		The FAKE aperture of the photo.
		"""
		return Decimal(2.8)

	@property
	def date(self) -> datetime:
		"""
		The FAKE date of the photo.
		"""
		return datetime.datetime.now()

	@property
	def exposure_bias(self) -> Decimal:
		"""
		The FAKE exposure bias of the photo.
		"""
		return Decimal(0)

	@property
	def focal_length(self) -> Decimal:
		"""
		The FAKE focal length of the photo.
		"""
		return 35

	@property
	def wb(self) -> str:
		"""
		The FAKE white balance of the photo.
		"""
		return 'Auto'

	@property
	def lens(self) -> str:
		"""
		The FAKE lens of the photo.
		"""
		return 'FE 35mm F1.8'

	@property
	def camera(self) -> str:
		"""
		The FAKE camera model of the photo.
		"""
		return 'ILCE-7RM4'

	@property
	def brightness(self) -> Decimal:
		"""
		The FAKE brightness of the photo.
		"""
		return Decimal(0)

	@property
	def exposure_time(self) -> Decimal:
		"""
		The FAKE exposure time of the photo.
		"""
		return Decimal(0.5)

	@property
	def f(self) -> Decimal:
		"""
		The FAKE f-stop of the photo.
		"""
		return Decimal(2.8)

	def attr(self, key : ExifTag) -> str:
		"""
		Get fake EXIF data.

		Args:
			key (str): The key to get the EXIF data for.

		Returns:
			str | Decimal | int: The EXIF data.

		Examples:
			>>> get_exif_data(ExifTag.EXPOSURE_TIME)
			{'EXIF ExposureTime': (1, 100)}
		"""
		return 'fake'

