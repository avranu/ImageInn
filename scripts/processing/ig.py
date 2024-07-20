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
import time
from PIL import Image, ImageFilter, ImageEnhance, ImageOps
import argparse
from typing import Any, Protocol, runtime_checkable
from tqdm import tqdm
from dataclasses import dataclass, field
from decimal import Decimal
import numpy as np

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Define typealias for Number
@runtime_checkable
class Number(Protocol):
    def __float__(self) -> float:
        ...

DEFAULT_CANVAS_SIZE : int = 2160
DEFAULT_MARGIN : int = 100
DEFAULT_BLUR : int = 100
DEFAULT_BRIGHTNESS : Number = 1.8
DEFAULT_CONTRAST : Number = 0.5
DEFAULT_SATURATION : Number = 0.5
DEFAULT_BORDER : int = 8

class IGImage:
    """
    Stores data about the image we are processing, including the original image, the scaled image, and the blurred image, the canvas size, margins, and so on.
    """
    

@dataclass
class IGImageProcessor:
    """
    Process images for Instagram posts.

    Args:
        input_dir (Path): Path to the directory containing JPG images.
        margin (int): Margin size for the canvas.
        canvas_size (int): Size of the canvas for the output images.
        blur_amount (Number): Amount of Gaussian blur to apply.
        brightness_factor (Number): Brightness factor for the background.
        contrast_factor (Number): Contrast factor for the background.
        saturation_factor (Number): Saturation factor for the background.
        border_size (int): Border size for the scaled image.
        file_suffix (str): Suffix to add to the processed images.
        max_errors (int): Maximum number of errors to allow before stopping.
        target_size (int): Target size for the scaled images.
    """
    input_dir: Path
    margin: int = DEFAULT_MARGIN
    canvas_size: int = DEFAULT_CANVAS_SIZE
    blur_amount: Number = DEFAULT_BLUR
    brightness_factor: Number = DEFAULT_BRIGHTNESS
    contrast_factor: Number = DEFAULT_CONTRAST
    saturation_factor: Number = DEFAULT_SATURATION
    border_size: int = DEFAULT_BORDER
    file_suffix: str = '_ig'
    max_errors: int = 5
    make_image_adjustments: bool = False

    def get_canvas_area(self, image: Image.Image) -> tuple[int, int]:
        """
        Calculate the area of the canvas and the area the image can take up on the canvas.
        """
        canvas_size = self.canvas_size
        margin_size = self.margin
        target_size = self.canvas_size - (2 * self.margin)
        
        # If the original image is smaller than the target size, halve the canvas size
        if max(image.width, image.height) < target_size:
            canvas_size = max(1080, canvas_size // 2)
            margin_size = max(50, margin_size // 2)
            target_size = canvas_size - (2 * margin_size)

        return canvas_size, target_size

    def process_images(self) -> None:
        """
        Process all JPG images in the input directory.

        Ignore any that end in "_ig"
        """
        count : int = 0
        images = [img for img in self.input_dir.glob('*.jpg') if img.is_file() and not img.stem.endswith(self.file_suffix)]
        error_count : int = 0

        # Check if any files will be overwritten
        existing_files = [str(img) for img in images if (self.input_dir / f"{img.stem}{self.file_suffix}.jpg").exists()]
        if existing_files:
            logger.warning(f"{len(existing_files)} files will be overwritten. Waiting for 5 seconds before continuing: {'\n'.join(existing_files)}")
            time.sleep(5)
        
        for file_path in tqdm(images, desc="Processing images"):
            try:
                self.process_image(file_path)
                count += 1
            except Exception as e:
                logger.error(f"Failed to process {file_path}: {e}")
                error_count += 1
                if error_count >= self.max_errors:
                    logger.error(f"Reached maximum error count ({self.max_errors}). Stopping.")
                    break

        logger.info(f"Processed {count} images")

    def process_image(self, file_path: Path) -> None:
        """
        Process a single image: scale, apply background edits, and save.
        
        Args:
            file_path (Path): Path to the file to process.
        """
        logger.debug(f"Processing image: {file_path}")
        original_img = Image.open(file_path)

        # If the original image is smaller than the target size, halve the canvas size
        canvas_size, target_size = self.get_canvas_area(original_img)

        logger.debug('Creating canvas')
        canvas = Image.new('RGB', (canvas_size, canvas_size), (255, 255, 255))

        scaled_img = self.scale_image(original_img, target_size)
        if self.make_image_adjustments:
            scaled_img = self.adjust_image(scaled_img)
            
        blurred_img = self.create_blurred_background(original_img, canvas_size)

        self.apply_edits(canvas, blurred_img, scaled_img, file_path)

    def scale_image(self, image: Image.Image, target_size : int) -> Image.Image:
        """
        Scale the image to fit within the target size, maintaining aspect ratio.
        
        Args:
            image (Image.Image): Original image to be scaled.
        
        Returns:
            Image.Image: Scaled image.
        """ 
        img_ratio = min(target_size / image.width, target_size / image.height)
        new_size = (int(image.width * img_ratio), int(image.height * img_ratio))
        logger.debug(f"Scaling image to {new_size}")
        return image.resize(new_size)

    def create_blurred_background(self, image: Image.Image, canvas_size: int) -> Image.Image:
        """
        Create a blurred and enhanced version of the image for background.
        
        Args:
            image (Image.Image): Original image to be processed.
        
        Returns:
            Image.Image: Processed background image.
        """
        logger.debug('Resizing blurred background image')
        img_ratio = max(canvas_size / image.width, canvas_size / image.height)
        new_size = (int(image.width * img_ratio), int(image.height * img_ratio))
        blurred_img = image.copy().resize(new_size)
        
        logger.debug('Applying blur to background image')
        blurred_img = blurred_img.filter(ImageFilter.GaussianBlur(self.blur_amount))
        blurred_img = blurred_img.filter(ImageFilter.SMOOTH)

        # Apply autocontrast first, so we have a standard base to adjust from for all images
        #blurred_img = ImageOps.autocontrast(blurred_img)

        # Apply adjustments
        logger.debug('Applying adjustments to background image')
        blurred_img = ImageEnhance.Brightness(blurred_img).enhance(self.brightness_factor)
        blurred_img = ImageEnhance.Contrast(blurred_img).enhance(self.contrast_factor)
        blurred_img = ImageEnhance.Color(blurred_img).enhance(self.saturation_factor)
        
        logger.debug('Background image processing complete')

        return blurred_img

    def adjust_image(self, image: Image.Image) -> Image.Image:
        """
        Adjust the image's saturation, highlights, and shadows based on histogram analysis.
        
        Args:
            image (Image.Image): Image to adjust.
        
        Returns:
            Image.Image: Adjusted image.
        """
        logger.debug('Analyzing image histogram for adjustments')

        # Convert to numpy array for analysis
        img_array = np.array(image)
        hist, _ = np.histogram(img_array, bins=256, range=(0, 255))
        
        # Calculate saturation
        hsv_img = image.convert("HSV")
        h, s, v = hsv_img.split()
        saturation = np.array(s)
        luminance = np.array(v)
        #saturation_hist, _ = np.histogram(saturation, bins=256, range=(0, 255))

        mean_saturation = np.mean(saturation)
        if mean_saturation > 200:
            logger.info('Reducing saturation')
            image = ImageEnhance.Color(image).enhance(0.7)

        mean_luminance = np.mean(luminance)
        if mean_luminance < 50:
            logger.info('Brightening image')
            image = ImageEnhance.Brightness(image).enhance(1.2)
        elif mean_luminance > 200:
            logger.info('Darkening image')
            image = ImageEnhance.Brightness(image).enhance(0.8)

        # Calculate highlights and shadows
        dark_pixels = np.sum(hist[:50]) # dark pixels
        light_pixels = np.sum(hist[205:])  # light pixels

        """
        if dark_pixels > len(img_array) * 0.3:
            logger.debug('Brightening shadows')
            image = ImageEnhance.Brightness(image).enhance(1.2)

        if light_pixels > len(img_array) * 0.3:  # Arbitrary threshold for too many light pixels
            logger.debug('Reducing highlights')
            image = ImageEnhance.Contrast(image).enhance(0.8)
        """

        """
        # Sharpen slightly
        logger.debug('Sharpening image')
        image = image.filter(ImageFilter.UnsharpMask(radius=1, percent=50, threshold=4))

        logger.info('Adjusted image with %d mean sat, %d mean lum, %d darks, %d lights', 
                    round(mean_saturation), 
                    round(mean_luminance), 
                    dark_pixels, 
                    light_pixels)
        """

        
        logger.debug('Image adjustments complete')
        return image

    def apply_edits(self, canvas: Image.Image, blurred_img: Image.Image, scaled_img: Image.Image, file_path: Path) -> None:
        """
        Apply final edits to the canvas and save the processed image.
        
        Args:
            canvas (Image.Image): Canvas image to place the final edits on.
            blurred_img (Image.Image): Blurred background image.
            scaled_img (Image.Image): Scaled original image.
            file_path (Path): Path of the file being processed.
        """
        logger.debug('Copying blurred image to canvas')
        canvas.paste(blurred_img, (0, 0))

        logger.debug('Placing scaled image on canvas')
        canvas_size = canvas.width
        x_offset = (canvas_size - scaled_img.width) // 2
        y_offset = (canvas_size - scaled_img.height) // 2
        canvas.paste(scaled_img, (x_offset, y_offset))

        # Add a black border to the scaled image
        # -- if the canvas size is halved, the border size should be halved as well
        logger.debug('Adding border to scaled image')
        border_size = self.border_size
        if canvas_size < self.canvas_size:
            border_size = border_size // 2
            
        border_img = ImageOps.expand(scaled_img, border=border_size, fill='black').convert("RGB")
        canvas.paste(border_img, (x_offset - border_size, y_offset - border_size))

        logger.debug('Saving processed image')
        output_path = self.input_dir / f"{file_path.stem}{self.file_suffix}.jpg"
        if output_path.exists():
            logger.debug(f"Overwriting processed image: {output_path}")
        canvas.save(output_path)
        logger.debug(f"Processed image saved as {output_path}")

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
    parser.add_argument('--adjust-image', action='store_true', help='Adjust the image based on histogram analysis.')
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
        make_image_adjustments = args.adjust_image
    )
    processor.process_images()

if __name__ == "__main__":
    main()