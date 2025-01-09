"""*********************************************************************************************************************
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    METADATA:                                                                                                         *
*                                                                                                                      *
*        File:    fix_created.py                                                                                       *
*        Project: imageinn                                                                                             *
*        Version: 1.0.0                                                                                                *
*        Created: 2024-04-30                                                                                           *
*        Author:  Jess Mann                                                                                            *
*        Email:   jess.a.mann@gmail.com                                                                                *
*        Copyright (c) 2024 Jess Mann                                                                                  *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    LAST MODIFIED:                                                                                                    *
*                                                                                                                      *
*        2024-10-21     By Jess Mann                                                                                   *
*                                                                                                                      *
*********************************************************************************************************************"""
import argparse
import os
from datetime import datetime
import sys
import exifread


class TimestampUpdater:
	"""
	Update the created and modified timestamps of a series of photos.
	"""

	def change_timestamp(self, filename, new_year, new_month, new_day):
		self.change_system_timestamp(filename, new_year, new_month, new_day)
		# self.change_exif_timestamp(filename, new_year, new_month, new_day)

	def change_system_timestamp(self, filename, new_year, new_month, new_day):
		try:
			# Get the current modified and created timestamps
			modified_time = os.path.getmtime(filename)
			created_time = os.path.getctime(filename)

			# Convert to datetime objects
			modified_dt = datetime.fromtimestamp(modified_time)
			created_dt = datetime.fromtimestamp(created_time)

			# Create new datetime objects with the desired year, month, and day
			new_modified_dt = modified_dt.replace(year=new_year, month=new_month, day=new_day)
			new_created_dt = created_dt.replace(year=new_year, month=new_month, day=new_day)

			# Convert back to timestamps
			new_modified_time = new_modified_dt.timestamp()
			new_created_time = new_created_dt.timestamp()

			# Update the file timestamps
			os.utime(filename, (new_created_time, new_modified_time))

			print(f"System timestamps updated for file: {filename}")
		except Exception as e:
			print(f"An error occurred while processing {filename}: {str(e)}")

	def change_exif_timestamp(self, filename, new_year, new_month, new_day):
		"""
		Change the EXIF data of the file to the new date. Notably, the "photo taken" date.

		This can be used on any photo, including raw photos, such as those with an "arw" extension.

		NOTE: This approach below does not work on raw photos. See here:
		https://stackoverflow.com/questions/64514225/add-date-taken-exif-xmp-information-to-tif-file-using-python
		"""
		raise NotImplementedError("This method is not yet implemented for raw photos.")
		"""
		# Load the EXIF data from the image file
		exif_data = piexif.load(filename)

		# Remove the thumbnail information if it exists
		if "thumbnail" in exif_data:
			del exif_data["thumbnail"]
			del exif_data["1st"]

		# Get the EXIF tag for the "photo taken" date
		if piexif.ExifIFD.DateTimeOriginal in exif_data["Exif"]:
			# Get the current photo taken date
			photo_taken = exif_data["Exif"][piexif.ExifIFD.DateTimeOriginal].decode("utf-8")

			# Convert to a datetime object
			photo_taken_dt = datetime.strptime(photo_taken, "%Y:%m:%d %H:%M:%S")

			# Create a new datetime object with the desired year, month, and day
			new_photo_taken_dt = photo_taken_dt.replace(year=new_year, month=new_month, day=new_day)

			# Convert back to a string
			new_photo_taken = new_photo_taken_dt.strftime("%Y:%m:%d %H:%M:%S")

			# Update the EXIF data with the new date
			exif_data["Exif"][piexif.ExifIFD.DateTimeOriginal] = new_photo_taken.encode("utf-8")

			# Save the exif data
			exif_bytes = piexif.dump(exif_data)
			piexif.insert(exif_bytes, filename)

			print(f"EXIF data updated for file: {filename}")
		else:
			print(f"EXIF data not found for file: {filename}")
		"""

	def get_exif_from_raw(self, filename: str) -> dict[str, str]:
		"""
		Get all exif attributes from a raw photo.

		Args:
			filename (str): The filename of the raw photo.

		Returns:
			dict: A dictionary of all exif attributes and their values.

		Examples:
			>>> get_exif_from_raw('test.arw')
			{'Image Make': 'SONY', 'Image Model': 'ILCE-7RM3', 'Image Orientation': 'Horizontal (normal)', 'Image XResolution': '350', 'Image YResolution': '350', 'Image ResolutionUnit': 'Pixels/Inch', 'Image Software': 'ILCE-7RM3 v1.10', 'Image DateTime': '2020:01:01 00:00:00', 'Image Artist': 'Unknown', 'Image Copyright': '', 'Image ExifOffset': '240'}
		"""
		try:
			# Open the raw file
			with open(filename, 'rb') as f:
				exif = exifread.process_file(f)
				return exif
		except Exception as e:
			print(f"An error occurred while processing {filename}: {str(e)}")

		return {}

def main():
	# Get a path using argparse
	parser = argparse.ArgumentParser(description="Change the created and modified timestamps of all files in a directory.")
	parser.add_argument("path", help="The path to the directory containing the files to be processed.")
	parser.add_argument('date', help='The date to set the timestamps to in the format YYYY-MM-DD')
	args = parser.parse_args()

	path = args.path
	date = args.date

	if not os.path.isdir(path):
		print("The path provided is not a valid directory.")
		sys.exit(1)

	# Parse the date into year/month/day
	try:
		new_year, new_month, new_day = date.split('-')
		new_year = int(new_year)
		new_month = int(new_month)
		new_day = int(new_day)
	except Exception as e:
		print(f"An error occurred while parsing the date: {str(e)}")
		sys.exit(1)

	files = []
	for f in os.listdir(path):
		try:
			fpath = os.path.join(path, f)
			if os.path.isfile(fpath):
				files.append(fpath)
		except OSError:
			continue

	# Iterate through files and update the timestamps
	updater = TimestampUpdater()
	for filename in files:
		updater.change_timestamp(filename, new_year, new_month, new_day)

	# Get the new exif data and print it
	print("New EXIF data:")
	for filename in files:
		print(filename)
		exif = updater.get_exif_from_raw(filename)
		# Print each key->value on a new line
		for key, value in exif.items():
			# Ignore JPEGThumbnail
			if key == 'JPEGThumbnail':
				continue
			print(f"{key}: {value}")
		print('')

	print("Operation completed.")


if __name__ == "__main__":
	try:
		main()
	except KeyboardInterrupt:
		print("Operation cancelled.")
