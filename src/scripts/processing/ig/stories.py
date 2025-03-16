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
from pydantic import Field, field_validator
from decimal import Decimal
from scripts.processing.ig.processor import IGImageProcessor
from scripts.processing.ig.image import IGImage
from scripts.processing.meta import Formats

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
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
    fade_in: Decimal = Field(default=1.0)
    fade_out: Decimal = Field(default=1.0)
    volume: Decimal = Field(default=0.7)
    output_folder: str = Field(default="music_stories")
    skip_image_adjustments: bool = Field(default=True)

    def __init__(self, **data):
        # Always force story format for music stories
        data['format'] = Formats.STORY.value
        data['place_into_canvas'] = True
        super().__init__(**data)

    @field_validator('input_dir', mode='before')
    @classmethod
    def validate_input_dir(cls, v):
        if not v:
            return None
        path = Path(v)
        return cls._fix_input_path(path)

    @field_validator('music_file', mode="before")
    @classmethod
    def validate_music_file(cls, v):
        if not v:
            raise ValueError("Music file is required")

        path = Path(v)
        return cls._fix_music_path(path)

    @field_validator('duration', mode="before")
    def validate_duration(cls, v):
        if v <= 0:
            raise ValueError("Duration must be positive")
        return v

    @field_validator('volume', mode="before")
    def validate_volume(cls, v):
        if v < 0 or v > 1:
            raise ValueError("Volume must be between 0.0 and 1.0")
        return v

    @classmethod
    def _fix_input_path(cls, path : Path) -> Path:
        if path.exists():
            return path
        
        if not path.is_absolute():
            parent = os.getenv('IMAGEINN_STORY_DIR', None)
            if parent:
                path = Path(parent) / path

        if path.exists():
            return path
        raise FileNotFoundError(f"File not found: {path}")
        
    @classmethod
    def _fix_music_path(cls, path : Path) -> Path:
        if path.exists():
            return path
        
        if not path.is_absolute():
            parent = os.getenv('IMAGEINN_MUSIC_DIR', None)
            if parent:
                path = Path(parent) / path

        if path.exists():
            return path
        raise FileNotFoundError(f"File not found: {path}")

    def process_images(self) -> None:
        """
        Process all JPG images in the input directory.

        Ignore any that end in "_ig"
        """
        count : int = 0
        error_count : int = 0
        images = self._get_images()
        total = len(images)

        try:
            # Ensure output dirs exist
            self.output_dir.mkdir(exist_ok=True)

            with tqdm(total=total, desc="Processing images") as self._progress_bar:
                for file_path in images:
                    try:
                        """
                        if self.check_if_processed(file_path):
                            logger.debug(f"Skipping {file_path.name}. Already processed.")
                            continue
                        """
                        self.process_image(file_path)
                        count += 1
                    except Exception as e:
                        logger.error(f"Failed to process {file_path}: {e}")
                        error_count += 1
                        if error_count >= self.max_errors:
                            logger.error(f"Reached maximum error count ({self.max_errors}). Stopping.")
                            break
                    finally:
                        self.update_progress()

        finally:
            self.cleanup_topaz_output()

        logger.info("Processed %s images", count)

    def process_image(self, file_path: Path) -> None:
        """
        Process a single image into a music story.
        """
        self.update_progress(f"Processing image: {file_path.name}")

        # Determine if topaz is needed
        topaz_file_path = None
        if not self.skip_image_adjustments:
            if topaz_file_path := self.apply_topaz(file_path):
                file_path = topaz_file_path

        # Create IGImage instance
        self.update_progress(f"Setting up image frame: {file_path.name}")
        image = Image.open(file_path)
        
        # Save the processed image to a temp file
        temp_dir = Path(tempfile.mkdtemp())
        temp_image_path = temp_dir / f"temp_image.jpg"
        temp_video_path = temp_dir / f"temp_video.mp4"
        final_output_path = self.output_dir / f"{file_path.stem}_story_music.mp4"
        
        self.update_progress(f"Saving temporary image")
        image.save(temp_image_path)
        
        # Create video from image
        self.update_progress(f"Creating video from image")
        self.create_video_from_image(temp_image_path, temp_video_path)
        
        # Add music to video
        self.update_progress(f"Adding music to video")
        self.add_music_to_video(temp_video_path, self.music_file, final_output_path)
        
        # Clean up temp files
        self.update_progress(f"Cleaning up")
        shutil.rmtree(temp_dir)
        
        if topaz_file_path:
            topaz_file_path.unlink()
            
        # Copy to Instagram folder if available
        if self.ig_output_dir:
            self.update_progress(f'Copying to Instagram folder: {final_output_path.name}')
            self.copy_file(final_output_path, self.ig_output_dir / final_output_path.name, skip_existing=True)

    def create_video_from_image(self, image_path: Path, output_path: Path) -> None:
        """
        Create a video from a static image with the specified duration.
        """
        logger.debug('Creating video from image: %s -> %s', image_path, output_path)
        try:
            (
                ffmpeg
                .input(str(image_path), loop=1, t=float(self.duration))
                .output(str(output_path), vcodec='libx264', pix_fmt='yuv420p')
                .global_args('-loglevel', 'error')
                .run()
            )
        except ffmpeg.Error as e:
            logger.error(f"Failed to create video: {e.stderr.decode() if e.stderr else str(e)}")
            raise

    def add_music_to_video(self, video_path: Path, music_path: Path, output_path: Path) -> None:
        """
        Add music to a video with fade in/out effects.
        """
        try:
            logger.debug('Inputting video path into ffmpeg')
            video = ffmpeg.input(str(video_path))
            logger.debug('Inputting music path into ffmpeg (afade in %s, out %s, volume %s)', self.fade_in, float(self.duration)-float(self.fade_out), self.volume)
            audio = (
                ffmpeg
                .input(str(music_path))
                .filter('afade', type='in', start_time=0, duration=float(self.fade_in))
                .filter('afade', type='out', start_time=float(self.duration)-float(self.fade_out), duration=float(self.fade_out))
                .filter('volume', volume=float(self.volume))
            )

            loglevel = 'info' if logger.isEnabledFor(logging.DEBUG) else 'error'

            logger.debug('Outputting video with music. Output path: %s, duration: %s', output_path, self.duration)
            logger.debug('You can reproduce with the following cli command: %s', f'ffmpeg -i "{video_path}" -i "{music_path}" -af afade=in:st=0:d={self.fade_in},afade=out:st={float(self.duration)-float(self.fade_out)}:d={self.fade_out},volume={self.volume} -t {self.duration} {output_path} -loglevel "info')
            (
                ffmpeg
                .output(video.video, audio, str(output_path), t=float(self.duration), shortest=None)
                .global_args('-loglevel', loglevel)
                .run()
            )
        except ffmpeg.Error as e:
            logger.error(f"Failed to add music: {e.stderr.decode() if e.stderr else str(e)} -> {e}")
            # If the file exists, delete it
            if output_path.exists():
                output_path.unlink()
            raise

def main() -> None:
    """
    Main function to parse arguments and start the music story processing.
    """
    parser = argparse.ArgumentParser(description='''Instagram Music Story Creator.
                    This script processes images into Instagram stories with music background.''')
    parser.add_argument('input_dir', type=Path, help='Path to the input directory containing images.')
    parser.add_argument('music_file', type=Path, help='Path to the music file to use.')
    parser.add_argument('--duration', type=Decimal, default=15.0, help='Duration of the story in seconds (default: 15).')
    parser.add_argument('--fade-in', type=Decimal, default=1.0, help='Fade in duration in seconds (default: 1).')
    parser.add_argument('--fade-out', type=Decimal, default=1.0, help='Fade out duration in seconds (default: 1).')
    parser.add_argument('--volume', type=Decimal, default=0.7, help='Music volume (0.0-1.0, default: 0.7).')
    parser.add_argument('--margin', type=int, default=50, help='Margin size for the canvas.')
    #parser.add_argument('--skip-adjustments', action='store_true', help='Skip adjustments to the main image.')
    parser.add_argument('--topaz-exe', type=Path, help='Path to the Topaz DeNoise AI executable.')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging.')
    
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    processor = IGMusicStoryProcessor(
        input_dir=args.input_dir,
        music_file=args.music_file,
        duration=args.duration,
        fade_in=args.fade_in,
        fade_out=args.fade_out,
        volume=args.volume,
        margin=args.margin,
        #skip_image_adjustments=args.skip_adjustments,
        topaz_exe=args.topaz_exe
    )
    processor.process_images()

if __name__ == "__main__":
    main()