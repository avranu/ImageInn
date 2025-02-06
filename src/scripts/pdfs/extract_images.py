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
from pathlib import Path
import sys
import os
import logging
import colorlog
from alive_progress import alive_it, alive_bar
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator
import fitz

logger = logging.getLogger(__name__)

class PdfProcessor(BaseModel):
    """
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
    max_threads : int = 0
    
    @field_validator('max_threads', mode='before')
    def validate_max_threads(cls, value):
        # Sensible default
        if not value:
            # default is between 1-4 threads. More than 4 presumptively stresses the HDD non-optimally.
            return max(1, min(4, round(os.cpu_count() / 2)))
            
        if value < 1:
            raise ValueError('max_threads must be a positive integer.')
        return value


    def extract_images(self, pdf_path: str | Path, output_dir: Path | str | None = None) -> None:
        """
        Extracts all images from a PDF and saves them as separate image files.

        Args:
            pdf_path (str): Path to the PDF file.
            output_dir (str): Directory where extracted images will be saved.

        Returns:
            None
        """
        try:
            # Normalize Path objects
            pdf_path = Path(pdf_path)
            pdf_directory = Path(pdf_path).parent.absolute()
            if output_dir:
                output_dir = Path(output_dir)
            else:
                output_dir = pdf_directory

            if not output_dir.is_absolute():
                output_dir = pdf_directory / output_dir
            
            # Open the PDF file
            pdf_document = fitz.open(str(pdf_path))
            logger.info(f"Opened PDF: {pdf_path}")

            image_count = 0

            for page_num, page in enumerate(pdf_document):
                images = page.get_images(full=True)

                for img_index, img in enumerate(images):
                    xref = img[0]
                    base_image = pdf_document.extract_image(xref)
                    image_bytes = base_image["image"]
                    img_ext = base_image["ext"]

                    # Create output filename
                    img_filename = output_dir / f"page_{page_num + 1}_img_{img_index + 1}.{img_ext}"

                    # Save image
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


def setup_logging():

    logging.basicConfig(level=logging.INFO)

    # Define a custom formatter class
    class CustomFormatter(colorlog.ColoredFormatter):
        def format(self, record):
            self._style._fmt = '(%(log_color)s%(levelname)s%(reset)s) %(message)s'
            return super().format(record)

    # Configure colored logging with the custom formatter
    handler = colorlog.StreamHandler()
    handler.setFormatter(CustomFormatter(
        # Initial format string (will be overridden in the formatter)
        '',
        log_colors={
            'DEBUG':    'green',
            'INFO':     'blue',
            'WARNING':  'yellow',
            'ERROR':    'red',
            'CRITICAL': 'red,bg_white',
        }
    ))

    root_logger = logging.getLogger()
    root_logger.handlers = []  # Clear existing handlers
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)

    return root_logger

class ArgNamespace(argparse.Namespace):
    """
    A custom namespace class for argparse.
    """
    pdf_path : Path
    output_dir : Path | None = None


def main():
    try:
        logger = setup_logging()
        load_dotenv()

        parser = argparse.ArgumentParser(description="")
        parser.add_argument('pdf_path', type=Path, help="Path to the PDF file.")
        parser.add_argument('--output-dir', '-o', type=Path, help="Directory where extracted images will be saved.")
        parser.add_argument('--verbose', '-v', action='store_true', help="Verbose output")

        args = parser.parse_args(namespace=ArgNamespace())

        if args.verbose:
            logger.setLevel(logging.DEBUG)

        processor = PdfProcessor()
        processor.extract_images(args.pdf_path, args.output_dir)
   
    except KeyboardInterrupt:
        logger.info("Script cancelled by user.")
        sys.exit(1)

    sys.exit(0)

if __name__ == "__main__":
    main()