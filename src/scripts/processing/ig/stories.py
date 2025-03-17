"""*********************************************************************************************************************
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    METADATA:                                                                                                         *
*                                                                                                                      *
*        File:    stories.py                                                                                           *
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
from __future__ import annotations
import logging
import os
from pathlib import Path
import subprocess
from PIL import Image
import argparse
from tqdm import tqdm
import ffmpeg
import tempfile
import shutil
import uuid
import re
from pydantic import Field, field_validator
from decimal import Decimal
from scripts.processing.ig.processor import IGImageProcessor
from scripts.processing.ig.image import IGImage
from scripts.processing.meta import Formats

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class IGMusicStoryProcessor(IGImageProcessor):
    """
    Process images into Instagram stories with music.

    Args:
        input_dir (Path): Path to the directory containing images.
        music_file (Path): Path to the music file to use.
        duration (Decimal): Duration of the story in seconds.
        fade_in (Decimal): Fade in duration in seconds.
        fade_out (Decimal): Fade out duration in seconds.
        volume (Decimal): Audio volume level (0.0-1.0).
    """
    music_file: Path
    duration: Decimal = Field(default=15.0)
    fade_in: Decimal = Field(default=0.0)
    fade_out: Decimal = Field(default=0.0)
    volume: Decimal = Field(default=1.0)
    output_folder: str = Field(default="music_stories")

    def __init__(self, **data):
        # Always force story format for music stories
        data["format"] = Formats.STORY.value
        data["place_into_canvas"] = True
        super().__init__(**data)

    @field_validator("input_dir", mode="before")
    @classmethod
    def validate_input_dir(cls, v):
        if not v:
            return None
        path = Path(v)
        return cls._fix_input_path(path)

    @field_validator("music_file", mode="before")
    @classmethod
    def validate_music_file(cls, v):
        if not v:
            raise ValueError("Music file is required")

        path = Path(v)
        return cls._fix_music_path(path)

    @field_validator("duration", mode="before")
    def validate_duration(cls, v):
        if v <= 0:
            raise ValueError("Duration must be positive")
        return v

    @field_validator("volume", mode="before")
    def validate_volume(cls, v):
        if v < 0 or v > 1:
            raise ValueError("Volume must be between 0.0 and 1.0")
        return v

    @classmethod
    def _fix_input_path(cls, path: Path) -> Path:
        if path.exists():
            return path

        if not path.is_absolute():
            parent = os.getenv("IMAGEINN_STORY_DIR", None)
            if parent:
                path = Path(parent) / path

        if path.exists():
            return path
        raise FileNotFoundError(f"File not found: {path}")

    @classmethod
    def _fix_music_path(cls, path: Path) -> Path:
        if path.exists():
            return path

        if not path.is_absolute():
            parent = os.getenv("IMAGEINN_MUSIC_DIR", None)
            if parent:
                path = Path(parent) / path

        if path.exists():
            return path
        raise FileNotFoundError(f"File not found: {path}")

    def process_images(self) -> None:
        """
        Process all JPG images in the input directory.
        """
        count : int = 0
        error_count : int = 0
        
        images = self._get_images()
        total = len(images)
        logger.info('Found %s images in %s', total, self.input_dir)
        self.output_dir.mkdir(exist_ok=True)

        with tqdm(total=total, desc="Processing images") as self._progress_bar:
            for file_path in images:
                try:
                    self.process_image(file_path)
                    count += 1
                except Exception as e:
                    logger.error(f"Failed to process {file_path}: {e}")
                    error_count += 1
                    if error_count >= self.max_errors:
                        logger.error(f"Reached maximum error count ({self.max_errors}). Stopping.")
                        raise
                finally:
                    self.update_progress()

        logger.info("Processed %s images", count)

    def process_image(self, file_path: Path) -> None:
        """
        Process a single image into a music story.
        """
        self.update_progress(f"Processing image: {file_path.name}")

        base_name = re.sub(r"[^a-zA-Z0-9]", "_", file_path.stem)[:50]
        output_filename = f"{base_name}_story_music.mp4"
        final_output_path = self.output_dir / output_filename
        if final_output_path.exists():
            logger.info("Output file already exists: %s. Skipping", final_output_path)
            return

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            temp_image_path = temp_dir / "temp_image.jpg"
            temp_video_path = temp_dir / "temp_video.mp4"

            try:
                image = Image.open(file_path)
                image.save(temp_image_path)

                self.create_video_from_image(temp_image_path, temp_video_path)
                self.add_music_to_video(temp_video_path, self.music_file, final_output_path)

                if self.ig_output_dir:
                    self.copy_file(final_output_path, self.ig_output_dir / final_output_path.name, skip_existing=True)

            except Exception as e:
                logger.error(f"Error processing {file_path}: {e}")
                raise

    def create_video_from_image(self, image_path: Path, output_path: Path) -> None:
        """
        Create a video from a static image with the specified duration.
        """
        if output_path.exists():
            logger.error(f"Output file already exists: {output_path}. Not overwriting")
            return
        
        logger.debug("Creating video from image: %s -> %s", image_path, output_path)
        try:
            (
                ffmpeg
                .input(str(image_path), loop=1, t=float(self.duration))
                .output(str(output_path), vcodec="libx264", pix_fmt="yuv420p")
                .global_args("-loglevel", "error")
                .run()
            )
        except ffmpeg.Error as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            logger.error(f"Failed to create video: {error_msg}")
            raise RuntimeError(f"FFMPEG error creating video: {error_msg}")

    def add_music_to_video(self, video_path: Path, music_path: Path, output_path: Path) -> None:
        """
        Add music to a video with fade in/out effects.
        """
        try:
            # Logging details
            logger.debug('Adding music to video: %s + %s -> %s', video_path, music_path, output_path)
            logger.debug('Parameters: duration=%s, fade_in=%s, fade_out=%s, volume=%s', 
                        self.duration, self.fade_in, self.fade_out, self.volume)
            
            fade_out_start = float(self.duration) - float(self.fade_out)
            cmd = [
                "ffmpeg",
                "-i", str(video_path),
                "-i", str(music_path),
                "-c:v", "copy",
                "-af", f"afade=in:st=0:d={self.fade_in},afade=out:st={fade_out_start}:d={self.fade_out},volume={self.volume}",
                "-t", str(self.duration),
                "-shortest",
                "-y",
                str(output_path)
            ]
            
            # Add loglevel for debugging if verbose
            if logger.isEnabledFor(logging.DEBUG):
                cmd.extend(['-loglevel', 'info'])
            else:
                cmd.extend(['-loglevel', 'error'])
                
            logger.debug('Running command: %s', ' '.join(cmd))
            
            # Run the command
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                logger.error(f"FFMPEG command failed: {result.stderr}")
                raise RuntimeError(f"FFMPEG command failed: {result.stderr}")

            if not output_path.exists():
                raise RuntimeError(f"Output file was not created: {output_path}")

        except Exception as e:
            logger.error(f"Failed to add music: {e}")
            if output_path.exists():
                output_path.unlink()
            raise RuntimeError(f"Failed to add music: {e}")

def main() -> None:
    """
    Main function to parse arguments and start the music story processing.
    """
    parser = argparse.ArgumentParser(description="Instagram Music Story Creator.")
    parser.add_argument("input_dir", nargs="?", default=os.getenv("IMAGEINN_STORY_DIR"), help="Path to the input directory containing images or a single image file.")
    parser.add_argument("music_file", nargs="?", default=os.getenv("IMAGEINN_MUSIC_FILE"), help="Path to the music file to use.")
    parser.add_argument("--duration", type=Decimal, default=15.0, help="Duration of the story in seconds.")
    parser.add_argument("--fade-in", type=Decimal, default=0.0)
    parser.add_argument("--fade-out", type=Decimal, default=0.0)
    parser.add_argument("--volume", type=Decimal, default=1.0)
    parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    if args.music_file is None or args.input_dir is None:
        raise ValueError("Input dir and Music file are required")

    processor = IGMusicStoryProcessor(
        input_dir=Path(args.input_dir),
        music_file=Path(args.music_file),
        duration=args.duration,
        fade_in=args.fade_in,
        fade_out=args.fade_out,
        volume=args.volume
    )
    processor.process_images()

if __name__ == "__main__":
    main()
