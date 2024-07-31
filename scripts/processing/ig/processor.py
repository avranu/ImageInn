"""
Process images for Instagram posts.

This script processes JPG images in a directory, scaling them to fit within a square canvas, 
applies a blurred and enhanced version of the image as the background, and saving the 
processed image with a suffix.

Usage: 
    ig.py [-h] [--margin MARGIN] [--size SIZE] [--blur BLUR] [--brightness BRIGHTNESS] 
            [--contrast CONTRAST] [--saturation SATURATION] [--border BORDER]
            [--suffix SUFFIX]
            input_dir

positional arguments:
  input_dir             Path to the input directory containing JPG images.

options:
  -h, --help            show this help message and exit
  --margin MARGIN, -m MARGIN
                        Margin size for the canvas.
  --size SIZE, -s SIZE  Canvas size for the output images.
  --blur BLUR, -b BLUR  Amount of Gaussian blur to apply.
  --brightness BRIGHTNESS, -br BRIGHTNESS
                        Brightness factor for the background.
  --contrast CONTRAST, -c CONTRAST
                        Contrast factor for the background.
  --saturation SATURATION, -sat SATURATION
                        Saturation factor for the background.
  --border BORDER       Border size for the scaled image.
  --suffix SUFFIX       Suffix to add to the processed images.

Examples:
    # Basic Usage
    python ig.py images/

    # For more complex customization:
    python ig.py images/ -m 50 -s 1080 -b 10 -br 1.5 -c 0.7 -sat 0.8 -border 2 -suffix _processed
"""
from __future__ import annotations
import logging
from pathlib import Path
import subprocess
import time
from PIL import Image, ImageFilter, ImageEnhance
import argparse
from tqdm import tqdm
from dataclasses import dataclass, field
from decimal import Decimal
import numpy as np
from scripts.lib.types import Number
from scripts.processing.ig.meta import (
    DEFAULT_CANVAS_SIZE, 
    DEFAULT_MARGIN, 
    DEFAULT_BLUR, 
    DEFAULT_BRIGHTNESS, 
    DEFAULT_CONTRAST, 
    DEFAULT_SATURATION, 
    DEFAULT_BORDER,
    AdjustmentTypes,
    to_windows_path,
    DEFAULT_TOPAZ_PATH
)
from scripts.processing.ig.image import IGImage

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class IGImageProcessor:
    """
    Process images for Instagram posts.

    Args:
        input_dir (Path): Path to the directory containing JPG images.
        margin (int): Ideal margin size for the canvas.
        canvas_size (int): Ideal size of the canvas for the output images.
        blur_amount (Number): Amount of Gaussian blur to apply.
        brightness_factor (Number): Brightness factor for the background.
        contrast_factor (Number): Contrast factor for the background.
        saturation_factor (Number): Saturation factor for the background.
        border_size (int): Border size for the scaled image.
        file_suffix (str): Suffix to add to the processed images.
        max_errors (int): Maximum number of errors to allow before stopping.
        make_image_adjustments (bool): Flag to enable/disable image adjustments.
    """
    input_dir: Path
    margin: int = field(default=DEFAULT_MARGIN)
    canvas_size: int = field(default=DEFAULT_CANVAS_SIZE)
    blur_amount: Number = field(default=DEFAULT_BLUR)
    brightness_factor: Number = field(default=DEFAULT_BRIGHTNESS)
    contrast_factor: Number = field(default=DEFAULT_CONTRAST)
    saturation_factor: Number = field(default=DEFAULT_SATURATION)
    border_size: int = field(default=DEFAULT_BORDER)
    file_suffix: str = '_ig'
    max_errors: int = 5
    skip_image_adjustments: bool = False
    topaz_exe: Path | None = field(default=DEFAULT_TOPAZ_PATH)
    _progress_bar : tqdm | None = field(init=False, default=None)
    _topaz_available: bool | None = field(init=False, default=None)
    topaz_output_dir : Path | None = field(init=False, default=None)

    @property
    def progress_bar(self) -> tqdm | None:
        return self._progress_bar

    @property
    def topaz_available(self) -> bool:
        if self._topaz_available is None:
            self._topaz_available = self.topaz_exe and self.topaz_exe.exists()
            logger.info('Checking if Topaz DeNoise AI is available: ... %s', self._topaz_available)
            
        return self._topaz_available

    def _get_images(self) -> list[Path]:
        files = [img for img in self.input_dir.glob('*.jpg') if img.is_file() and not img.stem.endswith(self.file_suffix)]

        # Check if any files will be overwritten
        existing_files = [str(img) for img in files if (self.input_dir / f"{img.stem}{self.file_suffix}.jpg").exists()]
        if existing_files:
            logger.warning(f"{len(existing_files)} files will be overwritten. Waiting for 10 seconds before continuing")
            time.sleep(10)

        return files

    def create_image(self, file_path : Path) -> IGImage:
        return IGImage(file_path = file_path, processor = self)

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
            if not self.skip_image_adjustments:
                if self.topaz_available:
                    total *= 2
                    self.topaz_output_dir = self.input_dir / 'topaz'
                    self.topaz_output_dir.mkdir(exist_ok=True)

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
            # Cleanup by removing topaz dir
            if self.topaz_output_dir:
                self.topaz_output_dir.rmdir()

        logger.info(f"Processed {count} images")

    def update_progress(self, description : str = None) -> None:
        if not self.progress_bar:
            logger.error('Progress bar not initialized')
            return
        
        if description:
            self.progress_bar.set_description(description)
            logger.debug(description)
        else:
            self.progress_bar.update(1)

    def process_image(self, file_path: Path) -> None:
        """
        Process a single image: scale, apply background edits, and save.
        
        Args:
            file_path (Path): Path to the file to process.
        """
        self.update_progress(f"Processing image: {file_path.name}")

        # Determine if topaz is needed
        topaz_file_path = None
        if not self.skip_image_adjustments:
            if topaz_file_path := self.apply_topaz(file_path):
                file_path = topaz_file_path
        
        # Create IGImage instance
        self.update_progress(f"Setting up image frame: {file_path.name}")
        image = self.create_image(file_path)
        image.setup()
        
        if topaz_file_path:
            image.adjustments_applied(AdjustmentTypes.TOPAZ)

        self.update_progress(f'Saving image: {image.output_path.name}')
        image.save()

        # Cleanup, by removing topaz output
        if topaz_file_path:
            self.update_progress(f'Cleaning up: {topaz_file_path.name}')
            topaz_file_path.unlink()

    def apply_topaz(self, image_path : Path, timeout : int = 300) -> Path | None:
        """
        Apply Topaz DeNoise AI to the image.

        This is equivalent to the following Powershell command:
        C:/Program Files/Topaz Labs LLC/Topaz Photo AI> & './tpai.exe' "__FILE_PATH__" --output "__OUTPUT_PATH__/topaz"
        """
        if not self.topaz_available:
            return None
        
        self.update_progress(f'Applying Topaz DeNoise AI: {image_path.name}')

        # Convert paths to windows format for Topaz CLI
        input_path = to_windows_path(image_path)
        output_path = to_windows_path(self.topaz_output_dir)

        # Run Topaz DeNoise AI
        topaz_path = self.topaz_exe
        cmd = [str(topaz_path), input_path, '--output', output_path]
        logger.debug(f"Running command: {cmd}")
        
        # Default Timeout set to 5 minutes
        subprocess.run(cmd, capture_output=True, check=True, timeout=timeout)

        # Check for output. Original filename in the output_path dir
        topaz_output = self.topaz_output_dir / f"{image_path.stem}.jpg"
        if not topaz_output.exists():
            logger.error(f"Topaz output not found: {topaz_output}")
            return None

        # Move topaz output back one dir
        new_path = image_path.parent / f"{image_path.stem}-topaz.jpg"
        topaz_output.rename(new_path)
        
        return new_path

    def adjust_image(self, image: IGImage, force : bool = False):
        """
        Adjust the image's saturation, highlights, and shadows based on histogram analysis.
        """
        if self.skip_image_adjustments:
            if not force:
                logger.debug('Skipping image adjustments')
                return
            
            logger.debug('Forcing image adjustments')
        
        logger.debug('Analyzing image histogram for adjustments')
        main_image = image.scaled

        # Convert to numpy array for analysis
        img_array = np.array(main_image)
        hist, _ = np.histogram(img_array, bins=256, range=(0, 255))
        
        # Calculate saturation
        hsv_img = main_image.convert("HSV")
        h, s, v = hsv_img.split()
        saturation = np.array(s)
        luminance = np.array(v)

        mean_saturation = np.mean(saturation)
        if mean_saturation > 200:
            logger.debug('Reducing saturation')
            main_image = ImageEnhance.Color(main_image).enhance(0.7)
            image.adjustments_applied(AdjustmentTypes.COLOR)

        mean_luminance = np.mean(luminance)
        if mean_luminance < 50:
            logger.debug('Brightening image')
            main_image = ImageEnhance.Brightness(main_image).enhance(1.2)
            image.adjustments_applied(AdjustmentTypes.BRIGHTNESS)
        elif mean_luminance > 200:
            logger.debug('Darkening image')
            main_image = ImageEnhance.Brightness(main_image).enhance(0.8)
            image.adjustments_applied(AdjustmentTypes.BRIGHTNESS)

        image.scaled = main_image
        logger.debug('Image adjustments complete')

    def create_blurred_background(self, image : Image.Image, size : tuple[int, int], luminance : int = 185) -> Image.Image:
        """
        Create a blurred and enhanced version of the image for background.
        
        Returns:
            Image.Image: Processed background image.
        """
        blurred = image.copy().resize(size, Image.LANCZOS)
        
        logger.debug('Applying blur to background image')
        blurred = blurred.filter(ImageFilter.GaussianBlur(DEFAULT_BLUR))
        blurred = blurred.filter(ImageFilter.SMOOTH)

        # Apply adjustments
        logger.debug('Applying adjustments to background image')
        blurred = ImageEnhance.Brightness(blurred).enhance(DEFAULT_BRIGHTNESS)
        blurred = ImageEnhance.Contrast(blurred).enhance(DEFAULT_CONTRAST)
        blurred = ImageEnhance.Color(blurred).enhance(DEFAULT_SATURATION)

        # Brighten/darken to average luminance of 185
        current_luminance = np.mean(np.array(blurred.convert('L')))
        if current_luminance < luminance:
            logger.debug('Brightening background image')
            brightness = 1 + (luminance - current_luminance) / luminance
            blurred = ImageEnhance.Brightness(blurred).enhance(brightness)

        logger.debug('Background image processing complete')
        return blurred
    
def main() -> None:
    """Main function to parse arguments and start the image processing."""
    parser = argparse.ArgumentParser(description='''Instagram Image Processor. 
                    This script processes JPG images in a directory, scaling them to fit within a square canvas, 
                    applyies a blurred and enhanced version of the image as the background, and saving the 
                    processed image with a suffix.''')
    parser.add_argument('input_dir', type=Path, help='Path to the input directory containing JPG images.')
    parser.add_argument('--margin', '-m', type=int, default=DEFAULT_MARGIN, help='Margin size for the canvas.')
    parser.add_argument('--size', '-s', type=int, default=DEFAULT_CANVAS_SIZE, help='Canvas size for the output images.')
    parser.add_argument('--blur', '-b', type=Decimal, default=DEFAULT_BLUR, help='Amount of Gaussian blur to apply.')
    parser.add_argument('--brightness', '-br', type=Decimal, default=DEFAULT_BRIGHTNESS, help='Brightness factor for the background.')
    parser.add_argument('--contrast', '-c', type=Decimal, default=DEFAULT_CONTRAST, help='Contrast factor for the background.')
    parser.add_argument('--saturation', '-sat', type=Decimal, default=DEFAULT_SATURATION, help='Saturation factor for the background.')
    parser.add_argument('--border', type=int, default=DEFAULT_BORDER, help='Border size for the scaled image.')
    parser.add_argument('--suffix', type=str, default='_ig', help='Suffix to add to the processed images.')
    parser.add_argument('--skip-adjustments', action='store_true', help='Skip adjustments to the main image based on histogram analysis.')
    parser.add_argument('--topaz-exe', type=Path, default=DEFAULT_TOPAZ_PATH, help='Path to the Topaz DeNoise AI executable.')
    args = parser.parse_args()

    processor = IGImageProcessor(
        input_dir = args.input_dir,
        margin = args.margin,
        canvas_size = args.size,
        blur_amount = args.blur,
        brightness_factor = args.brightness,
        contrast_factor = args.contrast,
        saturation_factor = args.saturation,
        border_size = args.border,
        file_suffix = args.suffix,
        skip_image_adjustments = args.skip_adjustments,
        topaz_exe = args.topaz_exe
    )
    processor.process_images()

if __name__ == "__main__":
    main()