#!/usr/bin/env python3
"""
Fix and reorganize photos whose filename encodes a date (and optionally time) but are in the wrong folder.

Destination layout: /base/YYYY/YYYY-MM-DD/filename
Patterns matched:
  1) (IMG|PXL|dji_fly|PSX|Manly|VID|Screenshot|download)_YYYYMMDD_\\d+.(jpe?g|png|arw|dng)
  2) signal-YYYY-MM-DD-.*.(jpe?g|png)
  3) YYYY_MMDD_\\d{6}.mp4

Each one supports {pattern}-01.{ext}, {pattern}-01-02.{ext}, etc.

Key behavior:
- If the filename contains YMD + HMS, use that exact datetime.
- If the filename contains only YMD (no HMS), preserve the existing HMS from metadata (best available tag).
- If no HMS is available anywhere, default to 00:00:00 (and log a warning).

Author: Jess Mann
Python: 3.12
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Final, Iterable, Optional

from alive_progress import alive_bar
from pydantic import BaseModel, Field, PositiveInt, ValidationError, field_validator

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
@dataclass(frozen=True, slots=True)
class ParsedFilenameDatetime:
    shot_date: date
    shot_time: Optional[time]  # None means "not in filename"


class FilenameParser:
    """
    Parses a filename to extract a date and (optionally) time.

    We intentionally keep this broad and conservative:
    - Only accept years 2000-2099 (20xx).
    - Only accept valid calendar dates.
    - Only accept valid times (00:00:00 - 23:59:59).
    """

    _EXT_RE: Final[str] = r"(jpe?g|png|arw|nef|dng|mp4|psd|tif+)"
    _PREFIX_RE: Final[str] = r"(IMG|PXL|dji_fly|PSX|Manly|VID|Screenshot|download)"

    # Common: PREFIX_YYYYMMDD_<seq>...ext
    _re_prefix_ymd_seq: Final[re.Pattern[str]] = re.compile(
        rf"^(?P<prefix>{_PREFIX_RE})_(?P<ymd>20\d{{2}}[01]\d[0-3]\d)_(?P<seq>\d+).*?\.(?P<ext>{_EXT_RE})$",
        re.IGNORECASE,
    )

    # signal-YYYY-MM-DD-...ext
    _re_signal: Final[re.Pattern[str]] = re.compile(
        rf"^signal-(?P<ymd_dash>\d{{4}}-\d{{2}}-\d{{2}})(?P<rest>.*?)\.(?P<ext>{_EXT_RE})$",
        re.IGNORECASE,
    )

    # YYYY-MM-DD[... optional time ...].ext  (time might be 6 digits HHMMSS)
    _re_date_dash: Final[re.Pattern[str]] = re.compile(
        rf"^(?P<year>20\d{{2}})-(?P<month>[01]\d)-(?P<day>[0-3]\d)(?P<rest>.*?)\.(?P<ext>{_EXT_RE})$",
        re.IGNORECASE,
    )

    # YYYY_MMDD[_-]HHMMSS...ext (or YYYY_MMDD only)
    _re_date_underscore: Final[re.Pattern[str]] = re.compile(
        rf"^(?P<year>20\d{{2}})_(?P<month>[01]\d)(?P<day>[0-3]\d)(?P<rest>.*?)\.(?P<ext>{_EXT_RE})$",
        re.IGNORECASE,
    )

    # AirBrush_YYYYMMDD...ext
    _re_airbrush: Final[re.Pattern[str]] = re.compile(
        rf"^AirBrush_(?P<ymd>20[0-2]\d[01]\d[0-3]\d)[-\d()_ ]*?\.(?P<ext>{_EXT_RE})$",
        re.IGNORECASE,
    )

    # Flexible time detection in the "rest" portion after date:
    # - 6 digits: HHMMSS
    # - HH-MM-SS / HH_MM_SS / HH.MM.SS / HH:MM:SS
    # - HHMMSSmmm (we accept first 6)
    _re_time_candidates: Final[re.Pattern[str]] = re.compile(
        r"(?P<hh>\d{2})[:._-]?(?P<mm>\d{2})[:._-]?(?P<ss>\d{2})(?:\d{1,6})?"
    )

    @classmethod
    def parse_datetime(cls, filename: str) -> Optional[ParsedFilenameDatetime]:
        """
        Return ParsedFilenameDatetime if supported, else None.

        If time is not present in the filename, shot_time is None.
        """
        # 1) PREFIX_YYYYMMDD_<seq>...
        match = cls._re_prefix_ymd_seq.match(filename)
        if match:
            shot_date = cls._parse_ymd_compact(match.group("ymd"))
            if shot_date is None:
                return None

            seq = match.group("seq")
            shot_time = cls._infer_time_from_digits(seq)
            return ParsedFilenameDatetime(shot_date=shot_date, shot_time=shot_time)

        # 2) signal-YYYY-MM-DD-...
        match = cls._re_signal.match(filename)
        if match:
            shot_date = cls._parse_ymd_dash(match.group("ymd_dash"))
            if shot_date is None:
                return None
            rest = match.group("rest") or ""
            shot_time = cls._extract_time_from_rest(rest)
            return ParsedFilenameDatetime(shot_date=shot_date, shot_time=shot_time)

        # 3) YYYY-MM-DD...
        match = cls._re_date_dash.match(filename)
        if match:
            shot_date = cls._safe_date(
                int(match.group("year")),
                int(match.group("month")),
                int(match.group("day")),
            )
            if shot_date is None:
                return None
            rest = match.group("rest") or ""
            shot_time = cls._extract_time_from_rest(rest)
            return ParsedFilenameDatetime(shot_date=shot_date, shot_time=shot_time)

        # 4) YYYY_MMDD...
        match = cls._re_date_underscore.match(filename)
        if match:
            shot_date = cls._safe_date(
                int(match.group("year")),
                int(match.group("month")),
                int(match.group("day")),
            )
            if shot_date is None:
                return None
            rest = match.group("rest") or ""
            shot_time = cls._extract_time_from_rest(rest)
            return ParsedFilenameDatetime(shot_date=shot_date, shot_time=shot_time)

        # 5) AirBrush_YYYYMMDD...
        match = cls._re_airbrush.match(filename)
        if match:
            shot_date = cls._parse_ymd_compact(match.group("ymd"))
            if shot_date is None:
                return None
            # AirBrush typically doesn't include time in name; keep None.
            return ParsedFilenameDatetime(shot_date=shot_date, shot_time=None)

        return None

    @staticmethod
    def _safe_date(year: int, month: int, day: int) -> Optional[date]:
        try:
            return date(year, month, day)
        except ValueError:
            return None

    @classmethod
    def _parse_ymd_compact(cls, ymd: str) -> Optional[date]:
        try:
            return datetime.strptime(ymd, "%Y%m%d").date()
        except ValueError:
            logger.debug("Failed compact YMD parse: %s", ymd)
            return None

    @classmethod
    def _parse_ymd_dash(cls, ymd_dash: str) -> Optional[date]:
        try:
            return datetime.strptime(ymd_dash, "%Y-%m-%d").date()
        except ValueError:
            logger.debug("Failed dashed YMD parse: %s", ymd_dash)
            return None

    @staticmethod
    def _infer_time_from_digits(digits: str) -> Optional[time]:
        """
        For things like:
          - PXL_20240422_002405682 -> digits=002405682 -> take 00:24:05
          - IMG_20240101_123456 -> 12:34:56
        """
        if len(digits) < 6:
            return None
        candidate = digits[:6]
        try:
            hh = int(candidate[0:2])
            mm = int(candidate[2:4])
            ss = int(candidate[4:6])
            if not (0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59):
                return None
            return time(hh, mm, ss)
        except ValueError:
            return None

    @classmethod
    def _extract_time_from_rest(cls, rest: str) -> Optional[time]:
        """
        Search for an HHMMSS-ish time after the date in the filename.
        """
        if not rest:
            return None

        # Prefer a 6-digit run (HHMMSS) if present (optionally followed by millis).
        digits_runs = re.findall(r"\d{6,}", rest)
        for run in digits_runs:
            inferred = cls._infer_time_from_digits(run)
            if inferred is not None:
                return inferred

        # Otherwise look for separated time formats.
        match = cls._re_time_candidates.search(rest)
        if not match:
            return None

        try:
            hh = int(match.group("hh"))
            mm = int(match.group("mm"))
            ss = int(match.group("ss"))
            if not (0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59):
                return None
            return time(hh, mm, ss)
        except ValueError:
            return None


# --------------------------------------------------------------------------------------
# Metadata Updaters (Strategy)
# --------------------------------------------------------------------------------------
class MetadataUpdater:
    """Strategy interface to update image metadata dates."""

    def get_existing_time(self, file_path: Path) -> Optional[time]:
        """Best-effort read of the existing HMS from metadata (DateTimeOriginal/CreateDate/etc.)."""
        raise NotImplementedError

    def update_datetime(self, file_path: Path, shot_dt: datetime, dry_run: bool) -> bool:
        """Update metadata to shot_dt (EXIF/QuickTime date tags, etc.)."""
        raise NotImplementedError


class ExifToolUpdater(MetadataUpdater):
    """Uses exiftool if available to set multiple date tags in one go."""

    _MP4_NO_DATA_REFERENCE_ERROR: Final[str] = "No data reference for sample description"

    # Tags to read (best-effort) for time-of-day preservation.
    _READ_TAGS: Final[list[str]] = [
        "DateTimeOriginal",
        "CreateDate",
        "MediaCreateDate",
        "TrackCreateDate",
        "ModifyDate",
        "QuickTime:CreateDate",
        "QuickTime:MediaCreateDate",
        "QuickTime:TrackCreateDate",
    ]

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
            logger.info(
                "Dry-run: would remux %s -> %s, rename original -> %s",
                file_path.name,
                temp_fixed_path.name,
                before_fix_path.name,
            )
            return True

        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            stderr = (res.stderr or "").strip()
            raise RuntimeError(f"ffmpeg remux failed for {file_path}: {stderr}")

        if not temp_fixed_path.exists() or temp_fixed_path.stat().st_size == 0:
            raise RuntimeError(f"ffmpeg produced no output for {file_path}: {temp_fixed_path}")

        # Preserve original by renaming it out of the way first.
        file_path.rename(before_fix_path)

        # Put fixed file into original filename.
        temp_fixed_path.rename(file_path)

        logger.info(
            "MP4 repaired. Preserved original as %s; fixed file kept as %s",
            before_fix_path.name,
            file_path.name,
        )
        return True

    @staticmethod
    def _parse_exiftool_datetime(value: str) -> Optional[datetime]:
        """
        Parse common exiftool datetime formats (best-effort).
        Examples:
          - 2024:01:02 03:04:05
          - 2024:01:02 03:04:05-05:00
          - 2024:01:02 03:04:05Z
        """
        if not value:
            return None

        value = value.strip()

        # Common EXIF: "YYYY:MM:DD HH:MM:SS"
        for fmt in ("%Y:%m:%d %H:%M:%S",):
            try:
                return datetime.strptime(value[:19], fmt)
            except ValueError:
                pass

        # Try extracting "HH:MM:SS" from anything that starts with a date.
        match = re.search(r"\b(?P<hh>\d{2}):(?P<mm>\d{2}):(?P<ss>\d{2})\b", value)
        if not match:
            return None

        try:
            hh = int(match.group("hh"))
            mm = int(match.group("mm"))
            ss = int(match.group("ss"))
            if not (0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59):
                return None
        except ValueError:
            return None

        # If we can also safely parse the date portion:
        match_date = re.match(r"^(?P<y>\d{4}):(?P<m>\d{2}):(?P<d>\d{2})", value)
        if not match_date:
            return None
        try:
            yy = int(match_date.group("y"))
            mo = int(match_date.group("m"))
            dd = int(match_date.group("d"))
            return datetime(yy, mo, dd, hh, mm, ss)
        except ValueError:
            return None

    def get_existing_time(self, file_path: Path) -> Optional[time]:
        if not self.available:
            return None

        cmd = ["exiftool", "-j", "-n"]
        for tag in self._READ_TAGS:
            cmd.append(f"-{tag}")
        cmd.append(str(file_path))

        logger.debug("Running exiftool (read): %s", " ".join(cmd))
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            logger.debug("exiftool read failed for %s: %s", file_path.name, (res.stderr or "").strip())
            return None

        try:
            payload = json.loads(res.stdout or "[]")
            if not payload:
                return None
            row = payload[0]
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to parse exiftool JSON for %s: %s", file_path.name, exc)
            return None

        for tag in self._READ_TAGS:
            value = row.get(tag)
            if value is None:
                continue
            parsed = self._parse_exiftool_datetime(str(value))
            if parsed is None:
                continue
            return parsed.time()

        return None

    def update_datetime(self, file_path: Path, shot_dt: datetime, dry_run: bool) -> bool:
        if not self.available:
            raise RuntimeError("exiftool not available")

        dt_str = shot_dt.strftime("%Y:%m:%d %H:%M:%S")

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
            logger.debug("Running exiftool (write): %s", " ".join(cmd))
            return subprocess.run(cmd, capture_output=True, text=True, check=False)

        if dry_run:
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
            raise RuntimeError(f"exiftool failed after ffmpeg repair for {file_path}: {stderr_retry}")

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

    def get_existing_time(self, file_path: Path) -> Optional[time]:
        if not self.available:
            return None

        suffix = file_path.suffix.lower()
        if suffix not in {".jpg", ".jpeg"}:
            return None

        # Motion photos tend to be tricky; avoid piexif reads here.
        if "_MP" in file_path.stem.upper():
            return None

        import piexif  # type: ignore

        try:
            exif_dict = piexif.load(str(file_path))
        except Exception as exc:  # noqa: BLE001
            logger.debug("piexif load failed for %s: %s", file_path.name, exc)
            return None

        # Prefer DateTimeOriginal, then DateTimeDigitized, then 0th DateTime.
        candidates: list[bytes | None] = [
            exif_dict.get("Exif", {}).get(piexif.ExifIFD.DateTimeOriginal),
            exif_dict.get("Exif", {}).get(piexif.ExifIFD.DateTimeDigitized),
            exif_dict.get("0th", {}).get(piexif.ImageIFD.DateTime),
        ]

        for raw in candidates:
            if not raw:
                continue
            try:
                value = raw.decode(errors="ignore").strip()
                parsed = datetime.strptime(value[:19], "%Y:%m:%d %H:%M:%S")
                return parsed.time()
            except Exception:  # noqa: BLE001
                continue

        return None

    def update_datetime(self, file_path: Path, shot_dt: datetime, dry_run: bool) -> bool:
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

        dt_str = shot_dt.strftime("%Y:%m:%d %H:%M:%S")
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
            exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = dt_str.encode()
            exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = dt_str.encode()
            exif_dict["0th"][piexif.ImageIFD.DateTime] = dt_str.encode()

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

    acceptable_date_range: tuple[date, date]

    def __init__(self, prefer_piexif: bool = False) -> None:
        self.exiftool = ExifToolUpdater()
        self.piexif = PiexifUpdater()
        self.prefer_piexif = prefer_piexif
        self.acceptable_date_range = (date(2000, 1, 1), datetime.now().date())

    def get_existing_time(self, file_path: Path) -> Optional[time]:
        # Prefer exiftool reads if available, since it supports many formats (including mp4).
        if self.exiftool.available:
            return self.exiftool.get_existing_time(file_path)

        if self.piexif.available:
            return self.piexif.get_existing_time(file_path)

        return None

    def update_datetime(self, file_path: Path, shot_dt: datetime, dry_run: bool) -> bool:
        try:
            if not (self.acceptable_date_range[0] <= shot_dt.date() <= self.acceptable_date_range[1]):
                logger.warning(
                    "Shot date %s for %s is outside acceptable range %s - %s; skipping update.",
                    shot_dt.date(),
                    file_path.name,
                    self.acceptable_date_range[0],
                    self.acceptable_date_range[1],
                )
                return False

            if self.prefer_piexif and self.piexif.available:
                try:
                    return self.piexif.update_datetime(file_path, shot_dt, dry_run)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("piexif failed for %s: %s; trying exiftool", file_path.name, exc)

            if self.exiftool.available:
                self.exiftool.update_datetime(file_path, shot_dt, dry_run)
                return True

            if self.piexif.available:
                return self.piexif.update_datetime(file_path, shot_dt, dry_run)

            logger.warning("No metadata tool available for %s; EXIF not updated.", file_path.name)
        except RuntimeError as rexc:
            logger.warning("Metadata update failed for %s: %s", file_path.name, rexc)
        return False


# --------------------------------------------------------------------------------------
# File Moving
# --------------------------------------------------------------------------------------
class PhotoMover:
    """Finds, validates, updates, and moves photos to correct dated folders."""

    acceptable_date_range: tuple[date, date]
    mover: FileManager

    def __init__(self, config: AppConfig, updater: MetadataUpdater) -> None:
        self.config = config
        self.updater = updater
        self.acceptable_date_range = (date(2000, 1, 1), datetime.now().date())
        self.mover = FileManager(dry_run=config.dry_run, directory=self.config.base_directory)

    def scan_files(self) -> Iterable[Path]:
        """Yield candidate files under base_directory (bounded by max_depth)."""
        directory_to_sort = self.config.directory_to_sort or self.config.base_directory
        max_depth = self.config.max_depth
        logger.info("Scanning files...")

        allowed_suffixes = {".jpg", ".jpeg", ".png", ".arw", ".nef", ".dng", ".mp4", ".psd", ".tif", ".tiff"}
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

            if path.suffix.lower() not in allowed_suffixes:
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
            year == shot_date.year
            and day == shot_date.strftime("%Y-%m-%d")
            and file_path.parent == exp_dir
        )

    def _ensure_unique_destination(self, destination: Path) -> Path:
        if not destination.exists():
            return destination
        if self.config.skip_existing:
            raise FileExistsError(f"Destination exists: {destination}")

        stem = destination.stem
        suffix = destination.suffix
        parent = destination.parent
        index = 1
        while True:
            candidate = parent / f"{stem}-{index}{suffix}"
            if not candidate.exists():
                return candidate
            index += 1

    @staticmethod
    def _set_file_times(file_path: Path, shot_dt: datetime, dry_run: bool) -> None:
        # Set atime/mtime to the resolved datetime (local naive).
        ts = shot_dt.timestamp()
        if dry_run:
            return
        os.utime(file_path, (ts, ts), follow_symlinks=False)

    def _resolve_shot_datetime(self, file_path: Path, parsed: ParsedFilenameDatetime) -> datetime:
        """
        Resolve final datetime:
        - If filename provides HMS -> use it
        - Else attempt to pull HMS from existing metadata
        - Else default to 00:00:00 (warn)
        """
        if parsed.shot_time is not None:
            return datetime.combine(parsed.shot_date, parsed.shot_time)

        existing_time = self.updater.get_existing_time(file_path)
        if existing_time is not None:
            return datetime.combine(parsed.shot_date, existing_time)

        logger.warning(
            "No time-of-day in filename or metadata; defaulting to 00:00:00 for %s",
            file_path.name,
        )
        return datetime.combine(parsed.shot_date, time.min)

    def process(self) -> tuple[int, int]:
        """Process all candidate files. Returns tuple: (checked, moved)."""
        moved = 0
        checked = 0
        errors = 0

        if self.mover.is_same_filesystem(self.config.base_directory, self.config.directory_to_sort or self.config.base_directory):
            logger.info("Moves will be atomic.")
        else:
            logger.info("Moving across Filesystems. Moves will be slow.")
            
        with alive_bar(title="Processing", dual_line=True, unknown="waves") as bar:
            def progress_text(message: str, log_level: int | None = None) -> None:
                bar.text(f"({moved} →/{errors} E/{checked} ✓) {message}")
                if log_level is None:
                    return
                if log_level == logging.INFO:
                    logger.info(message)
                elif log_level == logging.WARNING:
                    logger.warning(message)
                elif log_level == logging.ERROR:
                    logger.error(message)
                elif log_level == logging.DEBUG:
                    logger.debug(message)

            for file_path in self.scan_files():
                try:
                    checked += 1
                    filename = file_path.name

                    parsed = FilenameParser.parse_datetime(filename)
                    if parsed is None:
                        progress_text(f"No date in filename: {filename}", log_level=logging.DEBUG)
                        continue

                    if not (self.acceptable_date_range[0] <= parsed.shot_date <= self.acceptable_date_range[1]):
                        progress_text(
                            (
                                f"Shot date {parsed.shot_date} for {filename} is outside acceptable range "
                                f"{self.acceptable_date_range[0]} - {self.acceptable_date_range[1]}; skipping."
                            ),
                            log_level=logging.INFO,
                        )
                        continue

                    if self.is_correct_location(file_path, parsed.shot_date):
                        progress_text(f"Already in correct location: {file_path}", log_level=logging.DEBUG)
                        continue

                    shot_dt = self._resolve_shot_datetime(file_path, parsed)

                    # Update metadata (best effort)
                    try:
                        self.updater.update_datetime(file_path, shot_dt, self.config.dry_run)
                    except (OSError, PermissionError) as exc:  # noqa: BLE001
                        errors += 1
                        progress_text(f"Metadata update failed for {filename}: {exc}", log_level=logging.WARNING)

                    # Update filesystem times (best effort)
                    try:
                        self._set_file_times(file_path, shot_dt, self.config.dry_run)
                    except (OSError, PermissionError) as exc:  # noqa: BLE001
                        errors += 1
                        progress_text(f"Failed to set file times for {filename}: {exc}", log_level=logging.WARNING)

                    # Compute destination and move
                    dest_dir = self._expected_dir(self.config.base_directory, parsed.shot_date)
                    destination = dest_dir / filename

                    try:
                        destination = self._ensure_unique_destination(destination)
                        progress_text(f"Moving to: {destination}", log_level=logging.DEBUG)
                        self.move(file_path, destination)
                        moved += 1
                    except FileExistsError as exc:
                        progress_text(f"Skipping (exists): {exc}", log_level=logging.DEBUG)

                finally:
                    bar()

        return checked, moved

    def move(self, source: Path, destination: Path) -> None:
        """Move file from source to destination."""
        if self.config.dry_run:
            logger.debug("Dry-run: would move %s -> %s", source, destination)
            return
        self.mover.move_file(source, destination)
        logger.debug("Moved %s -> %s", source, destination)


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------
def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Find photos with date-encoded filenames not in the correct folder, fix metadata, and move."
    )
    parser.add_argument(
        "base_directory",
        type=Path,
        help="Root Photos directory (e.g., /mnt/i/Photos).",
    )
    parser.add_argument(
        "--directory-to-sort",
        type=Path,
        default=None,
        help="Directory to scan and fix. By default, same as base_directory.",
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
        except ValidationError as exc:
            logger.error("Invalid configuration: %s", exc)
            return 2

        updater = CompositeUpdater(prefer_piexif=config.prefer_piexif)
        mover = PhotoMover(config, updater)
        checked, moved = mover.process()

        logger.info(
            "Done. Checked: %s, Moved: %s%s",
            checked,
            moved,
            " (dry-run)" if config.dry_run else "",
        )
        return 0

    except KeyboardInterrupt:
        logger.warning("Interrupted by user.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
