import logging
import cv2
from merge import HDRProcessor

logger = logging.getLogger(__name__)

if __name__ == "__main__":

    logger.info("Starting HDR processing")

    # Initialize the HDRProcessor with exposure files
    hdr_processor = HDRProcessor(["images/exposure1.ARW", "images/exposure2.ARW", "images/exposure3.ARW"])

    # Process the HDR image
    hdr_image = hdr_processor.save_hdr("hdr_image.jpg")

    logger.info("Finished HDR processing")