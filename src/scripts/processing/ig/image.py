"""*********************************************************************************************************************
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    METADATA:                                                                                                         *
*                                                                                                                      *
*        File:    image.py                                                                                             *
*        Project: imageinn                                                                                             *
*        Version: 0.1.0                                                                                                *
*        Created: 2024-07-20                                                                                           *
*        Author:  Jess Mann                                                                                            *
*        Email:   jess.a.mann@gmail.com                                                                                *
*        Copyright (c) 2025 Jess Mann                                                                                  *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    LAST MODIFIED:                                                                                                    *
*                                                                                                                      *
*        2025-01-30     By Jess Mann                                                                                   *
*                                                                                                                      *
*********************************************************************************************************************"""
from __future__ import annotations
import logging
from pathlib import Path
from typing import TYPE_CHECKING
from PIL import Image, ImageOps
from dataclasses import dataclass, field
from scripts.processing.meta import AdjustmentTypes

if TYPE_CHECKING:
    from scripts.processing.ig.processor import IGImageProcessor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class IGImage:
    file_path: Path
    processor: IGImageProcessor
    canvas_size: tuple[int, int] = field(init=False)
    margin: int = field(init=False)
    border_size: int = field(init=False)
    _output_suffix: str = field(init=False)
    _adjustments: list[AdjustmentTypes] = field(default_factory=list)
    _original: Image.Image | None = field(init=False, default=None)
    _scaled: Image.Image | None = field(init=False, default=None)
    _blurred: Image.Image | None = field(init=False, default=None)
    _canvas: Image.Image | None = field(init=False, default=None)
    output_dir : Path | None = None

    def __post_init__(self):
        self._output_suffix = self.processor.file_suffix
        # processor might define a default 1080x1350 or something else
        # For best IG results, we default to double 1080x1350 unless changed
        self.canvas_size = (2160, 2700)
        self.margin = self.processor.margin
        self.border_size = self.processor.border_size
        self.open_image()
        self.recalculate_canvas_size()

    @property
    def target_size(self) -> tuple[int, int]:
        """Max area inside the margin for the scaled image."""
        w, h = self.canvas_size
        return (w - 2 * self.margin, h - 2 * self.margin)

    @property
    def output_path(self) -> Path:
        folder = self.output_dir or self.file_path.parent
        return folder / f"{self.file_path.stem}{self.output_suffix}.jpg"

    @property
    def original(self) -> Image.Image:
        if not self._original:
            return self.open_image()
        return self._original

    @property
    def canvas(self) -> Image.Image:
        if not self._canvas:
            return self.setup_canvas()
        return self._canvas

    @property
    def scaled(self) -> Image.Image:
        if not self._scaled:
            return self.scale_image()
        return self._scaled

    @scaled.setter
    def scaled(self, value: Image.Image) -> None:
        self._scaled = value

    @property
    def blurred(self) -> Image.Image:
        if not self._blurred:
            return self.create_blurred_background()
        return self._blurred

    @property
    def output_suffix(self) -> str:
        if self.adjustments_applied:
            tags = '-'.join([adj.value for adj in self._adjustments])
            return f'adj-{tags}-{self._output_suffix}'
        return self._output_suffix

    def setup(self):
        self.scale_image()
        self.create_blurred_background()
        self.adjust_image()

    def open_image(self) -> Image.Image:
        self._original = Image.open(self.file_path)
        return self._original

    def recalculate_canvas_size(self) -> None:
        """
        Optionally adjust the final canvas or margin based on image size.
        Keeps final ratio at 4:5 (e.g. 1080x1350) but can reduce margins if the image is very small.
        """
        base_w, base_h = self.canvas_size
        # If original is very small, reduce margin/border to avoid overwhelming the image
        if max(self.original.width, self.original.height) < min(base_w, base_h):
            self.margin = max(50, self.margin // 2)
            self.border_size = max(4, self.border_size // 2)

    def scale_image(self) -> Image.Image:
        """
        Scale image to fit within (canvas_width - 2*margin) x (canvas_height - 2*margin).
        Maintains original aspect ratio.
        """
        tw, th = self.target_size
        ratio = min(tw / self.original.width, th / self.original.height)
        new_w = int(self.original.width * ratio)
        new_h = int(self.original.height * ratio)
        logger.debug("Scaling image to %s x %s", new_w, new_h)
        self._scaled = self.original.resize((new_w, new_h), Image.LANCZOS)
        return self._scaled

    def create_blurred_background(self) -> Image.Image:
        """
        Create a blurred background that covers the full 4:5 image (or final canvas_size).
        """
        final_w, final_h = self.canvas_size
        # Scale original so it's at least as large as the canvas in both dimensions
        ratio = max(final_w / self.original.width, final_h / self.original.height)
        new_w = int(self.original.width * ratio)
        new_h = int(self.original.height * ratio)
        logger.debug("Creating blurred background sized %s x %s", new_w, new_h)
        self._blurred = self.processor.create_blurred_background(self.original, (new_w, new_h))
        return self._blurred

    def setup_canvas(self) -> Image.Image:
        """
        Centers the scaled image over a blurred background on a 4:5 canvas.
        """
        final_w, final_h = self.canvas_size
        logger.debug('Creating canvas')
        self._canvas = Image.new('RGB', (final_w, final_h), (255, 255, 255))

        logger.debug('Placing blurred image')
        self._canvas.paste(self.blurred, (0, 0))

        logger.debug('Placing scaled image')
        x_offset = (final_w - self.scaled.width) // 2
        y_offset = (final_h - self.scaled.height) // 2

        # Optional border
        bordered_scaled = ImageOps.expand(self.scaled, self.border_size, fill='black')
        self._canvas.paste(bordered_scaled, (x_offset - self.border_size, y_offset - self.border_size))

        return self._canvas

    def adjust_image(self):
        return self.processor.adjust_image(self)

    def adjustments_applied(self, adjustment_type: AdjustmentTypes = AdjustmentTypes.BASIC):
        if adjustment_type not in self._adjustments:
            self._adjustments.append(adjustment_type)

    def save(self) -> Path:
        if not self.canvas:
            raise ValueError("Canvas not created. Run apply_edits() first.")

        logger.debug('Saving processed image')
        if self.output_path.exists():
            logger.debug(f"Overwriting processed image: {self.output_path}")

        self.canvas.save(self.output_path)
        logger.debug(f"Processed image saved as {self.output_path}")
        return self.output_path
