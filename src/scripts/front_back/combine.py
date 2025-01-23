"""*********************************************************************************************************************
*                                                                                                                      *
*                                                                                                                      *
                    Untested
                    Combines pairs of images in the current directory into individual PDF files.

                    Useful for double-sided documents, or photos with a date written on the back.
*                                                                                                                      *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    METADATA:                                                                                                         *
*                                                                                                                      *
*        File:    combine.py                                                                                           *
*        Project: imageinn                                                                                             *
*        Version: 0.1.0                                                                                                *
*        Created: 2025-01-22                                                                                           *
*        Author:  Jess Mann                                                                                            *
*        Email:   jess.a.mann@gmail.com                                                                                *
*        Copyright (c) 2025 Jess Mann                                                                                  *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    LAST MODIFIED:                                                                                                    *
*                                                                                                                      *
*        2025-01-22     By Jess Mann                                                                                   *
*                                                                                                                      *
*********************************************************************************************************************"""
from pathlib import Path
from PIL import Image
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# I:\Historical\New York\HRSH\Found Photos\pdfs
DIRECTORY = Path("/mnt/i/Historical/New York/HRSH/Found Photos/pdfs")

def combine_images_to_pdf():
    """
    Combine pairs of images in the current directory into individual PDF files.
    The images are combined in the order of their filenames.
    """
    try:
        # Get all image files sorted by filename
        image_extensions = {'.jpg'} #, '.jpeg', '.png', '.bmp', '.tiff', '.webp'}
        files = sorted([f for f in DIRECTORY.iterdir() if f.suffix.lower() in image_extensions])

        if len(files) % 2 != 0:
            logger.warning("The number of images is odd. The last image will be ignored.")

        # Process pairs of images
        for i in range(0, len(files) - 1, 2):
            front_image_path = files[i]
            back_image_path = files[i + 1]
            output_pdf_name = f"document_{i//2 + 1}.pdf"
            output_pdf = DIRECTORY / output_pdf_name

            logger.info(f"Combining {front_image_path.name} and {back_image_path.name} into {output_pdf_name}")

            # Open images
            with Image.open(front_image_path) as front_img, Image.open(back_image_path) as back_img:
                front_img_rgb = front_img.convert("RGB")
                back_img_rgb = back_img.convert("RGB")

                # Save the combined images as a PDF
                front_img_rgb.save(output_pdf, save_all=True, append_images=[back_img_rgb])

        logger.info("All pairs have been processed successfully.")
    except Exception as e:
        logger.error(f"An error occurred: {e}")

if __name__ == "__main__":
    combine_images_to_pdf()