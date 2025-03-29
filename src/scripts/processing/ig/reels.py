from __future__ import annotations
import logging
import os
import re
import sys
import random
import subprocess
import tempfile
from pathlib import Path
from decimal import Decimal
import argparse

from natsort import natsorted
import ffmpeg
from PIL import Image
from tqdm import tqdm
from pydantic import Field, field_validator

from scripts.processing.ig.processor import IGImageProcessor
from scripts.processing.ig.image import IGImage
from scripts.processing.meta import (
    Formats,
    DEFAULT_CANVAS_SIZE,
    DEFAULT_MARGIN,
    DEFAULT_BLUR,
    DEFAULT_BRIGHTNESS,
    DEFAULT_CONTRAST,
    DEFAULT_SATURATION,
    DEFAULT_BORDER,
    DEFAULT_TOPAZ_PATH,
    AdjustmentTypes,
    to_windows_path,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class IGReelProcessor(IGImageProcessor):
    """
    Process images into Instagram reels with music and image adjustments.

    Args:
        input_dir (Path): Directory or file to process.
        music_file (Path | None): Music file to use. If not provided, one is chosen at random from a default music directory.
        duration (Decimal): Reel duration in seconds.
        fade_in (Decimal): Fade-in duration.
        fade_out (Decimal): Fade-out duration.
        volume (Decimal): Audio volume (0.0-1.0).
        format (str): 'story' or 'post'; determines canvas dimensions and is reflected in the filename.
    """
    music_file: Path | None = Field(default=None)
    duration: Decimal = Field(default=15.0)
    fade_in: Decimal = Field(default=0.0)
    fade_out: Decimal = Field(default=0.0)
    volume: Decimal = Field(default=1.0)
    output_folder: str = Field(default="reels")
    format : str = Formats.REEL.value
    canvas_size : tuple[int, int] = Field(default=(1080, 1080))

    _music_files: list[Path] | None = None
    _music_index: int = 0

    @field_validator("music_file", mode="before")
    @classmethod
    def validate_music_file(cls, v):
        return Path(v) if v else None

    def __init__(self, **data):
        # Allow CLI to set format (story or post) without forcing a value.
        super().__init__(**data)
        
        # Set canvas dimensions based on format.
        self.canvas_size = (2160, 2700)

        # If no music file is provided, load music files from environment variable directory.
        if self.music_file is None or self.music_file.is_dir():
            music_dir = self.music_file or os.getenv("IMAGEINN_MUSIC_DIR")
            if not music_dir:
                raise ValueError("Music file not provided and IMAGEINN_MUSIC_DIR environment variable not set")
            music_dir = Path(music_dir)
            if not music_dir.exists() or not music_dir.is_dir():
                raise FileNotFoundError(f"Music directory not found: {music_dir}")
            # Look for common music file extensions.
            mp3_files = sorted(music_dir.glob("*.mp3"))
            wav_files = sorted(music_dir.glob("*.wav"))
            self._music_files = mp3_files + wav_files
            if not self._music_files:
                raise FileNotFoundError(f"No music files found in: {music_dir}")
            random.shuffle(self._music_files)
            # Use the list, not one file
            self.music_file = None
        else:
            self.music_file = Path(self.music_file)

    def _get_next_music_file(self) -> Path:
        """Return the next music file (cycling through random order if needed)."""
        if self.music_file is not None:
            return self.music_file
        if self._music_files is None or len(self._music_files) == 0:
            raise RuntimeError("No music files available")
        next_music = self._music_files[self._music_index]
        self._music_index += 1
        if self._music_index >= len(self._music_files):
            random.shuffle(self._music_files)
            self._music_index = 0
        return next_music

    def create_image(self, file_path: Path) -> IGImage:
        image = super().create_image(file_path)
        # Override canvas dimensions based on chosen format.
        image.canvas_size = self.canvas_size
        return image

    def process_images(self) -> None:
        """Process all images (ordered by filename)."""
        images = self._get_images()
        images = natsorted(self._get_images(), key=lambda p: p.name.lower())
        total = len(images)
        count = 0
        error_count = 0

        self.output_dir.mkdir(exist_ok=True)

        try:
            with tqdm(total=total, desc=f"Processing {total} images") as self._progress_bar:
                for file_path in images:
                    try:
                        self.process_image(file_path)
                        count += 1
                    except ValueError as e:
                        logger.error("Failed to process %s: %s", file_path, e)
                        error_count += 1
                        if error_count >= self.max_errors:
                            logger.error("Reached maximum error count (%s). Stopping.", self.max_errors)
                            raise
                    finally:
                        self.update_progress()
            logger.info("Processed %s images", count)

        finally:
            self.cleanup_topaz_output()
            
    def process_image(self, file_path: Path) -> None:
        """
        Process a single image: apply Topaz (if enabled), generate the final canvas,
        create a video, and add music.
        """
        self.update_progress(f"Processing image: {file_path.name}")
        
        # Apply Topaz if available (and if the file isn’t already Topaz-processed)
        topaz_file_path = None
        """
        if not self.skip_image_adjustments and self.topaz_available:
            # Avoid reprocessing if already a Topaz file
            if not file_path.stem.endswith("-topaz"):
                topaz_file_path = self.apply_topaz(file_path)
                if topaz_file_path:
                    file_path = topaz_file_path
        """

        # Create a single IGImage instance from the (possibly updated) file_path
        image = self.create_image(file_path)
        image.setup()  # This loads, scales, creates the blurred background, and applies adjustments

        if topaz_file_path:
            image.adjustments_applied(AdjustmentTypes.TOPAZ)

        logger.debug("Final canvas mode: %s, size: %s", image.canvas.mode, image.canvas.size)
        
        # Save the final composite (canvas) to a temporary file for video creation
        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            temp_image_path = temp_dir / "temp_image.jpg"
            temp_video_path = temp_dir / "temp_video.mp4"
            
            image.canvas.save(temp_image_path)
            self.create_video_from_image(temp_image_path, temp_video_path)
            
            music_path = self._get_next_music_file()
            # Build output filename (using natsorted-friendly sanitized strings)
            base_name = re.sub(r"[^a-zA-Z0-9]", "_", file_path.stem)[:50]
            music_name = re.sub(r"[^a-zA-Z0-9]", "", music_path.stem)[:25]
            output_filename = f"{base_name}_{self.format.lower()}_{music_name}.mp4"
            final_output_path = self.output_dir / output_filename

            if final_output_path.exists():
                logger.info("Output file already exists: %s. Skipping", final_output_path)
                return

            self.add_music_to_video(temp_video_path, music_path, final_output_path)
            
            if self.ig_output_dir:
                self.copy_file(final_output_path, self.ig_output_dir / final_output_path.name, skip_existing=True)
            
            # Clean up the Topaz file if it was created
            if topaz_file_path and topaz_file_path.exists():
                self.update_progress(f'Cleaning up: {topaz_file_path.name}')
                topaz_file_path.unlink()

    def create_video_from_image(self, image_path: Path, output_path: Path) -> None:
        """Create a video from a static image, ensuring dimensions are even."""
        if output_path.exists():
            logger.error("Output file already exists: %s. Not overwriting", output_path)
            return

        logger.debug("Creating video from image: %s -> %s", image_path, output_path)

        # Force even dimensions
        probe = ffmpeg.probe(str(image_path), v='error')
        width = int(probe['streams'][0]['width'])
        height = int(probe['streams'][0]['height'])
        even_width = width if width % 2 == 0 else width + 1
        even_height = height if height % 2 == 0 else height + 1

        try:
            (
                ffmpeg
                .input(str(image_path), loop=1, t=float(self.duration))
                .filter('scale', even_width, even_height)
                .output(str(output_path), vcodec="libx264", pix_fmt="yuv420p")
                .global_args("-loglevel", "error")
                .run()
            )
        except ffmpeg.Error as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            logger.error("Failed to create video: %s", error_msg)
            raise RuntimeError(f"FFMPEG error creating video: {error_msg}")


    def add_music_to_video(self, video_path: Path, music_path: Path, output_path: Path) -> None:
        """Add music with fade in/out effects to the video."""
        try:
            logger.debug("Adding music to video: %s + %s -> %s", video_path, music_path, output_path)
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
            if logger.isEnabledFor(logging.DEBUG):
                cmd.extend(["-loglevel", "info"])
            else:
                cmd.extend(["-loglevel", "error"])
            logger.debug("Running command: %s", " ".join(cmd))
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error("FFMPEG command failed: %s", result.stderr)
                raise RuntimeError(f"FFMPEG command failed: {result.stderr}")
            if not output_path.exists():
                raise RuntimeError(f"Output file was not created: {output_path}")
        except Exception as e:
            logger.error("Failed to add music: %s", e)
            if output_path.exists():
                output_path.unlink()
            raise RuntimeError(f"Failed to add music: {e}")


def main() -> None:
    try:
        """CLI entry point."""
        parser = argparse.ArgumentParser(
            description="Instagram Reel Creator with Music and Image Adjustments."
        )
        parser.add_argument("input_dir", nargs="?", default=os.getenv("IMAGEINN_REEL_DIR"),
                            help="Path to the input directory (or file) containing images.")
        parser.add_argument("music_file", nargs="?", default=None,
                            help="Path to the music file to use. If not provided, one is chosen at random from the default music directory.")
        parser.add_argument("--duration", type=Decimal, default=15.0, help="Duration of the reel in seconds.")
        parser.add_argument("--fade-in", type=Decimal, default=0.0, help="Fade-in duration in seconds.")
        parser.add_argument("--fade-out", type=Decimal, default=0.0, help="Fade-out duration in seconds.")
        parser.add_argument("--volume", type=Decimal, default=1.0, help="Audio volume level (0.0-1.0).")
        parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging.")

        args = parser.parse_args()

        if args.verbose:
            logger.setLevel(logging.DEBUG)

        if not args.input_dir:
            raise ValueError("Input directory is required")

        processor = IGReelProcessor(
            input_dir=Path(args.input_dir),
            music_file=args.music_file,
            duration=args.duration,
            fade_in=args.fade_in,
            fade_out=args.fade_out,
            volume=args.volume,
        )
        processor.process_images()
    except KeyboardInterrupt:
        print("\nProcess interrupted by user.")
        sys.exit(1)


if __name__ == "__main__":
    main()
