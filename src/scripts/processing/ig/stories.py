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
    fade_in: Decimal = Field(default=0.0)
    fade_out: Decimal = Field(default=0.0)
    volume: Decimal = Field(default=1.0)
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
        
        try:
            images = self._get_images()
            total = len(images)

            # Ensure output dirs exist
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

        # Create a simplified output filename
        base_name = re.sub(r'[^a-zA-Z0-9]', '_', file_path.stem)[:50]  # Limit length and remove problematic chars
        unique_id = str(uuid.uuid4())[:8]  # Add a unique ID to prevent overwrites
        output_filename = f"{base_name}_{unique_id}_story_music.mp4"
        final_output_path = self.output_dir / output_filename

        # Create temp directory
        temp_dir = Path(tempfile.mkdtemp())
        temp_image_path = temp_dir / f"temp_image.jpg"
        temp_video_path = temp_dir / f"temp_video.mp4"
        
        try:
            # Open and process image
            self.update_progress(f"Setting up image frame")
            image = Image.open(file_path)
            
            # Ensure output directory exists
            self.output_dir.mkdir(exist_ok=True)
            
            # Save the processed image to a temp file
            self.update_progress(f"Saving temporary image")
            image.save(temp_image_path)
            
            # Create video from image
            self.update_progress(f"Creating video from image")
            self.create_video_from_image(temp_image_path, temp_video_path)
            
            # Add music to video
            self.update_progress(f"Adding music to video")
            self.add_music_to_video(temp_video_path, self.music_file, final_output_path)
            
            # Copy to Instagram folder if available
            if self.ig_output_dir:
                self.update_progress(f'Copying to Instagram folder: {final_output_path.name}')
                self.copy_file(final_output_path, self.ig_output_dir / final_output_path.name, skip_existing=True)
                
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            raise
            
        finally:
            # Clean up temp files
            self.update_progress(f"Cleaning up")
            shutil.rmtree(temp_dir)
            
            if topaz_file_path and topaz_file_path.exists():
                topaz_file_path.unlink()

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
            
            # Alternative implementation using subprocess instead of python-ffmpeg
            # This can be more reliable in some cases
            fade_out_start = float(self.duration) - float(self.fade_out)
            cmd = [
                'ffmpeg',
                '-i', str(video_path),
                '-i', str(music_path),
                '-c:v', 'copy',  # Copy video codec to avoid re-encoding
                '-af', f'afade=in:st=0:d={self.fade_in},afade=out:st={fade_out_start}:d={self.fade_out},volume={self.volume}',
                '-t', str(self.duration),
                '-shortest',
                '-y',  # Overwrite output files without asking
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
                
            # Verify the output was created successfully
            if not output_path.exists():
                raise RuntimeError(f"Output file was not created: {output_path}")
                
            logger.debug('Successfully created music video at %s', output_path)
            
        except Exception as e:
            logger.error(f"Failed to add music: {e}")
            # If the file exists, delete it
            if output_path.exists():
                output_path.unlink()
            raise RuntimeError(f"Failed to add music: {e}")

def main() -> None:
    """
    Main function to parse arguments and start the music story processing.
    """
    parser = argparse.ArgumentParser(description='''Instagram Music Story Creator.
                    This script processes images into Instagram stories with music background.''')
    parser.add_argument('input_dir', type=str, help='Path to the input directory containing images or a single image file.')
    parser.add_argument('music_file', type=str, default=None, help='Path to the music file to use.')
    parser.add_argument('--duration', type=Decimal, default=15.0, help='Duration of the story in seconds (default: 15).')
    parser.add_argument('--fade-in', type=Decimal, default=0.0, help='Fade in duration in seconds (default: 1).')
    parser.add_argument('--fade-out', type=Decimal, default=0.0, help='Fade out duration in seconds (default: 1).')
    parser.add_argument('--volume', type=Decimal, default=1.0, help='Music volume (0.0-1.0, default: 0.7).')
    parser.add_argument('--margin', type=int, default=50, help='Margin size for the canvas.')
    parser.add_argument('--topaz-exe', type=Path, help='Path to the Topaz DeNoise AI executable.')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging.')
    
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    if args.music_file is None:
        args.music_file = os.getenv('IMAGEINN_MUSIC_FILE', None)
        if not args.music_file:
            raise ValueError("Music file is required")

    processor = IGMusicStoryProcessor(
        input_dir=Path(args.input_dir),
        music_file=Path(args.music_file),
        duration=args.duration,
        fade_in=args.fade_in,
        fade_out=args.fade_out,
        volume=args.volume,
        margin=args.margin,
        topaz_exe=args.topaz_exe if args.topaz_exe else None
    )
    processor.process_images()

if __name__ == "__main__":
    main()
