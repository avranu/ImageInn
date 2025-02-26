"""*********************************************************************************************************************
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    METADATA:                                                                                                         *
*                                                                                                                      *
*        File:    split.py                                                                                             *
*        Project: imageinn                                                                                             *
*        Version: 0.1.0                                                                                                *
*        Created: 2025-02-25                                                                                           *
*        Author:  Jess Mann                                                                                            *
*        Email:   jess.a.mann@gmail.com                                                                                *
*        Copyright (c) 2025 Jess Mann                                                                                  *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    LAST MODIFIED:                                                                                                    *
*                                                                                                                      *
*        2025-02-25     By Jess Mann                                                                                   *
*                                                                                                                      *
*********************************************************************************************************************"""
import argparse
import cv2
import numpy as np
from pathlib import Path
from PIL import Image
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# I:\Historical\New York\HRSH\HRSH Box of Photos\4800

class TiffSplitter:
    """Splits a TIFF file containing a grid of images into separate image files."""

    def __init__(self, input_path: Path, output_dir: Path):
        self.input_path = Path(input_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def process(self):
        """Processes the TIFF file and extracts individual images."""
        logger.info(f"Processing: {self.input_path}")
        image = cv2.imread(str(self.input_path), cv2.IMREAD_GRAYSCALE)

        if image is None:
            logger.error(f"Failed to load image: {self.input_path}")
            return

        contours = self.detect_grid(image)
        self.extract_and_save(image, contours)

    def detect_grid(self, image):
        """Detects grid lines and finds individual image contours."""
        logger.info("Detecting grid structure...")

        # Edge detection and thresholding
        blurred = cv2.GaussianBlur(image, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Filter contours to keep only those of reasonable size
        contours = [c for c in contours if cv2.contourArea(c) > 5000]
        contours = sorted(contours, key=lambda c: cv2.boundingRect(c)[1])  # Sort by vertical position

        logger.info(f"Found {len(contours)} individual images.")
        return contours

    def extract_and_save(self, image, contours):
        """Crops and saves individual images."""
        for i, contour in enumerate(contours):
            x, y, w, h = cv2.boundingRect(contour)
            cropped = image[y : y + h, x : x + w]
            output_path = self.output_dir / f"{self.input_path.stem}_part_{i+1}.png"
            cv2.imwrite(str(output_path), cropped)
            logger.info(f"Saved: {output_path}")

class ArgNamespace(argparse.Namespace):
    input : str = '.'
    verbose : bool

def main():
    parser = argparse.ArgumentParser(description="Fetch documents with a specific tag from Paperless NGX.")
    parser.add_argument('--input', default='.', type=str, help="The input dir")        
    parser.add_argument('--verbose', '-v', action='store_true', help="Verbose output")
        
    args = parser.parse_args(namespace=ArgNamespace())

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    input_folder = Path(args.input)
    output_folder =  input_folder / "split"

    for tiff_file in input_folder.glob("*.tif"):
        splitter = TiffSplitter(tiff_file, output_folder)
        splitter.process()

if __name__ == "__main__":
    main()

