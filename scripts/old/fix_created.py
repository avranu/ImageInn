import argparse
import os
from datetime import datetime

# Function to change the timestamp of a single file
def change_timestamp(filename, new_year, new_month, new_day):
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
        print(f"Timestamps updated for file: {filename}")
    except Exception as e:
        print(f"An error occurred while processing {filename}: {str(e)}")


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
        exit(1)

    # Parse the date into year/month/day
    try:
        new_year, new_month, new_day = date.split('-')
        new_year = int(new_year)
        new_month = int(new_month)
        new_day = int(new_day)
    except Exception as e:
        print(f"An error occurred while parsing the date: {str(e)}")
        exit(1)

    files = []
    for f in os.listdir(path):
        try:
            fpath = os.path.join(path, f)
            if os.path.isfile(fpath):
                files.append(fpath)
        except OSError as e:
            continue

    # Iterate through files and update the timestamps
    for filename in files:
        change_timestamp(filename, new_year, new_month, new_day)

    print("Operation completed.")

if __name__ == "__main__":
    main()