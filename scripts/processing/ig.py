from decimal import Decimal
import logging
from numbers import Number
from pathlib import Path
from PIL import Image, ImageFilter, ImageEnhance, ImageOps
import argparse
from typing import Tuple

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class IGImageProcessor:
    input_dir : Path
    canvas_size : int
    margin : int
    target_size : int
    blur_amount : Number
    brightness_factor : Number
    contrast_factor : Number
    saturation_factor : Number
    border_size : int
    file_suffix : str
    
    def __init__(self, 
                 input_dir: Path, 
                 margin: int = 100, 
                 canvas_size: int = 2160,
                 blur_amount: Number = 10,
                 brightness_factor: Number = 1.6,
                 contrast_factor: Number = 0.5,
                 saturation_factor: Number = 0.85,
                 border_size : int = 4,
                 file_suffix : str = '_ig') -> None:
        """
        Initialize the ImageProcessor with the input directory.
        
        Args:
            input_dir (Path): Path to the directory containing the input images.
        """
        self.input_dir = input_dir
        self.canvas_size = canvas_size
        self.margin = margin
        self.target_size = self.canvas_size - 2 * self.margin
        self.blur_amount = blur_amount
        self.brightness_factor = brightness_factor
        self.contrast_factor = contrast_factor
        self.saturation_factor = saturation_factor
        self.border_size = border_size
        self.file_suffix = file_suffix

    def process_images(self) -> None:
        """
        Process all JPG images in the input directory.

        Ignore any that end in "_ig"
        """
        for file_path in self.input_dir.glob('*.jpg'):
            if not file_path.stem.endswith('_ig'):
                self.process_image(file_path)

    def process_image(self, file_path: Path) -> None:
        """
        Process a single image: scale, apply background edits, and save.
        
        Args:
            file_path (Path): Path to the file to process.
        """
        try:
            logger.debug(f"Processing image: {file_path}")
            original_img = Image.open(file_path)

            # If the original image is smaller than the target size, halve the canvas size
            canvas_size = self.canvas_size
            if max(original_img.width, original_img.height) < self.target_size:
                canvas_size = self.canvas_size // 2
            
            logger.debug('Creating canvas')
            canvas = Image.new('RGB', (canvas_size, canvas_size), (255, 255, 255))

            scaled_img = self.scale_image(original_img)
            blurred_img = self.create_blurred_background(original_img, canvas_size)

            self.apply_edits(canvas, blurred_img, scaled_img, file_path)
        except Exception as e:
            logger.error(f"Failed to process {file_path}: {e}")

    def scale_image(self, image: Image.Image) -> Image.Image:
        """
        Scale the image to fit within the target size, maintaining aspect ratio.
        
        Args:
            image (Image.Image): Original image to be scaled.
        
        Returns:
            Image.Image: Scaled image.
        """
        try:
            img_ratio = min(self.target_size / image.width, self.target_size / image.height)
            new_size = (int(image.width * img_ratio), int(image.height * img_ratio))
            logger.debug(f"Scaling image to {new_size}")
            return image.resize(new_size)
        except Exception as e:
            logger.error(f"Failed to scale image: {e}")
            raise

    def create_blurred_background(self, image: Image.Image, canvas_size : int = 0) -> Image.Image:
        """
        Create a blurred and enhanced version of the image for background.
        
        Args:
            image (Image.Image): Original image to be processed.
        
        Returns:
            Image.Image: Processed background image.
        """
        if not canvas_size:
            canvas_size = self.canvas_size
            
        try:
            logger.debug('Resizing blurred background image')
            blurred_img = image.copy().resize((canvas_size, canvas_size))
            logger.debug('Applying Gaussian blur to background image')
            blurred_img = blurred_img.filter(ImageFilter.GaussianBlur(self.blur_amount))
            
            # Apply brightness and contrast adjustments
            logger.debug('Applying adjustments to background image')
            blurred_img = ImageEnhance.Brightness(blurred_img).enhance(self.brightness_factor)
            blurred_img = ImageEnhance.Contrast(blurred_img).enhance(self.contrast_factor)
            
            # Apply color adjustments
            blurred_img = ImageEnhance.Color(blurred_img).enhance(self.saturation_factor)
            logger.debug('Background image processing complete')
            
            return blurred_img
        except Exception as e:
            logger.error(f"Failed to create blurred background: {e}")
            raise

    def apply_edits(self, canvas: Image.Image, blurred_img: Image.Image, scaled_img: Image.Image, file_path: Path) -> None:
        """
        Apply final edits to the canvas and save the processed image.
        
        Args:
            canvas (Image.Image): Canvas image to place the final edits on.
            blurred_img (Image.Image): Blurred background image.
            scaled_img (Image.Image): Scaled original image.
            file_path (Path): Path of the file being processed.
        """
        try:
            logger.debug('Copying blurred image to canvas')
            canvas.paste(blurred_img, (0, 0))

            logger.debug('Placing scaled image on canvas')
            canvas_size = canvas.width
            x_offset = (canvas_size - scaled_img.width) // 2
            y_offset = (canvas_size - scaled_img.height) // 2
            canvas.paste(scaled_img, (x_offset, y_offset))

            # Add a black border to the scaled image
            logger.debug('Adding border to scaled image')
            border_img = ImageOps.expand(scaled_img, border=4, fill='black').convert("RGB")
            canvas.paste(border_img, (x_offset - self.border_size, y_offset - self.border_size))

            logger.debug('Saving processed image')
            output_path = self.input_dir / f"{file_path.stem}_ig.jpg"
            canvas.save(output_path)
            logger.info(f"Processed image saved as {output_path}")
        except Exception as e:
            logger.error(f"Failed to apply edits: {e}")
            raise

def main() -> None:
    """Main function to parse arguments and start the image processing."""
    parser = argparse.ArgumentParser(description='Process JPG images in a directory.')
    parser.add_argument('input_dir', type=Path, help='Path to the input directory containing JPG images.')
    parser.add_argument('--margin', '-m', type=int, default=100, help='Margin size for the canvas.')
    parser.add_argument('--size', '-s', type=int, default=2160, help='Canvas size for the output images.')
    parser.add_argument('--blur', '-b', type=Decimal, default=10, help='Amount of Gaussian blur to apply.')
    parser.add_argument('--brightness', '-br', type=Decimal, default=1.6, help='Brightness factor for the background.')
    parser.add_argument('--contrast', '-c', type=Decimal, default=0.5, help='Contrast factor for the background.')
    parser.add_argument('--saturation', '-sat', type=Decimal, default=0.85, help='Saturation factor for the background.')
    parser.add_argument('--border', type=int, default=4, help='Border size for the scaled image.')
    parser.add_argument('--suffix', type=str, default='_ig', help='Suffix to add to the processed images.')
    args = parser.parse_args()

    processor = IGImageProcessor(args.input_dir, args.margin, args.size)
    processor.process_images()

if __name__ == "__main__":
    main()