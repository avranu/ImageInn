"""

	Metadata:

		File: exif.py
		Project: imageinn
		Created Date: 17 Aug 2023
		Author: Jess Mann
		Email: jess.a.mann@gmail.com

		-----

		Last Modified: Wed Aug 23 2023
		Modified By: Jess Mann

		-----

		Copyright (c) 2023 Jess Mann
"""
from __future__ import annotations
from enum import Enum

class ExifTag(str, Enum):
	"""
	Enum of EXIF tags.
	"""
	A = 'EXIF MaxApertureValue'
	APERTURE = 'EXIF MaxApertureValue'
	B = 'EXIF BrightnessValue'
	BRIGHTNESS = 'EXIF BrightnessValue'
	CAMERA = 'Image Model'
	DATE = 'EXIF DateTimeOriginal'
	DIMENSIONS = 'Image ImageDimensions'
	EXPOSURE_BIAS = 'EXIF ExposureBiasValue'
	EXPOSURE_MODE = 'EXIF ExposureMode'
	EXPOSURE_PROGRAM = 'EXIF ExposureProgram'
	EXPOSURE_TIME = 'EXIF ExposureTime'
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
	SS = 'EXIF ExposureTime'
	SHUTTER_SPEED = 'EXIF ExposureTime'
	SIZE = 'Image Size'
	TEMPERATURE = 'EXIF WhiteBalanceTemperature'
	WB = 'EXIF WhiteBalance'
	WHITE_BALANCE = 'EXIF WhiteBalance'
	WB_MODE = 'EXIF WhiteBalanceMode'
	WIDTH = 'Image ImageWidth'
	RESOLUTION = 'Image XResolution'


"""
Tags appear to be as follows:

{
	'Image SubfileType': (0x00FE) Long=Reduced-resolution image @ 18'
	'Image Compression': (0x0103) Short=JPEG (old-style) @ 30'
	'Image ImageDescription': (0x010E) ASCII=                                @ 302'
	'Image Make': (0x010F) ASCII=SONY @ 334'
	'Image Model': (0x0110) ASCII=ILCE-7RM4 @ 340'
	'Image Orientation': (0x0112) Short=Horizontal (normal) @ 78'
	'Image XResolution': (0x011A) Ratio=350 @ 350'
	'Image YResolution': (0x011B) Ratio=350 @ 358'
	'Image ResolutionUnit': (0x0128) Short=Pixels/Inch @ 114'
	'Image Software': (0x0131) ASCII=ILCE-7RM4 v1.20 @ 366'
	'Image DateTime': (0x0132) ASCII=2023:08:05 19:27:27 @ 382'
	'Image Artist': (0x013B) ASCII=jess mann @ 402'
	'Image WhitePoint': (0x013E) Ratio=[313/1000, 329/1000] @ 412'
	'Image PrimaryChromaticities': (0x013F) Ratio=[16/25, 33/100, 21/100, 71/100, 3/20, 3/50] @ 428'
	'Image SubIFDs': (0x014A) Long=132338 @ 186'
	'Image JPEGInterchangeFormat': (0x0201) Long=135330 @ 198'
	'Image JPEGInterchangeFormatLength': (0x0202) Long=565586 @ 210'
	'Image YCbCrCoefficients': (0x0211) Ratio=[299/1000, 587/1000, 57/500] @ 476'
	'Image YCbCrPositioning': (0x0213) Short=Co-sited @ 234'
	'Image Copyright': (0x8298) ASCII=jess mann @ 4596'
	'Image ExifOffset': (0x8769) Long=4712 @ 270'
	'Image PrintIM': (0xC4A5) Undefined=[80, 114, 105, 110, 116, 73, 77, 0, 48, 51, 48, 48, 0, 0, 3, 0, 2, 0, 1, 0, ... ] @ 4606'
	'Image Tag 0xC634': (0xC634) Byte=[48, 205, 0, 0] @ 294'
	'Thumbnail SubfileType': (0x00FE) Long=Reduced-resolution image @ 43192'
	'Thumbnail Compression': (0x0103) Short=JPEG (old-style) @ 43204'
	'Thumbnail ImageDescription': (0x010E) ASCII=                                @ 43380'
	'Thumbnail Make': (0x010F) ASCII=SONY @ 43412'
	'Thumbnail Model': (0x0110) ASCII=ILCE-7RM4 @ 43418'
	'Thumbnail Orientation': (0x0112) Short=Horizontal (normal) @ 43252'
	'Thumbnail XResolution': (0x011A) Ratio=72 @ 43428'
	'Thumbnail YResolution': (0x011B) Ratio=72 @ 43436'
	'Thumbnail ResolutionUnit': (0x0128) Short=Pixels/Inch @ 43288'
	'Thumbnail Software': (0x0131) ASCII=ILCE-7RM4 v1.20 @ 43444'
	'Thumbnail DateTime': (0x0132) ASCII=2023:08:05 19:27:27 @ 43460'
	'Thumbnail Artist': (0x013B) ASCII=jess mann @ 43480'
	'Thumbnail JPEGInterchangeFormat': (0x0201) Long=43500 @ 43336'
	'Thumbnail JPEGInterchangeFormatLength': (0x0202) Long=7773 @ 43348'
	'Thumbnail YCbCrPositioning': (0x0213) Short=Co-sited @ 43360'
	'Thumbnail Copyright': (0x8298) ASCII=jess mann @ 43490'
	'EXIF ExposureTime': (0x829A) Ratio=1/13 @ 5234'
	'EXIF FNumber': (0x829D) Ratio=2 @ 5242'
	'EXIF ExposureProgram': (0x8822) Short=Aperture Priority @ 4746'
	'EXIF ISOSpeedRatings': (0x8827) Short=320 @ 4758'
	'EXIF SensitivityType': (0x8830) Short=Recommended Exposure Index @ 4770'
	'EXIF RecommendedExposureIndex': (0x8832) Long=320 @ 4782'
	'EXIF ExifVersion': (0x9000) Undefined=0231 @ 4794'
	'EXIF DateTimeOriginal': (0x9003) ASCII=2023:08:05 19:27:27 @ 5250'
	'EXIF DateTimeDigitized': (0x9004) ASCII=2023:08:05 19:27:27 @ 5270'
	'EXIF OffsetTime': (0x9010) ASCII=-05:00 @ 5290'
	'EXIF OffsetTimeOriginal': (0x9011) ASCII=-05:00 @ 5298'
	'EXIF OffsetTimeDigitized': (0x9012) ASCII=-05:00 @ 5306'
	'EXIF ComponentsConfiguration': (0x9101) Undefined=YCbCr @ 4866'
	'EXIF CompressedBitsPerPixel': (0x9102) Ratio=1 @ 5314'
	'EXIF BrightnessValue': (0x9203) Signed Ratio=-143/80 @ 5322'
	'EXIF ExposureBiasValue': (0x9204) Signed Ratio=1 @ 5330'
	'EXIF MaxApertureValue': (0x9205) Ratio=2 @ 5338'
	'EXIF MeteringMode': (0x9207) Short=Pattern @ 4926'
	'EXIF LightSource': (0x9208) Short=Unknown @ 4938'
	'EXIF Flash': (0x9209) Short=Flash did not fire, compulsory flash mode @ 4950'
	'EXIF FocalLength': (0x920A) Ratio=12 @ 5346'
	'EXIF FlashPixVersion': (0xA000) Undefined=0100 @ 4998'
	'EXIF ColorSpace': (0xA001) Short=Uncalibrated @ 5010'
	'EXIF ExifImageWidth': (0xA002) Long=9504 @ 5022'
	'EXIF ExifImageLength': (0xA003) Long=6336 @ 5034'
	'Interoperability InteroperabilityIndex': (0x0001) ASCII=R03 @ 43162'
	'Interoperability InteroperabilityVersion': (0x0002) Undefined=[48, 49, 48, 48] @ 43174'
	'EXIF InteroperabilityOffset': (0xA005) Long=43152 @ 5046'
	'EXIF FileSource': (0xA300) Undefined=Digital Camera @ 5058'
	'EXIF SceneType': (0xA301) Undefined=Directly Photographed @ 5070'
	'EXIF CustomRendered': (0xA401) Short=Normal @ 5082'
	'EXIF ExposureMode': (0xA402) Short=Auto Bracket @ 5094'
	'EXIF WhiteBalance': (0xA403) Short=Auto @ 5106'
	'EXIF DigitalZoomRatio': (0xA404) Ratio=1 @ 43072'
	'EXIF FocalLengthIn35mmFilm': (0xA405) Short=12 @ 5130'
	'EXIF SceneCaptureType': (0xA406) Short=Standard @ 5142'
	'EXIF Contrast': (0xA408) Short=Normal @ 5154'
	'EXIF Saturation': (0xA409) Short=Normal @ 5166'
	'EXIF Sharpness': (0xA40A) Short=Normal @ 5178'
	'EXIF BodySerialNumber': (0xA431) ASCII=03385579 @ 43080'
	'EXIF LensSpecification': (0xA432) Ratio=[12, 12, 2, 2] @ 43090'
	'EXIF LensModel': (0xA434) ASCII=SAMYANG AF 12mm F2.0 @ 43122'
	'EXIF Gamma': (0xA500) Ratio=11/5 @ 43144
}
"""