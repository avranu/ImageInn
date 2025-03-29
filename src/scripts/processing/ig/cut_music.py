"""*********************************************************************************************************************
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    METADATA:                                                                                                         *
*                                                                                                                      *
*        File:    cut_music.py                                                                                         *
*        Project: imageinn                                                                                             *
*        Version: 0.1.0                                                                                                *
*        Created: 2025-03-16                                                                                           *
*        Author:  Jess Mann                                                                                            *
*        Email:   jess@jmann.me                                                                                        *
*        Copyright (c) 2025 Jess Mann                                                                                  *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    LAST MODIFIED:                                                                                                    *
*                                                                                                                      *
*        2025-03-16     By Jess Mann                                                                                   *
*                                                                                                                      *
*********************************************************************************************************************"""
import os
import argparse
import logging
from pathlib import Path
from pydub import AudioSegment

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class MP3Splitter:
    """Class to split an MP3 file into 15-second segments."""
    
    def __init__(self, input_file: Path, output_dir: Path | None = None, segment_length: int = 15000):
        """
        Initializes the MP3Splitter.

        Args:
            input_file (Path): Path to the input MP3 file.
            output_dir (Path): Directory to save the split MP3 files.
            segment_length (int): Length of each segment in milliseconds (default: 15 seconds).
        """
        self.input_file = input_file
        self.output_dir = output_dir or input_file.parent / "split"
        self.segment_length = segment_length

        if not self.output_dir.exists():
            self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_name(self, filepath : Path, part : int) -> str:
        """Generates a name for the split file."""
        stem = filepath.stem
        extension = filepath.suffix
        
        # Find the first "-", and add {part} before it
        index = stem.find("-")
        if index < 1:
            return f"{stem} - {part}{extension}"
        return f"{stem[:index]} {part} - {stem[index+1:]}{extension}"
        
    def split(self) -> None:
        """Splits the MP3 file into multiple segments of specified duration."""
        try:
            # Load audio file
            audio = AudioSegment.from_mp3(self.input_file)
            duration = len(audio)
            num_segments = (duration // self.segment_length) + (1 if duration % self.segment_length else 0)

            self.output_dir.mkdir(parents=True, exist_ok=True)

            for i in range(num_segments):
                start_time = i * self.segment_length
                end_time = min((i + 1) * self.segment_length, duration)

                segment = audio[start_time:end_time]
                output_filename = self.generate_name(self.input_file, i+1)
                output_path = self.output_dir / output_filename

                segment.export(output_path, format="mp3")
                logger.info(f"Exported: {output_path}")

            logger.info("Splitting complete.")

        except Exception as e:
            logger.error(f"Error processing file: {e}", exc_info=True)

def split_directory(input_dir: Path, output_dir: Path | None = None) -> None:
    """Splits all MP3 files in the specified directory."""
    if output_dir is None:
        output_dir = input_dir / "split"

    for file in input_dir.glob("*.mp3"):
        logger.info(f"Processing file: {file}")
        splitter = MP3Splitter(file, output_dir)
        splitter.split()


def main():
    parser = argparse.ArgumentParser(description="Split an MP3 file into 15-second segments.")
    parser.add_argument("input_file", type=Path, help="Path to the input MP3 file.")
    parser.add_argument("--output_dir", "-o", type=Path, help="Directory to save split files.")
    
    args = parser.parse_args()

    input_dir = Path(args.input_file)
    if input_dir.is_dir():
        split_directory(input_dir, args.output_dir)
        return
    
    splitter = MP3Splitter(args.input_file, args.output_dir)
    splitter.split()

if __name__ == "__main__":
    main()
