#!/usr/bin/env python3

import argparse
import logging
import sys
from pathlib import Path
import tqdm

import cv2
import numpy as np

logger = logging.getLogger(__name__)

class PaperCropper:
    def __init__(self, input_dir: Path, output_dir: Path):
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def crop_all_images(self):
        image_files = list(self.input_dir.glob("*.jpg")) + \
                      list(self.input_dir.glob("*.jpeg")) + \
                      list(self.input_dir.glob("*.png"))

        if not image_files:
            logger.warning("No images found in input directory.")
            return

        total = len(image_files)

        for img_path in tqdm.tqdm(image_files, desc="Processing images", unit="image", total=total):
            out_path = self.output_dir / img_path.name
            if out_path.exists():
                logger.debug(f"Skipping {img_path}, already exists in output directory.")
                continue
            try:
                cropped = self.crop_image(img_path)
                if cropped is not None:
                    out_path = self.output_dir / img_path.name
                    cv2.imwrite(str(out_path), cropped)
                    logger.info(f"Cropped image saved to {out_path}")
                else:
                    logger.warning(f"Could not crop image {img_path}")
            except Exception as exc:
                logger.error(f"Failed to process {img_path}: {exc}")

    def crop_image(self, img_path: Path) -> np.ndarray | None:
        image = cv2.imread(str(img_path))
        if image is None:
            logger.error(f"Failed to read {img_path}")
            return None

        resized = cv2.resize(image, (0, 0), fx=0.5, fy=0.5)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2
        )
        thresh = cv2.bitwise_not(thresh)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            logger.warning(f"No contours found in {img_path}")
            return None

        h_img, w_img = resized.shape[:2]
        candidate = max(contours, key=cv2.contourArea)
        peri = cv2.arcLength(candidate, True)
        approx = cv2.approxPolyDP(candidate, 0.02 * peri, True)

        if len(approx) < 4:
            logger.warning(f"Not enough points in polygon for {img_path}")
            return None

        # Try using approximated polygon for tighter fit
        peri = cv2.arcLength(candidate, True)
        approx = cv2.approxPolyDP(candidate, 0.015 * peri, True)  # more aggressive than 0.02

        if len(approx) == 4:
            box_points = approx.reshape(4, 2)
        else:
            # fallback to minAreaRect
            box = cv2.minAreaRect(candidate)
            box_points = cv2.boxPoints(box)
            box_points = box_points.astype(np.int32)


        # Scale box points back to full-res image
        scale_x, scale_y = image.shape[1] / resized.shape[1], image.shape[0] / resized.shape[0]
        box_points = np.array([[int(x * scale_x), int(y * scale_y)] for x, y in box_points])

        # Warp the perspective to get a tight crop
        width = int(max(np.linalg.norm(box_points[0] - box_points[1]),
                        np.linalg.norm(box_points[2] - box_points[3])))
        height = int(max(np.linalg.norm(box_points[1] - box_points[2]),
                        np.linalg.norm(box_points[3] - box_points[0])))

        dst_pts = np.array([
            [0, 0],
            [width - 1, 0],
            [width - 1, height - 1],
            [0, height - 1]
        ], dtype="float32")

        # Sort points: top-left, top-right, bottom-right, bottom-left
        def sort_pts(pts):
            s = pts.sum(axis=1)
            diff = np.diff(pts, axis=1)
            return np.array([
                pts[np.argmin(s)],
                pts[np.argmin(diff)],
                pts[np.argmax(s)],
                pts[np.argmax(diff)],
            ])

        sorted_box = sort_pts(box_points).astype("float32")

        M = cv2.getPerspectiveTransform(sorted_box, dst_pts)
        warped = cv2.warpPerspective(image, M, (width, height))

        # Final resize to fixed output size for timelapse consistency
        final_size = (1560, 2502)
        resized = cv2.resize(warped, final_size, interpolation=cv2.INTER_CUBIC)

        return resized




def main():
    parser = argparse.ArgumentParser(description="Crop images around a white paper region.")
    parser.add_argument("input_dir", type=Path, help="Path to directory containing images.")
    parser.add_argument("output_dir", type=Path, help="Path to directory for cropped images.")
    parser.add_argument('--verbose', action='store_true', help="Enable verbose logging.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO if not args.verbose else logging.DEBUG, format="%(levelname)s: %(message)s", handlers=[logging.StreamHandler()])

    cropper = PaperCropper(args.input_dir, args.output_dir)
    cropper.crop_all_images()

    sys.exit(1)

if __name__ == "__main__":
    main()