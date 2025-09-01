from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from PIL import Image, ImageOps

from scripts.processing.meta import AdjustmentTypes

if TYPE_CHECKING:
    from scripts.processing.bsky.processor import BlueskyProcessor

logger = logging.getLogger(__name__)


@dataclass
class BlueskyImage:
    file_path: Path
    processor: BlueskyProcessor
    crop_ratio: Literal["auto", "1:1", "4:5", "16:9"] = "auto"
    output_dir: Path | None = None

    _output_suffix: str = field(init=False)
    _adjustments: list[AdjustmentTypes] = field(default_factory=list)
    _original: Image.Image | None = field(init=False, default=None)
    _final: Image.Image | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        self._output_suffix = self.processor.get_file_suffix()
        self.open_image()

    @property
    def output_path(self) -> Path:
        folder = self.output_dir or self.file_path.parent
        return folder / f"{self.file_path.stem}{self._output_suffix}"

    @property
    def original(self) -> Image.Image:
        if not self._original:
            return self.open_image()
        return self._original

    @property
    def final(self) -> Image.Image:
        if not self._final:
            return self.prepare_final()
        return self._final

    def open_image(self) -> Image.Image:
        img = Image.open(self.file_path)
        # Convert to RGB for consistent JPEG/WEBP saves
        if img.mode not in ("RGB", "RGBA"):
            logger.debug("Converting image mode from %s to RGB (%s)", img.mode, self.file_path.name)
            img = img.convert("RGB")
        self._original = img
        return self._original

    def setup(self) -> None:
        # optional crop to ratio
        img = self._crop_to_ratio(self.original, self.crop_ratio)
        # optional simple adjustments via processor
        img = self.processor.adjust_image(img)
        self._final = img

    def prepare_final(self) -> Image.Image:
        # Fallback in case setup not called
        img = self._crop_to_ratio(self.original, self.crop_ratio)
        img = self.processor.adjust_image(img)
        return img

    def _crop_to_ratio(self, img: Image.Image, choice: str) -> Image.Image:
        if choice == "auto":
            return img

        target_map = {
            "1:1": (1, 1),
            "4:5": (4, 5),
            "16:9": (16, 9),
        }
        if choice not in target_map:
            return img

        tw, th = target_map[choice]
        target = tw / th

        w, h = img.size
        current = w / h

        if abs(current - target) < 1e-3:
            return img  # already close

        if current > target:
            # too wide -> crop width
            new_w = int(h * target)
            x0 = (w - new_w) // 2
            box = (x0, 0, x0 + new_w, h)
        else:
            # too tall -> crop height
            new_h = int(w / target)
            y0 = (h - new_h) // 2
            box = (0, y0, w, y0 + new_h)

        cropped = img.crop(box)
        logger.debug("Cropped to %s from %s -> %s", choice, (w, h), cropped.size)
        return cropped

    def adjustments_applied(self, adjustment_type: AdjustmentTypes = AdjustmentTypes.BASIC) -> None:
        if adjustment_type not in self._adjustments:
            self._adjustments.append(adjustment_type)

    # --- Save logic enforcing <= max_bytes ---
    def save(self, max_bytes: int, output_format: Literal["jpeg", "webp"] = "jpeg") -> Path:
        img = self.final

        # Prefer progressive JPEG; for WEBP use default smart settings.
        quality_candidates = [95, 90, 85, 80, 75, 70, 60, 50, 40]

        out_path = self.output_path
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # 1) Try quality ladder without resizing
        for q in quality_candidates:
            if self._try_save(img, out_path, output_format, q, max_bytes):
                return out_path

        # 2) If still too big, scale down iteratively (binary-ish search on long side)
        # Start with 95 and drop size until we meet the cap.
        long_side = max(img.size)
        lo, hi = 480, long_side  # do not go below 480px on long side by default
        best: tuple[Image.Image, int] | None = None  # (image, quality)

        while hi - lo > 64:  # step resolution
            mid = (hi + lo) // 2
            scaled = self._scale_long_side(img, mid)
            ok = False
            chosen_q = 85
            for q in quality_candidates[2:]:  # start at 85 downward
                if self._try_save(scaled, out_path, output_format, q, max_bytes):
                    best = (scaled, q)
                    ok = True
                    break
            if ok:
                hi = mid  # can try smaller image (to keep more headroom)
            else:
                lo = mid  # need larger (we failed? then we actually need to reduce constraints)
                # But if even 40 at this size fails, continue loop to try a *smaller* image (lower hi)
                hi = mid

        if best:
            scaled, q = best
            self._try_save(scaled, out_path, output_format, q, max_bytes)  # final write
            return out_path

        # 3) Last resort: save whatever we have at lowest quality
        logger.warning("Could not meet size cap; saving at minimum quality.")
        self._try_save(img, out_path, output_format, 40, max_bytes, force=True)
        return out_path

    def _scale_long_side(self, img: Image.Image, target_long_side: int) -> Image.Image:
        w, h = img.size
        if w >= h:
            ratio = target_long_side / float(w)
            new_size = (int(w * ratio), int(h * ratio))
        else:
            ratio = target_long_side / float(h)
            new_size = (int(w * ratio), int(h * ratio))
        return img.resize(new_size, Image.LANCZOS)

    def _try_save(
        self,
        img: Image.Image,
        out_path: Path,
        fmt: Literal["jpeg", "webp"],
        quality: int,
        max_bytes: int,
        force: bool = False,
    ) -> bool:
        """Attempt in-memory save; write to disk only if ≤ max_bytes (or force)."""
        buf = io.BytesIO()
        save_kwargs: dict = {}
        if fmt == "jpeg":
            save_kwargs.update(dict(format="JPEG", quality=quality, optimize=True, progressive=True, subsampling="4:2:0"))
            img_to_save = img.convert("RGB") if img.mode != "RGB" else img
        else:  # webp
            save_kwargs.update(dict(format="WEBP", quality=quality, method=6))
            # WEBP supports RGBA; leave as-is
            img_to_save = img

        img_to_save.save(buf, **save_kwargs)
        size = buf.tell()
        if size <= max_bytes or force:
            with out_path.open("wb") as f:
                f.write(buf.getvalue())
            logger.debug("Saved %s (%d bytes) q=%d", out_path.name, size, quality)
            return True
        return False
