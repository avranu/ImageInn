from __future__ import annotations
import logging
from pathlib import Path
from typing import TYPE_CHECKING
from PIL import Image, ImageOps
from dataclasses import dataclass, field
from scripts.processing.ig.meta import (
    AdjustmentTypes
)

if TYPE_CHECKING:
    from scripts.processing.ig.processor import IGImageProcessor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class IGImage:
    """
    Stores data about the image we are processing, including the original image,
    the scaled image, the blurred image, the canvas size, margins, and so on.
    """
    file_path : Path
    processor : IGImageProcessor
    canvas_size: int = field(init=False)
    margin: int = field(init=False)
    border_size : int = field(init=False)
    _output_suffix : str = field(init=False)
    _adjustments : list[AdjustmentTypes] = field(default_factory=list)
    _original: Image.Image | None = field(init=False, default=None)
    _scaled: Image.Image | None = field(init=False, default=None)
    _blurred: Image.Image | None = field(init=False, default=None)
    _canvas : Image.Image | None = field(init=False, default=None)

    def __post_init__(self):
        # Copy over default attribs
        self._output_suffix = self.processor.file_suffix
        self.canvas_size = self.processor.canvas_size
        self.margin = self.processor.margin
        self.border_size = self.processor.border_size

        # Create stuff we need
        self.open_image()
        self.recalculate_canvas_size()

    @property
    def target_size(self) -> int:
        """
        Calculate the target size for the image based on canvas size and margins.
        """
        return self.canvas_size - (2 * self.margin)

    @property
    def output_path(self) -> Path:
        return self.file_path.parent / f"{self.file_path.stem}{self.output_suffix}.jpg"

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
        If the image is smaller than the canvas, reduce the canvas size.
        """
        # If the original image is smaller than the target size, halve the canvas size
        if max(self.original.width, self.original.height) < self.target_size:
            self.canvas_size = max(1080, self.canvas_size // 2)
            self.margin = max(50, self.margin // 2)
            self.border_size = max(4, self.border_size // 2)

    def scale_image(self) -> Image.Image:
        """
        Scale the image to fit within the target size, maintaining aspect ratio.
        
        Args:
            image (Image.Image): Original image to be scaled.
        
        Returns:
            Image.Image: Scaled image.
        """ 
        target_size = self.target_size
        img_ratio = min(target_size / self.original.width, target_size / self.original.height)
        new_size = (int(self.original.width * img_ratio), int(self.original.height * img_ratio))
        
        logger.debug(f"Scaling image to {new_size}")
        self._scaled = self.original.resize(new_size, Image.LANCZOS)

        return self._scaled

    def create_blurred_background(self) -> Image.Image:
        """
        Create a blurred and enhanced version of the image for background.
        
        Returns:
            Image.Image: Processed background image.
        """
        
        img_ratio = max(self.canvas_size / self.original.width, self.canvas_size / self.original.height)
        new_size = (int(self.original.width * img_ratio), int(self.original.height * img_ratio))
        
        self._blurred = self.processor.create_blurred_background(self.original, new_size)
        
        return self._blurred

    def setup_canvas(self) -> Image.Image:
        """
        Setup the canvas and layers on top of it.
        """
        logger.debug('Creating canvas')
        self._canvas = Image.new('RGB', (self.canvas_size, self.canvas_size), (255, 255, 255))

        logger.debug('Copying blurred image to canvas')
        self._canvas.paste(self.blurred, (0, 0))

        logger.debug('Placing scaled image on canvas')
        canvas_size = self.canvas_size
        x_offset = (canvas_size - self.scaled.width) // 2
        y_offset = (canvas_size - self.scaled.height) // 2
        self.canvas.paste(self.scaled, (x_offset, y_offset))
            
        border_img = ImageOps.expand(self.scaled, self.border_size, fill='black').convert('RGBA')
        self._canvas.paste(border_img, (x_offset - self.border_size, y_offset - self.border_size))

        return self._canvas

    def adjust_image(self):
        return self.processor.adjust_image(self)

    def adjustments_applied(self, adjustment_type : AdjustmentTypes = AdjustmentTypes.BASIC):
        if adjustment_type not in self._adjustments:
            self._adjustments.append(adjustment_type)

    def save(self) -> Path:
        """
        Save the processed image to a file.
        """
        if not self.canvas:
            raise ValueError("Canvas not created. Run apply_edits() first.")
        
        logger.debug('Saving processed image')
        if self.output_path.exists():
            logger.debug(f"Overwriting processed image: {self.output_path}")

        self.canvas.save(self.output_path)
        logger.debug(f"Processed image saved as {self.output_path}")
        
        return self.output_path