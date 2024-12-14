"""*********************************************************************************************************************
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    METADATA:                                                                                                         *
*                                                                                                                      *
*        File:    topaz.py                                                                                             *
*        Project: imageinn                                                                                             *
*        Version: 0.1.0                                                                                                *
*        Created: 2024-12-13                                                                                           *
*        Author:  Jess Mann                                                                                            *
*        Email:   jess.a.mann@gmail.com                                                                                *
*        Copyright (c) 2024 Jess Mann                                                                                  *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    LAST MODIFIED:                                                                                                    *
*                                                                                                                      *
*        2024-12-13     By Jess Mann                                                                                   *
*                                                                                                                      *
*********************************************************************************************************************"""
from __future__ import annotations
from pathlib import Path
import subprocess
import logging
from tqdm import tqdm
import argparse
from scripts.processing.meta import DEFAULT_TOPAZ_PATH

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_SUFFIX = "-topaz"
DEFAULT_TIMEOUT = 300
DEFAULT_IMAGE_EXTENSIONS = ["*.jpg", "*.jpeg", "*.png"]

class TopazProcessor:
    """
    A class to process images using Topaz DeNoise AI.

    Attributes:
        directory (Path): Directory containing images to process.
        topaz_exe (Path): Path to the Topaz executable.
        output_suffix (str): Suffix to add to the output files.
        timeout (int): Timeout for the Topaz subprocess.
    """

    def __init__(
        self,
        directory: Path,
        topaz_exe: Path = DEFAULT_TOPAZ_PATH,
        output_suffix: str = DEFAULT_OUTPUT_SUFFIX,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.directory = directory
        self.topaz_exe = topaz_exe
        self.output_suffix = output_suffix
        self.timeout = timeout

    def apply_topaz(self, image_path: Path) -> Path | None:
        """
        Apply Topaz DeNoise AI to an image.

        Args:
            image_path (Path): Path to the image to process.

        Returns:
            Optional[Path]: Path to the processed image or None if processing fails.
        """
        output_path = image_path.with_name(f"{image_path.stem}{self.output_suffix}{image_path.suffix}")

        if output_path.exists():
            logger.warning(f"Output file already exists, skipping: {output_path}")
            return output_path

        cmd = [str(self.topaz_exe), str(image_path), "--output", str(output_path.parent)]
        logger.info(f"Running Topaz on {image_path}")
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=self.timeout)
        except subprocess.CalledProcessError as e:
            logger.error(f"Topaz failed for {image_path}: {e.stderr.decode()}")
            return None

        if not output_path.exists():
            logger.error(f"Topaz output file not created: {output_path}")
            return None

        return output_path

    def process_images(self):
        """
        Process all images in the directory using Topaz.
        """
        if not self.topaz_exe.exists():
            raise FileNotFoundError(f"Topaz executable not found at {self.topaz_exe}")

        images : list[Path] = []
        for ext in DEFAULT_IMAGE_EXTENSIONS:
            images.extend(self.directory.glob(ext))

        if not images:
            logger.warning("No supported images found in the directory.")
            return

        logger.info(f"Found {len(images)} images to process.")

        with tqdm(total=len(images), desc="Processing images") as pbar:
            for image in images:
                # If the image has the output suffix, skip it
                if self.output_suffix in image.stem:
                    pbar.update(1)
                    continue
                
                try:
                    self.apply_topaz(image)
                except Exception as e:
                    logger.error(f"Failed to process {image}: {e}")
                pbar.update(1)

class TopazArgNamespace(argparse.Namespace):
	"""
	A custom namespace class for the TopazProcessor argument parser.
	"""

	directory: Path
	topaz_exe: Path
	output_suffix: str
	timeout: int
    
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch process images with Topaz.")
    parser.add_argument("directory",        type=Path,                                help="Directory containing images to process.")
    parser.add_argument("--topaz-exe",      type=Path, default=DEFAULT_TOPAZ_PATH,    help=f"Path to the Topaz executable. On this machine, defaults to {DEFAULT_TOPAZ_PATH}")
    parser.add_argument("--output-suffix",  type=str,  default=DEFAULT_OUTPUT_SUFFIX, help=f"Suffix to add to the output files. Defaults to {DEFAULT_OUTPUT_SUFFIX}")
    parser.add_argument("--timeout",        type=int,  default=DEFAULT_TIMEOUT,       help=f"Timeout for the Topaz subprocess in seconds. Defaults to {DEFAULT_TIMEOUT}")

    args = parser.parse_args(namespace=TopazArgNamespace())

    processor = TopazProcessor(
        directory=args.directory,
        topaz_exe=args.topaz_exe,
        output_suffix=args.output_suffix,
        timeout=args.timeout,
    )
    processor.process_images()
