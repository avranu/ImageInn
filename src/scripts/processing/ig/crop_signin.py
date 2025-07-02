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
        h_img, w_img = resized.shape[:2]
        scale_x, scale_y = image.shape[1] / w_img, image.shape[0] / h_img

        # Adaptive threshold to isolate bright regions (paper)
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 11, 10
        )
        thresh = cv2.bitwise_not(thresh)  # paper becomes white

        # Clean up with morphological closing
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
        closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            logger.warning(f"No contours found in {img_path}")
            return None

        contours = sorted(contours, key=cv2.contourArea, reverse=True)
        sheet_corners = None

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 0.1 * (w_img * h_img):
                continue

            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
            if len(approx) == 4:
                corners = np.array([[int(x * scale_x), int(y * scale_y)] for [x, y] in approx.reshape(4, 2)], dtype="float32")

                # Check aspect ratio
                width = np.linalg.norm(corners[0] - corners[1])
                height = np.linalg.norm(corners[1] - corners[2])
                ratio = height / width if width > 0 else 0

                if 1.2 < ratio < 2.5:
                    sheet_corners = corners
                    break

        if sheet_corners is None:
            logger.warning(f"Primary 4-point page detection failed in {img_path}, attempting fallback.")

            candidate = max(contours, key=cv2.contourArea)
            box = cv2.minAreaRect(candidate)
            box_points = cv2.boxPoints(box).astype(np.float32)
            box_points *= np.array([scale_x, scale_y], dtype=np.float32)

            # Validate fallback shape
            w = np.linalg.norm(box_points[0] - box_points[1])
            h = np.linalg.norm(box_points[1] - box_points[2])
            aspect = h / w if w > 0 else 0
            area = w * h
            min_area = image.shape[0] * image.shape[1] * 0.05

            if 1.2 < aspect < 2.5 and area > min_area:
                sheet_corners = box_points
                logger.debug(f"Fallback bounding box used for {img_path}")
            else:
                logger.warning(f"Fallback also failed for {img_path} (aspect={aspect:.2f}, area={area:.0f})")
                return None


        # Order corners: TL, TR, BR, BL
        def order_points(pts):
            s = pts.sum(axis=1)
            diff = np.diff(pts, axis=1)
            return np.array([
                pts[np.argmin(s)],
                pts[np.argmin(diff)],
                pts[np.argmax(s)],
                pts[np.argmax(diff)]
            ], dtype="float32")

        src_pts = order_points(sheet_corners)
        dst_pts = np.array([
            [0, 0],
            [1559, 0],
            [1559, 2501],
            [0, 2501]
        ], dtype="float32")

        M = cv2.getPerspectiveTransform(src_pts, dst_pts)
        warped = cv2.warpPerspective(image, M, (1560, 2502))

        return warped


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