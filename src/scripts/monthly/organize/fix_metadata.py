#!/usr/bin/env python3
"""
Fix and reorganize photos whose filename encodes a date but are in the wrong folder.

Destination layout: /base/YYYY/YYYY-MM-DD/filename
Patterns matched:
  1) (IMG|PXL|dji_fly|PSX|Manly|VID|Screenshot|download)_YYYYMMDD_\\d+.(jpe?g|png|arw|dng)
  2) signal-YYYY-MM-DD-.*.(jpe?g|png)
  3) YYYY_MMDD_\\d{6}.mp4

Each one supports {pattern}-01.{ext}, {pattern}-01-02.{ext}, etc.

Author: Jess Mann
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
import uuid

from pydantic import BaseModel, Field, PositiveInt, ValidationError, field_validator, model_validator
from alive_progress import alive_bar

from scripts.lib.file_manager import FileManager

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
    directory_to_sort: Path | None = Field(
        None,
        description="Directory to scan and fix. By default, same as base_directory.",
    )
    dry_run: bool = Field(False, description="If True, do not perform any write operations.")
    skip_existing: bool = Field(False, description="If True, skip moves when the destination exists.")
    prefer_piexif: bool = Field(False, description="Force piexif over exiftool where possible.")
    max_depth: PositiveInt = Field(6, description="Maximum directory depth to scan from directory_to_sort.")
    verbose: bool = Field(False, description="Enable debug logging.")

    @field_validator("base_directory", mode="before")
    @classmethod
    def _normalize_base_directory(cls, value: object) -> Path:
        path = Path(value).expanduser().resolve()
        return path

    @field_validator("directory_to_sort", mode="before")
    @classmethod
    def _normalize_directory_to_sort(cls, value: object) -> Path | None:
        if value is None:
            return None
        return Path(value).expanduser().resolve()

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
        r"^(?P<prefix>IMG|PXL|dji_fly|PSX|Manly|VID|Screenshot|download)_(?P<ymd>20\d{2}[01]\d[0-3]\d)_(?P<seq>\d+).*?\.(?P<ext>jpe?g|png|arw|dng|mp4|psd|tif+)$",
        re.IGNORECASE,
    )
    # signal-YYYY-MM-DD-.*.[ext]
    _re_signal: Final[re.Pattern[str]] = re.compile(
        r"^signal-(?P<ymd_dash>\d{4}-\d{2}-\d{2})-.*?\.(?P<ext>jpe?g|png|mp4)$",
        re.IGNORECASE,
    )
    # YYYY_MMDD_HHMMSS.[ext]
    _re_date: Final[re.Pattern[str]] = re.compile(
        r"^(?P<year>20\d{2})-((?P<month>[01]\d)-(?P<day>[0-3]\d))([^\d][\s()\d_-]*)?\.(?P<ext>jpe?g|png|arw|dng|mp4|psd|tif+)$",
        re.IGNORECASE,
    )
    # AirBrush_YYYYMMDD[...].(jpe?g|png)
    _re_airbrush: Final[re.Pattern[str]] = re.compile(
        r"^AirBrush_(?P<ymd>20[0-2]\d[01]\d[0-3]\d)[-\d()]*?\.(?P<ext>jpe?g|png)$",
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

    def update_dates(self, file_path: Path, shot_date: date, dry_run: bool) -> bool:
        """Update metadata to shot_date (EXIF DateTimeOriginal/CreateDate, etc.)."""
        raise NotImplementedError
    
class ExifToolUpdater(MetadataUpdater):
    """Uses exiftool if available to set multiple date tags in one go."""

    _MP4_NO_DATA_REFERENCE_ERROR: Final[str] = "No data reference for sample description"

    def __init__(self) -> None:
        self._available = self._check_available()
        self._ffmpeg_available = self._check_ffmpeg_available()

    @staticmethod
    def _check_available() -> bool:
        try:
            subprocess.run(["exiftool", "-ver"], capture_output=True, check=False)
            return True
        except FileNotFoundError:
            return False

    @staticmethod
    def _check_ffmpeg_available() -> bool:
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=False)
            return True
        except FileNotFoundError:
            return False

    @property
    def available(self) -> bool:
        return self._available

    def _ensure_unique_sibling_path(self, desired_path: Path) -> Path:
        """Return a unique path by appending -{n} if needed."""
        if not desired_path.exists():
            return desired_path

        stem = desired_path.stem
        suffix = desired_path.suffix
        parent = desired_path.parent
        index = 1
        while True:
            candidate = parent / f"{stem}-{index}{suffix}"
            if not candidate.exists():
                return candidate
            index += 1

    def _ffmpeg_remux_mp4_in_place(self, file_path: Path, dry_run: bool) -> bool:
        """
        Remux MP4 (stream-copy) to rebuild container tables.

        Workflow:
          - Create temp fixed file next to original
          - Rename original to *_before-ffmpeg-fix.mp4 (preserve)
          - Rename fixed temp to original filename
          - Nothing deleted
        """
        if not self._ffmpeg_available:
            logger.warning("ffmpeg not available; cannot repair MP4 container: %s", file_path)
            return False

        if file_path.suffix.lower() != ".mp4":
            return False

        before_fix_desired = file_path.with_name(f"{file_path.stem}_before-ffmpeg-fix{file_path.suffix}")
        before_fix_path = self._ensure_unique_sibling_path(before_fix_desired)

        temp_fixed_path = file_path.with_name(
            f"{file_path.stem}.ffmpeg-fixed.{uuid.uuid4().hex}{file_path.suffix}"
        )

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(file_path),
            "-map",
            "0",
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(temp_fixed_path),
        ]

        logger.info("Repairing MP4 container with ffmpeg: %s", file_path.name)
        logger.debug("Running ffmpeg: %s", " ".join(cmd))

        if dry_run:
            logger.info("Dry-run: would remux %s -> %s, rename original -> %s",
                        file_path.name, temp_fixed_path.name, before_fix_path.name)
            return True

        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            stderr = (res.stderr or "").strip()
            # If ffmpeg fails, don't rename anything.
            raise RuntimeError(f"ffmpeg remux failed for {file_path}: {stderr}")

        if not temp_fixed_path.exists() or temp_fixed_path.stat().st_size == 0:
            raise RuntimeError(f"ffmpeg produced no output for {file_path}: {temp_fixed_path}")

        # Preserve original by renaming it out of the way first.
        file_path.rename(before_fix_path)

        # Put fixed file into original filename.
        temp_fixed_path.rename(file_path)

        logger.info("MP4 repaired. Preserved original as %s; fixed file kept as %s",
                    before_fix_path.name, file_path.name)
        return True

    def update_dates(self, file_path: Path, shot_date: date, dry_run: bool) -> bool:
        if not self.available:
            raise RuntimeError("exiftool not available")

        dt_str = f"{shot_date.strftime('%Y:%m:%d')} 00:00:00"

        # Update common date tags; -overwrite_original to avoid _original files.
        def run_exiftool(target_path: Path) -> subprocess.CompletedProcess[str]:
            cmd = [
                "exiftool",
                "-overwrite_original",
                f"-DateTimeOriginal={dt_str}",
                f"-CreateDate={dt_str}",
                f"-TrackCreateDate={dt_str}",
                f"-MediaCreateDate={dt_str}",
                str(target_path),
            ]
            logger.debug("Running exiftool: %s", " ".join(cmd))
            return subprocess.run(cmd, capture_output=True, text=True)

        if dry_run:
            # We treat dry-run as success. If you want strict "simulate failure", change this.
            return True

        res = run_exiftool(file_path)
        if res.returncode == 0:
            return True

        stderr = (res.stderr or "").strip()

        # If exiftool fails with the known MP4 container issue, repair with ffmpeg and retry.
        if file_path.suffix.lower() == ".mp4" and self._MP4_NO_DATA_REFERENCE_ERROR in stderr:
            logger.warning(
                "exiftool failed due to MP4 container issue; attempting ffmpeg repair: %s (%s)",
                file_path,
                stderr,
            )

            repaired = self._ffmpeg_remux_mp4_in_place(file_path, dry_run=False)
            if not repaired:
                raise RuntimeError(f"exiftool failed for {file_path}: {stderr}")

            # Retry exiftool against the repaired file (now at the original filename).
            res_retry = run_exiftool(file_path)
            if res_retry.returncode == 0:
                return True

            stderr_retry = (res_retry.stderr or "").strip()
            raise RuntimeError(
                f"exiftool failed after ffmpeg repair for {file_path}: {stderr_retry}"
            )

        raise RuntimeError(f"exiftool failed for {file_path}: {stderr}")

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

    def update_dates(self, file_path: Path, shot_date: date, dry_run: bool) -> bool:
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
            return False

        # Google Motion Photos often have complex XMP/MPF; piexif can choke. Prefer exiftool for these.
        if "_MP" in file_path.stem.upper():
            logger.debug("Likely Motion Photo; skipping piexif for %s", file_path.name)
            return False

        import piexif  # type: ignore

        date_str = f"{shot_date.strftime('%Y:%m:%d')} 00:00:00"
        if dry_run:
            return True

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
            if "Given file is neither" in str(exc):
                logger.warning("piexif cannot handle this JPEG (corrupt?): %s", file_path.absolute())
                return False
            
            raise RuntimeError(f"piexif update failed for {file_path}: {exc}") from exc
        return True

class CompositeUpdater(MetadataUpdater):
    """Try exiftool first (broad support), then piexif, else warn."""
    acceptable_date_range : tuple[date, date]

    def __init__(self, prefer_piexif: bool = False) -> None:
        self.exiftool = ExifToolUpdater()
        self.piexif = PiexifUpdater()
        self.prefer_piexif = prefer_piexif
        self.acceptable_date_range = (date(2000, 1, 1), datetime.now().date())

    def update_dates(self, file_path: Path, shot_date: date, dry_run: bool) -> bool:
        # Choose updater
        try:
            if not (self.acceptable_date_range[0] <= shot_date <= self.acceptable_date_range[1]):
                logger.warning("Shot date %s for %s is outside acceptable range %s - %s; skipping update.",
                               shot_date, file_path.name, self.acceptable_date_range[0], self.acceptable_date_range[1])
                return False

            if self.prefer_piexif and self.piexif.available:
                try:
                    return self.piexif.update_dates(file_path, shot_date, dry_run)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("piexif failed for %s: %s; trying exiftool", file_path.name, exc)

            if self.exiftool.available:
                self.exiftool.update_dates(file_path, shot_date, dry_run)
                return True

            if self.piexif.available:
                return self.piexif.update_dates(file_path, shot_date, dry_run)

            logger.warning("No metadata tool available for %s; EXIF not updated.", file_path.name)
        except RuntimeError as rexc:
            logger.warning("Metadata update failed for %s: %s", file_path.name, rexc)
        return False

# --------------------------------------------------------------------------------------
# File Moving
# --------------------------------------------------------------------------------------

class PhotoMover:
    """Finds, validates, updates, and moves photos to correct dated folders."""
    acceptable_date_range : tuple[date, date]
    mover : FileManager

    def __init__(self, config: AppConfig, updater: MetadataUpdater) -> None:
        self.config = config
        self.updater = updater
        self.acceptable_date_range = (date(2000, 1, 1), datetime.now().date())
        self.mover = FileManager(dry_run = config.dry_run, directory=self.config.base_directory)

    def scan_files(self) -> Iterable[Path]:
        """Yield candidate files under base_directory (bounded by max_depth)."""
        directory_to_sort = self.config.directory_to_sort or self.config.base_directory
        max_depth = self.config.max_depth
        logger.info('Scanning files...')
        for path in directory_to_sort.rglob("*"):
            if not path.is_file():
                continue
            # Enforce depth limit
            try:
                rel = path.relative_to(directory_to_sort)
            except ValueError:
                continue
            if len(rel.parts) > max_depth:
                continue
            # Quick suffix filter
            if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".arw", ".nef", ".dng", ".mp4"}:
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
        """Process all candidate files. Returns tuple: (checked, moved)."""
        moved = 0
        checked = 0
        errors = 0
        with alive_bar(title="Processing", dual_line=True, unknown='waves') as bar:
            def progress_text(s: str, log : int | None = None) -> None:
                bar.text(f"({moved} →/{errors} E/{checked} ✓) {s}")
                match log:
                    case logging.INFO:
                        logger.info(s)
                    case logging.WARNING:
                        logger.warning(s)
                    case logging.ERROR:
                        logger.error(s)
                    case logging.DEBUG:
                        logger.debug(s)
            
            for file_path in self.scan_files():
                try:
                    checked += 1
                    fname = file_path.name
                    shot_date = FilenameParser.parse_date(fname)

                    if not shot_date:
                        progress_text(f"No date in filename: {fname}", log=logging.DEBUG)
                        continue

                    if not (self.acceptable_date_range[0] <= shot_date <= self.acceptable_date_range[1]):
                        progress_text(f"Shot date {shot_date} for {fname} is outside acceptable range {self.acceptable_date_range[0]} - {self.acceptable_date_range[1]}; skipping update.", log=logging.INFO)
                        continue

                    if self.is_correct_location(file_path, shot_date):
                        progress_text(f"Already in correct location: {file_path}", log=logging.DEBUG)
                        continue

                    # Update EXIF (if possible) and file times
                    try:
                        self.updater.update_dates(file_path, shot_date, self.config.dry_run)
                    except (OSError, PermissionError) as exc:  # noqa: BLE001
                        errors += 1
                        progress_text(f"Metadata update failed for {fname}: {exc}", log=logging.WARNING)

                    try:
                        self._set_file_times(file_path, shot_date, self.config.dry_run)
                    except (OSError, PermissionError) as exc:  # noqa: BLE001
                        errors += 1
                        progress_text(f"Failed to set file times for {fname}: {exc}", log=logging.WARNING)

                    # Compute destination and move
                    dest_dir = self._expected_dir(self.config.base_directory, shot_date)
                    destination = dest_dir / fname
                    try:
                        destination = self._ensure_unique_destination(destination)
                        progress_text(f"Moving to: {destination}")
                        self.move(file_path, destination)
                        moved += 1
                    except FileExistsError as exc:
                        progress_text(f"Skipping (exists): {exc}", log=logging.DEBUG)
                finally:
                    bar()  # tick regardless

        return checked, moved

    def move(self, source: Path, destination: Path) -> None:
        """Move file from source to destination."""
        if self.config.dry_run:
            logger.info("Dry-run: would move %s -> %s", source, destination)
            return
        self.mover.move_file(source, destination)
        logger.info("Moved %s -> %s", source, destination)

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
    parser.add_argument(
        "--directory-to-sort", type=Path, default=None,
        help="Directory to scan and fix. By default, same as base_directory."
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
                directory_to_sort=args.directory_to_sort,
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
