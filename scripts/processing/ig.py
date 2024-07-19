import logging
from pathlib import Path
from PIL import Image, ImageFilter, ImageEnhance, ImageOps
import argparse
from typing import Tuple

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class IGImageProcessor:
    def __init__(self, input_dir: Path):
        """
        Initialize the ImageProcessor with the input directory.
        
        Args:
            input_dir (Path): Path to the directory containing the input images.
        """
        self.input_dir = input_dir
        self.canvas_size = 2160
        self.margin = 50
        self.target_size = self.canvas_size - 2 * self.margin

    def process_images(self) -> None:
        """
        Process all JPG images in the input directory.
        """
        for file_path in self.input_dir.glob('*.jpg'):
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
            logger.debug('Creating canvas')
            canvas = Image.new('RGB', (self.canvas_size, self.canvas_size), (255, 255, 255))

            scaled_img = self.scale_image(original_img)
            blurred_img = self.create_blurred_background(original_img)

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

    def create_blurred_background(self, image: Image.Image) -> Image.Image:
        """
        Create a blurred and enhanced version of the image for background.
        
        Args:
            image (Image.Image): Original image to be processed.
        
        Returns:
            Image.Image: Processed background image.
        """
        try:
            logger.debug('Resizing blurred background image')
            blurred_img = image.copy().resize((self.canvas_size, self.canvas_size))
            logger.debug('Applying Gaussian blur to background image')
            blurred_img = blurred_img.filter(ImageFilter.GaussianBlur(10))
            
            # Apply brightness and contrast adjustments
            logger.debug('Applying adjustments to background image')
            blurred_img = ImageEnhance.Brightness(blurred_img).enhance(1.6)
            blurred_img = ImageEnhance.Contrast(blurred_img).enhance(0.5)
            
            # Apply color adjustments
            blurred_img = ImageEnhance.Color(blurred_img).enhance(0.85)
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
            x_offset = (self.canvas_size - scaled_img.width) // 2
            y_offset = (self.canvas_size - scaled_img.height) // 2
            canvas.paste(scaled_img, (x_offset, y_offset))

            # Add a black border to the scaled image
            logger.debug('Adding border to scaled image')
            border_img = ImageOps.expand(scaled_img, border=4, fill='black')
            canvas.paste(border_img, (x_offset - 4, y_offset - 4), border_img)

            logger.debug('Saving processed image')
            output_path = self.input_dir / f"processed_{file_path.name}"
            canvas.save(output_path)
            logger.info(f"Processed image saved as {output_path}")
        except Exception as e:
            logger.error(f"Failed to apply edits: {e}")
            raise

def main() -> None:
    """Main function to parse arguments and start the image processing."""
    parser = argparse.ArgumentParser(description='Process JPG images in a directory.')
    parser.add_argument('input_dir', type=Path, help='Path to the input directory containing JPG images.')
    args = parser.parse_args()

    processor = IGImageProcessor(args.input_dir)
    processor.process_images()

if __name__ == "__main__":
    main()