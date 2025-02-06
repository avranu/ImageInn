"""*********************************************************************************************************************
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    METADATA:                                                                                                         *
*                                                                                                                      *
*        File:    extract_images.py                                                                                    *
*        Project: imageinn                                                                                             *
*        Version: 0.1.0                                                                                                *
*        Created: 2025-02-05                                                                                           *
*        Author:  Jess Mann                                                                                            *
*        Email:   jess.a.mann@gmail.com                                                                                *
*        Copyright (c) 2025 Jess Mann                                                                                  *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    LAST MODIFIED:                                                                                                    *
*                                                                                                                      *
*        2025-02-05     By Jess Mann                                                                                   *
*                                                                                                                      *
*********************************************************************************************************************"""
from __future__ import annotations

import argparse
import io
from pathlib import Path
import sys
import os
import logging
import colorlog
import fitz
import re
from dotenv import load_dotenv
import cv2
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator

from PIL import Image


logger = logging.getLogger(__name__)

class PdfProcessor(BaseModel):
    """
    Extract images from a PDF and rename them based on nearby text.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
    max_threads: int = 0

    @field_validator('max_threads', mode='before')
    def validate_max_threads(cls, value):
        if not value:
            return max(1, min(4, round(os.cpu_count() / 2)))
        if value < 1:
            raise ValueError('max_threads must be a positive integer.')
        return value

    def sanitize_filename(self, text: str, filename_suffix : str | None = None) -> str:
        """
        Convert extracted text into a valid filename.
        """
        # Remove invalid characters
        text = re.sub(r'[^a-zA-Z0-9]+', ' - ', text)
        text = re.sub(r'(^[.\s-]+|[.\s-]+$)', '', text)
        
        # Limit filename length
        max_size = 100
        if filename_suffix:
            max_size -= len(filename_suffix) + 3
            
        text = text.strip()[:max_size]

        if filename_suffix:
            text = f"{text} - {filename_suffix}"

        return text

    def extract_images(self, pdf_path: str | Path, output_dir: Path | str | None = None, filename_suffix : str | None = None) -> None:
        """
        Extracts all images from a PDF and names them based on the nearest text.

        Args:
            pdf_path (str): Path to the PDF file.
            output_dir (str): Directory where extracted images will be saved.

        Returns:
            None
        """
        try:
            pdf_path = Path(pdf_path)
            pdf_directory = pdf_path.parent.absolute()
            output_dir = Path(output_dir) if output_dir else pdf_directory

            if not output_dir.is_absolute():
                output_dir = pdf_directory / output_dir

            pdf_document = fitz.open(str(pdf_path))
            logger.info(f"Opened PDF: {pdf_path}")

            image_count = 0

            for page_num, page in enumerate(pdf_document):
                images = page.get_images(full=True)
                text_blocks = page.get_text("blocks")  # Get text blocks with positions

                for img_index, img in enumerate(images):
                    xref = img[0]
                    base_image = pdf_document.extract_image(xref)
                    image_bytes = base_image["image"]
                    img_ext = base_image["ext"]

                    # Determine image position
                    img_rect = fitz.Rect(page.get_image_rects(xref)[0])

                    # Find the closest text block below the image
                    closest_text = None
                    min_distance = float("inf")

                    for block in text_blocks:
                        x, y, x1, y1, text, *_ = block
                        block_rect = fitz.Rect(x, y, x1, y1)

                        # Ensure the block is below the image
                        if block_rect.y0 > img_rect.y1:
                            distance = block_rect.y0 - img_rect.y1
                            if distance < min_distance:
                                closest_text = text
                                min_distance = distance

                    # Sanitize extracted text for filenames
                    if closest_text:
                        filename = self.sanitize_filename(closest_text, filename_suffix)
                    else:
                        filename = f"page_{page_num + 1}_img_{img_index + 1}"

                    img_filename = output_dir / f"{filename}.{img_ext}"

                    while img_filename.exists():
                        img_filename = img_filename.with_name(f"{filename}_{image_count + 1}.{img_ext}")
                        image_count += 1

                    if img_ext.lower() == "jpx":
                        self.convert_jpx(image_bytes, img_filename)
                    else:
                        with img_filename.open("wb") as img_file:
                            img_file.write(image_bytes)

                    logger.info(f"Saved image: {img_filename}")
                    image_count += 1

            if image_count == 0:
                logger.warning("No images found in the PDF.")
            else:
                logger.info(f"Successfully extracted {image_count} images.")

        except Exception as e:
            logger.error(f"Error processing PDF: {e}")
            raise

    def convert_jpx(self, image_bytes: bytes, image_output: Path):
        """
        Convert a JPX (JPEG 2000) image to a standard JPG using OpenCV.

        Args:
            image_bytes (bytes): The raw JPX image data.
            image_output (Path): The output file path (without extension adjustment).

        Returns:
            None
        """
        try:
            img_array = np.frombuffer(image_bytes, np.uint8)
            image = cv2.imdecode(img_array, cv2.IMREAD_UNCHANGED)  # Load JPX image

            if image is None:
                logger.error(f"Failed to decode JPX image: {image_output}")
                return

            # Change output extension to .jpg
            image_output = image_output.with_suffix(".jpg")

            # Convert to standard RGB format and save as JPG
            cv2.imwrite(str(image_output), image)
            logger.info(f"Converted and saved JPX as JPG: {image_output}")

        except Exception as e:
            logger.error(f"Error converting JPX image: {e}")


def setup_logging():
    logging.basicConfig(level=logging.INFO)

    class CustomFormatter(colorlog.ColoredFormatter):
        def format(self, record):
            self._style._fmt = '(%(log_color)s%(levelname)s%(reset)s) %(message)s'
            return super().format(record)

    handler = colorlog.StreamHandler()
    handler.setFormatter(CustomFormatter(
        '',
        log_colors={
            'DEBUG': 'green',
            'INFO': 'blue',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'red,bg_white',
        }
    ))

    root_logger = logging.getLogger()
    root_logger.handlers = []
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)

    return root_logger


class ArgNamespace(argparse.Namespace):
    """
    A custom namespace class for argparse.
    """
    pdf_path: Path
    output_dir: Path | None = None
    filename_suffix : str | None = None


def main():
    try:
        logger = setup_logging()
        load_dotenv()

        parser = argparse.ArgumentParser(description="Extract images from a PDF and name them based on nearby text.")
        parser.add_argument('pdf_path', type=Path, help="Path to the PDF file.")
        parser.add_argument('--output-dir', '-o', type=Path, help="Directory where extracted images will be saved.")
        parser.add_argument('--filename-sufffix', '-s', type=str, help="Suffix to append to extracted image filenames.")
        parser.add_argument('--verbose', '-v', action='store_true', help="Verbose output")

        args = parser.parse_args(namespace=ArgNamespace())

        if args.verbose:
            logger.setLevel(logging.DEBUG)

        processor = PdfProcessor()
        processor.extract_images(args.pdf_path, args.output_dir, args.filename_suffix)

    except KeyboardInterrupt:
        logger.info("Script cancelled by user.")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
