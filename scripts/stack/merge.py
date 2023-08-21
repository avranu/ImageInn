from __future__ import annotations
from typing import List
import re
import logging
import cv2
import numpy as np
import imageio
from skimage import exposure
import rawpy

logger = logging.getLogger(__name__)

class HDRProcessor:
    '''
    Process HDR image from a list of bracketed exposures
    '''
    def __init__(self, exposure_files):
        self.exposure_files = exposure_files
        self.exposures = [self.load_image(file) for file in exposure_files]

        logger.debug("Loaded %d exposures", len(self.exposures))

    @staticmethod
    def load_image(file_path) -> np.ndarray:
        '''
        Load image from file path

        Args:
            file_path: path to the image file

        Returns:
            np.ndarray: loaded image
        '''
        if file_path.endswith(".ARW"):
            with rawpy.imread(file_path) as raw:
                image = raw.postprocess()
                logger.debug("Loaded ARW file %s", file_path)
        else:
            image = imageio.imread(file_path)

        return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

    def align_images(self) -> list[np.ndarray]:
        '''
        Align images using SIFT feature matching and RANSAC
        '''
        sift = cv2.SIFT_create()

        keypoints = [sift.detectAndCompute(exp, None) for exp in self.exposures]
        matcher = cv2.BFMatcher()

        homographies = []
        for i in range(len(self.exposures) - 1):
            matches = matcher.knnMatch(keypoints[i][1], keypoints[i + 1][1], k=2)
            good_matches = [m for m, n in matches if m.distance < 0.75 * n.distance]

            src_pts = np.float32([keypoints[i][0][m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
            dst_pts = np.float32([keypoints[i + 1][0][m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

            H, _ = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
            homographies.append(H)

        aligned_exposures = [self.exposures[0]]
        for i in range(len(homographies)):
            aligned_exp = cv2.warpPerspective(self.exposures[i + 1], np.linalg.inv(homographies[i]),
                                              (self.exposures[0].shape[1], self.exposures[0].shape[0]))
            aligned_exposures.append(aligned_exp)

        logger.debug("Aligned %d exposures", len(aligned_exposures))

        return aligned_exposures

    def merge_images(self, aligned_exposures: list[np.ndarray]) -> np.ndarray:
        '''
        Merge aligned images using simple averaging
        '''
        merged_image = np.zeros_like(aligned_exposures[0], dtype=np.float32)
        for exp in aligned_exposures:
            merged_image += exp.astype(np.float32) / len(aligned_exposures)
        return exposure.rescale_intensity(merged_image, out_range=(0, 255)).astype(np.uint8)

    def process_hdr(self) -> np.ndarray:
        '''
        Process HDR image from a list of bracketed exposures
        '''
        aligned_exposures = self.align_images()
        hdr_image = self.merge_images(aligned_exposures)

        logger.debug("Processed HDR image")
        return hdr_image

    def save_hdr(self, file_path: str) -> str:
        '''
        Save HDR image to file path

        Args:
            file_path: path to the output file
        '''
        hdr_image = self.process_hdr()

        # If no file extension, save as a tiff file
        if not re.search(r"\.[a-zA-Z]+$", file_path):
            file_path += ".tiff"

        imageio.imwrite(file_path, hdr_image)
        #cv2.imwrite(file_path, hdr_image)

        logger.info("Saved HDR image to %s", file_path)

        return file_path

