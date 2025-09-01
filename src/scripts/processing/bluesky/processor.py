from __future__ import annotations

import argparse
import logging
import os
import subprocess
from pathlib import Path
from decimal import Decimal
from typing import Literal

from PIL import Image, ImageEnhance
import numpy as np
from pydantic import Field, PrivateAttr, field_validator
from tqdm import tqdm

from scripts.lib.file_manager import FileManager
from scripts.lib.types import Number
from scripts.processing.meta import (
    AdjustmentTypes,
    to_windows_path,
    DEFAULT_TOPAZ_PATH,
)
from scripts.processing.bluesky.image import BlueskyImage

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class BlueskyProcessor(FileManager):
    """Process images for Bluesky posts (no borders/canvas; enforce file-size cap)."""

    input_dir: Path
    output_folder: str = "processed"
    # Image adjustments
    skip_image_adjustments: bool = Field(default=False)
    brightness_factor: Number = Field(default=1.0)
    contrast_factor: Number = Field(default=1.0)
    saturation_factor: Number = Field(default=1.0)
    # Bluesky constraints / output
    max_bytes: int = Field(default=1_000_000, ge=10_000)  # 1MB
    output_format: Literal["jpeg", "webp"] = Field(default="jpeg")
    file_suffix: str = Field(default="_bsky")
    # Optional Topaz
    topaz_exe: Path | None = Field(default=DEFAULT_TOPAZ_PATH)
    topaz_output_dir: Path | None = Field(default=None)
    # Aspect ratio handling
    ratio: Literal["auto", "1:1", "4:5", "16:9"] = Field(default="auto")
    # Safety / runtime
    max_errors: int = Field(default=10)

    _progress_bar: tqdm | None = PrivateAttr(default=None)
    _topaz_available: bool | None = PrivateAttr(default=None)

    @field_validator("input_dir", mode="before")
    def _val_input_dir(cls, v):
        return Path(v) if v else None

    @field_validator("topaz_exe", mode="before")
    def _val_topaz_exe(cls, v):
        return Path(v) if v else None

    @field_validator("topaz_output_dir", mode="before")
    def _val_topaz_output_dir(cls, v):
        return Path(v) if v else None

    @property
    def progress_bar(self) -> tqdm | None:
        return self._progress_bar

    @property
    def topaz_available(self) -> bool:
        if self._topaz_available is None:
            self._topaz_available = bool(self.topaz_exe and self.topaz_exe.exists())
            logger.debug("Topaz available: %s", self._topaz_available)
        return self._topaz_available

    @property
    def output_dir(self) -> Path:
        if self.input_dir.is_file():
            return self.input_dir.parent / self.output_folder
        return self.input_dir / self.output_folder

    def _get_images(self) -> list[Path]:
        if not self.input_dir.is_dir():
            return [self.input_dir]
        globs = ["*.jpg", "*.jpeg", "*.png", "*.webp", "*.tif", "*.tiff", "*.heic", "*.heif"]
        files: list[Path] = []
        for glob in globs:
            files.extend([p for p in self.input_dir.glob(glob) if p.is_file()])
        return files

    def get_file_suffix(self) -> str:
        return f"{self.file_suffix}.{self.output_format}"

    def check_if_processed(self, image_path: Path) -> bool:
        for image in self.output_dir.glob(f"{image_path.stem}*{self.get_file_suffix()}"):
            if image.is_file():
                return True
        return False

    def get_topaz_dir(self) -> Path:
        if not self.topaz_output_dir:
            self.topaz_output_dir = self.input_dir / "topaz"
        self.topaz_output_dir.mkdir(exist_ok=True)
        return self.topaz_output_dir

    def cleanup_topaz_output(self) -> bool:
        if not self.topaz_output_dir:
            return True
        try:
            for file in self.topaz_output_dir.glob("*"):
                file.unlink()
            self.topaz_output_dir.rmdir()
        except Exception as exc:
            logger.warning("Failed to cleanup Topaz dir: %s", exc)
            return False
        return True

    def update_progress(self, description: str | None = None) -> None:
        if not self.progress_bar:
            logger.error("Progress bar not initialized")
            return
        if description:
            self.progress_bar.set_description(description)
            logger.debug(description)
        else:
            self.progress_bar.update(1)

    def process_images(self) -> None:
        images = self._get_images()
        total = len(images)

        try:
            self.output_dir.mkdir(exist_ok=True)
            if not self.skip_image_adjustments and self.topaz_available:
                logger.info('Topaz is available and will be applied.')
                total *= 2  # extra steps when Topaz is used
                self.get_topaz_dir()
            else:
                logger.info('Skipping topaz adjustments.')

            processed = 0
            errors = 0
            with tqdm(total=total, desc=f"Processing {len(images)} images") as self._progress_bar:
                for file_path in images:
                    try:
                        if self.check_if_processed(file_path):
                            logger.debug("Skipping already processed: %s", file_path.name)
                            continue
                        self.process_image(file_path)
                        processed += 1
                    except Exception as exc:
                        logger.error("Failed to process %s: %s", file_path, exc)
                        errors += 1
                        if errors >= self.max_errors:
                            logger.error("Reached max errors (%s). Stopping.", self.max_errors)
                            break
                    finally:
                        self.update_progress()
            logger.info("Processed %s images", processed)
        finally:
            self.cleanup_topaz_output()

    def process_image(self, file_path: Path) -> None:
        self.update_progress(f"Opening: {file_path.name}")

        # Optional Topaz pass first (works best on source)
        topaz_file_path = None
        if not self.skip_image_adjustments and self.topaz_available:
            if topaz_file_path := self.apply_topaz(file_path):
                file_path = topaz_file_path

        image = self.create_image(file_path)
        image.setup()  # open, optional crop, optional adjustments

        if topaz_file_path:
            image.adjustments_applied(AdjustmentTypes.TOPAZ)

        self.update_progress(f"Saving: {image.output_path.name}")
        image.save(max_bytes=self.max_bytes, output_format=self.output_format)

        if topaz_file_path:
            self.update_progress(f"Cleaning Topaz: {topaz_file_path.name}")
            try:
                topaz_file_path.unlink()
            except Exception as exc:
                logger.warning("Failed to remove temp Topaz file: %s", exc)

    def create_image(self, file_path: Path) -> BlueskyImage:
        return BlueskyImage(
            file_path=file_path,
            processor=self,
            crop_ratio=self.ratio,
            output_dir=self.output_dir,
        )

    def apply_topaz(self, image_path: Path, timeout: int = 300) -> Path | None:
        """Run Topaz Photo AI CLI on an image."""
        if not self.topaz_available:
            return None
        if image_path.stem.endswith("-topaz"):
            return None

        self.update_progress(f"Topaz: {image_path.name}")

        input_path = to_windows_path(image_path)
        output_path = to_windows_path(self.get_topaz_dir())
        cmd = [str(self.topaz_exe), input_path, "--output", output_path]
        logger.debug("Running Topaz command: %s", cmd)
        subprocess.run(cmd, capture_output=True, check=True, timeout=timeout)

        topaz_output = self.get_topaz_dir() / image_path.name
        if not topaz_output.exists():
            logger.error("Topaz output not found: %s", topaz_output)
            return None

        new_path = image_path.parent / f"{image_path.stem}-topaz.jpg"
        topaz_output.rename(new_path)
        return new_path

    # Simple histogram-based tweaks (optional)
    def adjust_image(self, pil_image: Image.Image) -> Image.Image:
        if self.skip_image_adjustments:
            return pil_image

        hsv_img = pil_image.convert("HSV")
        _, s, v = hsv_img.split()
        mean_saturation = float(np.mean(np.array(s)))
        mean_luminance = float(np.mean(np.array(v)))

        out = pil_image
        if mean_saturation > 200:
            out = ImageEnhance.Color(out).enhance(0.8)
        if mean_luminance < 45:
            out = ImageEnhance.Brightness(out).enhance(1.15)
        elif mean_luminance > 210:
            out = ImageEnhance.Brightness(out).enhance(0.85)

        # User-tunable global factors
        if self.brightness_factor != 1.0:
            out = ImageEnhance.Brightness(out).enhance(float(self.brightness_factor))
        if self.contrast_factor != 1.0:
            out = ImageEnhance.Contrast(out).enhance(float(self.contrast_factor))
        if self.saturation_factor != 1.0:
            out = ImageEnhance.Color(out).enhance(float(self.saturation_factor))
        return out


class ArgNamespace(argparse.Namespace):
    input_dir: Path
    ratio: str
    max_bytes: int
    output_format: str
    skip_adjustments: bool
    topaz_exe: Path
    brightness: Decimal
    contrast: Decimal
    saturation: Decimal
    verbose: bool

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.input_dir = Path(self.input_dir)
        self.topaz_exe = Path(self.topaz_exe)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Bluesky Image Processor.\n"
            "No borders/canvas. Optional aspect-ratio crop. Enforces ≤ 1,000,000 bytes."
        )
    )
    parser.add_argument("input_dir", type=Path, nargs="?", default=".", help="Input file or directory.")
    parser.add_argument(
        "--ratio",
        type=str,
        default="auto",
        choices=["auto", "1:1", "4:5", "16:9"],
        help="Target aspect ratio (center-crop). Default keeps original.",
    )
    parser.add_argument(
        "--output-format",
        type=str,
        default="jpeg",
        choices=["jpeg", "webp"],
        help="Final image format. JPEG is safest for ≤1MB.",
    )
    parser.add_argument("--max-bytes", type=int, default=1_000_000, help="Max output size in bytes (default 1,000,000).")
    parser.add_argument("--suffix", type=str, default="_bsky", help="Suffix for output images.")
    parser.add_argument("--skip-adjustments", action="store_true", help="Disable histogram/global tweaks.")
    parser.add_argument("--topaz-exe", type=Path, default=DEFAULT_TOPAZ_PATH, help="Path to Topaz Photo AI executable.")
    parser.add_argument("--brightness", type=Decimal, default=1.0, help="Global brightness factor.")
    parser.add_argument("--contrast", type=Decimal, default=1.0, help="Global contrast factor.")
    parser.add_argument("--saturation", type=Decimal, default=1.0, help="Global saturation factor.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging.")
    args = parser.parse_args(namespace=ArgNamespace)

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    processor = BlueskyProcessor(
        input_dir=args.input_dir,
        ratio=args.ratio,
        output_format=args.output_format,
        max_bytes=args.max_bytes,
        file_suffix=args.suffix,
        skip_image_adjustments=args.skip_adjustments,
        topaz_exe=args.topaz_exe,
        brightness_factor=args.brightness,
        contrast_factor=args.contrast,
        saturation_factor=args.saturation,
    )
    processor.process_images()


if __name__ == "__main__":
    main()
