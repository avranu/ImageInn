"""
	
	Metadata:
	
		File: exif.py
		Project: import_sd
		Created Date: 17 Aug 2023
		Author: Jess Mann
		Email: jess.a.mann@gmail.com
	
		-----
	
		Last Modified: Thu Aug 17 2023
		Modified By: Jess Mann
	
		-----
	
		Copyright (c) 2023 Jess Mann
"""
from __future__ import annotations
from enum import Enum

class ExifTag(str, Enum):
	A = 'EXIF ApertureValue'
	APERTURE = 'EXIF ApertureValue'
	B = 'EXIF BrightnessValue'
	BRIGHTNESS = 'EXIF BrightnessValue'
	CAMERA = 'Image Model'
	DATE = 'EXIF DateTimeOriginal'
	DIMENSIONS = 'Image ImageDimensions'
	EXPOSURE_BIAS = 'EXIF ExposureBiasValue'
	EXPOSURE_MODE = 'EXIF ExposureMode'
	EXPOSURE_PROGRAM = 'EXIF ExposureProgram'
	EXPOSURE_TIME = 'EXIF ExposureTime'
	EXPOSURE_VALUE = 'EXIF ExposureValue'
	F = 'EXIF FNumber'
	F_NUMBER = 'EXIF FNumber'
	FLASH = 'EXIF Flash'
	FOCAL_LENGTH = 'EXIF FocalLength'
	HEIGHT = 'Image ImageLength'
	ISO = 'EXIF ISOSpeedRatings'
	LENS = 'EXIF LensModel'
	METERING_MODE = 'EXIF MeteringMode'
	MEGAPIXELS = 'EXIF PixelXDimension'
	MP = 'EXIF PixelXDimension'
	ORIENTATION = 'Image Orientation'
	SS = 'EXIF ShutterSpeedValue'
	SHUTTER_SPEED = 'EXIF ShutterSpeedValue'
	SIZE = 'Image Size'
	TEMPERATURE = 'EXIF WhiteBalanceTemperature'
	WB = 'EXIF WhiteBalance'
	WHITE_BALANCE = 'EXIF WhiteBalance'
	WB_MODE = 'EXIF WhiteBalanceMode'
	WIDTH = 'Image ImageWidth'
	RESOLUTION = 'Image XResolution'