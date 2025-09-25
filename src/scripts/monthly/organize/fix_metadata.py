#!/usr/bin/env python3
"""
Fix and reorganize photos whose filename encodes a date but are in the wrong folder.

Destination layout: /base/YYYY/YYYY-MM-DD/filename
Patterns matched:
  1) (IMG|PXL|dji_fly|PSX|Manly)_YYYYMMDD_\\d+.(jpe?g|png|arw|dng)
  2) signal-YYYY-MM-DD-.*.(jpe?g|png)

Author: You
Python: 3.12
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import subprocess
from datetime import datetime, date, time
from pathlib import Path
from typing import Final, Iterable, Optional

from pydantic import BaseModel, Field, PositiveInt, ValidationError
from alive_progress import alive_bar

# --------------------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------------------

logger = logging.getLogger("fix_photo_dates")
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# --------------------------------------------------------------------------------------
# Config (Pydantic)
# --------------------------------------------------------------------------------------

class AppConfig(BaseModel):
    """Configuration for the fixer."""
    base_directory: Path = Field(..., description="Root Photos directory (contains year subfolders).")
    dry_run: bool = Field(False, description="If True, do not perform any write operations.")
    skip_existing: bool = Field(False, description="If True, skip moves when the destination exists.")
    prefer_piexif: bool = Field(False, description="Force piexif over exiftool where possible.")
    max_depth: PositiveInt = Field(6, description="Maximum directory depth to scan from base.")
    verbose: bool = Field(False, description="Enable debug logging.")

    def model_post_init(self, __context: dict) -> None:  # pydantic v2 hook
        if self.verbose:
            logger.setLevel(logging.DEBUG)

# --------------------------------------------------------------------------------------
# Filename Parsers
# --------------------------------------------------------------------------------------

class FilenameParser:
    """Parses a filename to extract a date."""
    # (IMG|PXL|dji_fly|PSX|Manly)_YYYYMMDD_\d+.[ext]
    _re_compact: Final[re.Pattern[str]] = re.compile(
        r"^(?P<prefix>IMG|PXL|dji_fly|PSX|Manly)_(?P<ymd>20\d{2}[01]\d[0-3]\d)_(?P<seq>\d+).*?\.(?P<ext>jpe?g|png|arw|dng)$",
        re.IGNORECASE,
    )
    # signal-YYYY-MM-DD-.*.[ext]
    _re_signal: Final[re.Pattern[str]] = re.compile(
        r"^signal-(?P<ymd_dash>\d{4}-\d{2}-\d{2})-.*?\.(?P<ext>jpe?g|png)$",
        re.IGNORECASE,
    )
    _re_date: Final[re.Pattern[str]] = re.compile(
        r"^(?P<year>20\d{2})-((?P<month>[01]\d)-(?P<day>[0-3]\d))([^\d][\s()\d_-]*)?\.(?P<ext>jpe?g|png|arw|dng)$",
        re.IGNORECASE,
    )
    _re_airbrush: Final[re.Pattern[str]] = re.compile(
        r"^AirBrush_(?P<ymd>20[0-2]\d[01]\d[0-3]\d)\d*?\.(?P<ext>jpe?g|png)$",
        re.IGNORECASE,
    )

    @classmethod
    def parse_date(cls, filename: str) -> Optional[date]:
        """Return date from supported filename formats, else None."""
        m1 = cls._re_compact.match(filename)
        if m1:
            ymd = m1.group("ymd")
            try:
                return datetime.strptime(ymd, "%Y%m%d").date()
            except ValueError:
                logger.debug("Compact date parse failed for %s", filename)

        m2 = cls._re_signal.match(filename)
        if m2:
            ymd_dash = m2.group("ymd_dash")
            try:
                return datetime.strptime(ymd_dash, "%Y-%m-%d").date()
            except ValueError:
                logger.debug("Signal date parse failed for %s", filename)

        m3 = cls._re_date.match(filename)
        if m3:
            try:
                year = int(m3.group("year"))
                month = int(m3.group("month"))
                day = int(m3.group("day"))
                return date(year, month, day)
            except (ValueError, TypeError):
                logger.debug("Date parse failed for %s", filename)

        m4 = cls._re_airbrush.match(filename)
        if m4:
            ymd = m4.group("ymd")
            try:
                return datetime.strptime(ymd, "%Y%m%d").date()
            except ValueError:
                logger.debug("AirBrush date parse failed for %s", filename)

        return None

# --------------------------------------------------------------------------------------
# Metadata Updaters (Strategy)
# --------------------------------------------------------------------------------------

class MetadataUpdater:
    """Strategy interface to update image metadata dates."""

    def update_dates(self, file_path: Path, shot_date: date, dry_run: bool) -> None:
        """Update metadata to shot_date (EXIF DateTimeOriginal/CreateDate, etc.)."""
        raise NotImplementedError

class ExifToolUpdater(MetadataUpdater):
    """Uses exiftool if available to set multiple date tags in one go."""

    def __init__(self) -> None:
        self._available = self._check_available()

    @staticmethod
    def _check_available() -> bool:
        try:
            subprocess.run(["exiftool", "-ver"], capture_output=True, check=False)
            return True
        except FileNotFoundError:
            return False

    @property
    def available(self) -> bool:
        return self._available

    def update_dates(self, file_path: Path, shot_date: date, dry_run: bool) -> None:
        if not self.available:
            raise RuntimeError("exiftool not available")

        dt_str = f"{shot_date.strftime('%Y:%m:%d')} 00:00:00"
        # Update common date tags; -overwrite_original to avoid _original files.
        cmd = [
            "exiftool",
            "-overwrite_original",
            f"-DateTimeOriginal={dt_str}",
            f"-CreateDate={dt_str}",
            #f"-ModifyDate={dt_str}",
            # For some RAW containers:
            f"-TrackCreateDate={dt_str}",
            #f"-TrackModifyDate={dt_str}",
            f"-MediaCreateDate={dt_str}",
            #f"-MediaModifyDate={dt_str}",
            str(file_path),
        ]
        logger.debug("Running exiftool: %s", " ".join(cmd))
        if dry_run:
            return
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"exiftool failed for {file_path}: {res.stderr.strip()}")

class PiexifUpdater(MetadataUpdater):
    """Fallback for JPEG files using piexif (if installed)."""

    def __init__(self) -> None:
        try:
            import piexif  # noqa: F401
            self._available = True
        except Exception:  # noqa: BLE001
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def update_dates(self, file_path: Path, shot_date: date, dry_run: bool) -> None:
        """
        Update EXIF dates for JPEGs using piexif.

        Notes:
        - 'CreateDate' in exiftool maps to EXIF's DateTimeDigitized (Tag 36868).
        - Skip non-JPEGs and Google Motion Photos (e.g., PXL_*_MP.jpg) here; let exiftool handle those.
        """
        if not self.available:
            raise RuntimeError("piexif not available")

        suffix = file_path.suffix.lower()
        if suffix not in {".jpg", ".jpeg"}:
            logger.debug("piexif only supports JPEG; skipping %s", file_path.name)
            return

        # Google Motion Photos often have complex XMP/MPF; piexif can choke. Prefer exiftool for these.
        if "_MP" in file_path.stem.upper():
            logger.debug("Likely Motion Photo; skipping piexif for %s", file_path.name)
            return

        import piexif  # type: ignore

        date_str = f"{shot_date.strftime('%Y:%m:%d')} 00:00:00"
        if dry_run:
            return

        try:
            exif_dict = piexif.load(str(file_path))
            # Ensure dictionaries exist
            exif_dict.setdefault("Exif", {})
            exif_dict.setdefault("0th", {})

            # Map:
            # - DateTimeOriginal (36867) ~ when the photo was taken
            # - DateTimeDigitized (36868) ~ "CreateDate" in exiftool vocabulary
            # - 0th/IFD0 DateTime (306) ~ generic timestamp
            exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = date_str.encode()
            exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = date_str.encode()
            exif_dict["0th"][piexif.ImageIFD.DateTime] = date_str.encode()

            exif_bytes = piexif.dump(exif_dict)
            piexif.insert(exif_bytes, str(file_path))
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"piexif update failed for {file_path}: {exc}") from exc

class CompositeUpdater(MetadataUpdater):
    """Try exiftool first (broad support), then piexif, else warn."""

    def __init__(self, prefer_piexif: bool = False) -> None:
        self.exiftool = ExifToolUpdater()
        self.piexif = PiexifUpdater()
        self.prefer_piexif = prefer_piexif

    def update_dates(self, file_path: Path, shot_date: date, dry_run: bool) -> None:
        # Choose updater
        if self.prefer_piexif and self.piexif.available:
            try:
                self.piexif.update_dates(file_path, shot_date, dry_run)
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning("piexif failed for %s: %s; trying exiftool", file_path.name, exc)

        if self.exiftool.available:
            self.exiftool.update_dates(file_path, shot_date, dry_run)
            return

        if self.piexif.available:
            self.piexif.update_dates(file_path, shot_date, dry_run)
            return

        logger.warning("No metadata tool available for %s; EXIF not updated.", file_path.name)

# --------------------------------------------------------------------------------------
# File Moving
# --------------------------------------------------------------------------------------

class PhotoMover:
    """Finds, validates, updates, and moves photos to correct dated folders."""

    def __init__(self, config: AppConfig, updater: MetadataUpdater) -> None:
        self.config = config
        self.updater = updater

    def scan_files(self) -> Iterable[Path]:
        """Yield candidate files under base_directory (bounded by max_depth)."""
        base = self.config.base_directory
        max_depth = self.config.max_depth
        logger.info('Scanning files...')
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            # Enforce depth limit
            try:
                rel = path.relative_to(base)
            except ValueError:
                continue
            if len(rel.parts) > max_depth:
                continue
            # Quick suffix filter
            if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".arw", ".dng"}:
                continue
            yield path

    @staticmethod
    def _expected_dir(base: Path, shot_date: date) -> Path:
        return base / f"{shot_date.year:04d}" / shot_date.strftime("%Y-%m-%d")

    @staticmethod
    def _current_dir_info(file_path: Path) -> tuple[Optional[int], Optional[str]]:
        """Return (year, yyyy-mm-dd) from path, if present."""
        try:
            day_dir = file_path.parent.name  # YYYY-MM-DD
            year_dir = file_path.parent.parent.name  # YYYY
            year = int(year_dir) if re.fullmatch(r"\d{4}", year_dir) else None
            day = day_dir if re.fullmatch(r"\d{4}-\d{2}-\d{2}", day_dir) else None
            return year, day
        except Exception:  # noqa: BLE001
            return None, None

    def is_correct_location(self, file_path: Path, shot_date: date) -> bool:
        exp_dir = self._expected_dir(self.config.base_directory, shot_date)
        year, day = self._current_dir_info(file_path)
        return (
            year == shot_date.year and
            day == shot_date.strftime("%Y-%m-%d") and
            file_path.parent == exp_dir
        )

    def _ensure_unique_destination(self, destination: Path) -> Path:
        if not destination.exists():
            return destination
        if self.config.skip_existing:
            raise FileExistsError(f"Destination exists: {destination}")

        stem = destination.stem
        suffix = destination.suffix
        parent = destination.parent
        i = 1
        while True:
            candidate = parent / f"{stem}-{i}{suffix}"
            if not candidate.exists():
                return candidate
            i += 1

    @staticmethod
    def _set_file_times(file_path: Path, shot_date: date, dry_run: bool) -> None:
        # Set atime/mtime to midnight local time
        dt = datetime.combine(shot_date, time.min)
        ts = dt.timestamp()
        if dry_run:
            return
        os.utime(file_path, (ts, ts), follow_symlinks=False)

    def process(self) -> tuple[int, int]:
        """Process all candidate files. Returns (checked, moved)."""
        moved = 0
        checked = 0
        with alive_bar(title="Processing", dual_line=True, unknown='waves') as bar:
            for file_path in self.scan_files():
                try:
                    checked += 1
                    fname = file_path.name
                    shot_date = FilenameParser.parse_date(fname)

                    if not shot_date:
                        logger.debug("No date in filename: %s", fname)
                        continue

                    if self.is_correct_location(file_path, shot_date):
                        logger.debug("Already in correct location: %s", file_path)
                        continue

                    # Update EXIF (if possible) and file times
                    try:
                        self.updater.update_dates(file_path, shot_date, self.config.dry_run)
                    except (OSError, PermissionError) as exc:  # noqa: BLE001
                        logger.warning("Metadata update failed for %s: %s", fname, exc)

                    try:
                        self._set_file_times(file_path, shot_date, self.config.dry_run)
                    except (OSError, PermissionError) as exc:  # noqa: BLE001
                        logger.warning("Failed to set file times for %s: %s", fname, exc)

                    # Compute destination and move
                    dest_dir = self._expected_dir(self.config.base_directory, shot_date)
                    destination = dest_dir / fname
                    try:
                        destination = self._ensure_unique_destination(destination)
                        bar.text(f"({moved}/{checked}) Moving to: {destination}")
                        if not self.config.dry_run:
                            dest_dir.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(file_path), str(destination))
                        moved += 1
                    except FileExistsError as exc:
                        bar.text(f"Skipping (exists): {exc}")
                finally:
                    bar()  # tick regardless

        return checked, moved

# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Find photos with date-encoded filenames not in the correct folder, fix metadata, and move."
    )
    parser.add_argument(
        "base_directory", type=Path,
        help="Root Photos directory (e.g., /mnt/i/Photos)."
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not write changes.")
    parser.add_argument("--skip-existing", action="store_true", help="Skip if destination file exists.")
    parser.add_argument("--prefer-piexif", action="store_true", help="Prefer piexif over exiftool when possible.")
    parser.add_argument("--max-depth", type=int, default=6, help="Max directory depth to scan (default: 6).")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging.")
    return parser

def main(argv: Optional[list[str]] = None) -> int:
    try:
        parser = build_arg_parser()
        args = parser.parse_args(argv)

        try:
            config = AppConfig(
                base_directory=args.base_directory,
                dry_run=args.dry_run,
                skip_existing=args.skip_existing,
                prefer_piexif=args.prefer_piexif,
                max_depth=args.max_depth,
                verbose=args.verbose,
            )
        except ValidationError as ve:
            logger.error("Invalid configuration: %s", ve)
            return 2

        updater = CompositeUpdater(prefer_piexif=config.prefer_piexif)
        mover = PhotoMover(config, updater)
        checked, moved = mover.process()
        logger.info("Done. Checked: %s, Moved: %s%s",
                    checked, moved, " (dry-run)" if config.dry_run else "")

    except KeyboardInterrupt:
        logger.warning("Interrupted by user.")
        return 130

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
