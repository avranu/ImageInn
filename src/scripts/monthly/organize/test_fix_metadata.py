from __future__ import annotations

import os
from datetime import datetime, date, time
from pathlib import Path
from typing import Optional

import pytest

from scripts.monthly.organize.fix_metadata import AppConfig, FilenameParser, PhotoMover, CompositeUpdater, ParsedFilenameDatetime

class DummyUpdater(CompositeUpdater):
    def __init__(self):
        super().__init__(prefer_piexif=False)
        # Override to avoid touching real tools
        self.exiftool._available = False
        self.piexif._available = False

    def update_dates(self, file_path: Path, shot_date: date, dry_run: bool) -> None:
        # no-op to keep tests hermetic
        return

def touch_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"test")

@pytest.mark.parametrize(
    "name,expected",
    [
        ("IMG_20231001_123456.jpg", date(2023, 10, 1)),
        ("PXL_20240229_999999.DNG", date(2024, 2, 29)),  # leap year
        ("dji_fly_20211231_000001.PNG", date(2021, 12, 31)),
        ("PSX_20230115_000001.jpeg", date(2023, 1, 15)),
        ("Manly_20221201_1.arw", date(2022, 12, 1)),
        ("signal-2023-10-01-foo.jpg", date(2023, 10, 1)),
        ("signal-2021-01-09-bar.png", date(2021, 1, 9)),
    ],
)
def test_parse_datetime_ok(name, expected):
    parsed = FilenameParser.parse_datetime(name)
    assert parsed.shot_date == expected

@pytest.mark.parametrize(
    "name",
    [
        "IMG_20231_1.jpg",
        "signal-2023-13-40-foo.jpg",
        "random.jpg",
        "IMG_20231001.jpg",
    ],
)
def test_parse_datetime_fail(name):
    assert FilenameParser.parse_datetime(name) is None

def test_move_when_wrong_location(tmp_path: Path, monkeypatch):
    base = tmp_path / "Photos"
    wrong_dir = base / "2023" / "2023-10-02"
    right_dir = base / "2023" / "2023-10-01"
    fname = "IMG_20231001_000001.jpg"
    src = wrong_dir / fname
    touch_file(src)

    cfg = AppConfig(base_directory=base, dry_run=False, skip_existing=False, prefer_piexif=False, max_depth=6, verbose=True)
    mover = PhotoMover(cfg, DummyUpdater())

    checked, moved = mover.process()
    assert moved == 1
    assert (right_dir / fname).exists()
    assert not src.exists()

def test_skip_existing_collision(tmp_path: Path):
    base = tmp_path / "Photos"
    wrong_dir = base / "2023" / "2023-10-02"
    right_dir = base / "2023" / "2023-10-01"
    fname = "IMG_20231001_000001.jpg"
    src = wrong_dir / fname
    dst = right_dir / fname

    touch_file(src)
    touch_file(dst)

    cfg = AppConfig(base_directory=base, dry_run=False, skip_existing=True, prefer_piexif=False, max_depth=6, verbose=False)
    mover = PhotoMover(cfg, DummyUpdater())

    checked, moved = mover.process()
    # Should skip due to --skip-existing
    assert moved == 0
    assert src.exists()
    assert dst.exists()

def test_autorename_on_collision(tmp_path: Path):
    base = tmp_path / "Photos"
    wrong_dir = base / "2023" / "2023-10-02"
    right_dir = base / "2023" / "2023-10-01"
    fname = "IMG_20231001_000001.jpg"
    src = wrong_dir / fname
    dst = right_dir / fname

    touch_file(src)
    touch_file(dst)

    cfg = AppConfig(base_directory=base, dry_run=False, skip_existing=False, prefer_piexif=False, max_depth=6, verbose=False)
    mover = PhotoMover(cfg, DummyUpdater())

    _, moved = mover.process()
    # Should create "-1" alongside the existing file
    assert moved == 1
    assert (right_dir / "IMG_20231001_000001-1.jpg").exists()


class FakeUpdater:
    """Minimal updater stub for testing time preservation logic."""

    def __init__(self, existing_time: Optional[time]) -> None:
        self._existing_time = existing_time
        self.updated: list[tuple[Path, datetime]] = []

    def get_existing_time(self, file_path: Path) -> Optional[time]:
        return self._existing_time

    def update_datetime(self, file_path: Path, shot_dt: datetime, dry_run: bool) -> bool:
        self.updated.append((file_path, shot_dt))
        return True


def test_filename_parser_prefix_compact_with_millis_time() -> None:
    parsed = FilenameParser.parse_datetime("PXL_20240422_002405682.mp4")
    assert parsed is not None
    assert parsed.shot_date == date(2024, 4, 22)
    assert parsed.shot_time == time(0, 24, 5)


def test_filename_parser_prefix_compact_date_only() -> None:
    parsed = FilenameParser.parse_datetime("IMG_20240101_1.jpg")
    assert parsed is not None
    assert parsed.shot_date == date(2024, 1, 1)
    assert parsed.shot_time is None


def test_filename_parser_dash_date_with_hms_digits() -> None:
    parsed = FilenameParser.parse_datetime("2024-01-02-153045.jpg")
    assert parsed is not None
    assert parsed.shot_date == date(2024, 1, 2)
    assert parsed.shot_time == time(15, 30, 45)


def test_filename_parser_signal_with_separated_time() -> None:
    parsed = FilenameParser.parse_datetime("signal-2024-01-02-15-30-45.jpg")
    assert parsed is not None
    assert parsed.shot_date == date(2024, 1, 2)
    assert parsed.shot_time == time(15, 30, 45)


def test_resolve_datetime_uses_filename_time_when_present(tmp_path: Path) -> None:
    config = AppConfig(base_directory=tmp_path, dry_run=True, max_depth=2)
    updater = FakeUpdater(existing_time=time(9, 8, 7))
    mover = PhotoMover(config, updater)  # type: ignore[arg-type]

    file_path = tmp_path / "x.jpg"
    parsed = ParsedFilenameDatetime(shot_date=date(2024, 1, 1), shot_time=time(1, 2, 3))
    resolved = mover._resolve_shot_datetime(file_path, parsed)
    assert resolved == datetime(2024, 1, 1, 1, 2, 3)


def test_resolve_datetime_preserves_metadata_time_when_filename_time_missing(tmp_path: Path) -> None:
    config = AppConfig(base_directory=tmp_path, dry_run=True, max_depth=2)
    updater = FakeUpdater(existing_time=time(9, 8, 7))
    mover = PhotoMover(config, updater)  # type: ignore[arg-type]

    file_path = tmp_path / "x.jpg"
    parsed = ParsedFilenameDatetime(shot_date=date(2024, 1, 1), shot_time=None)
    resolved = mover._resolve_shot_datetime(file_path, parsed)
    assert resolved == datetime(2024, 1, 1, 9, 8, 7)


def test_resolve_datetime_defaults_to_midnight_when_no_time_anywhere(tmp_path: Path) -> None:
    config = AppConfig(base_directory=tmp_path, dry_run=True, max_depth=2)
    updater = FakeUpdater(existing_time=None)
    mover = PhotoMover(config, updater)  # type: ignore[arg-type]

    file_path = tmp_path / "x.jpg"
    parsed = ParsedFilenameDatetime(shot_date=date(2024, 1, 1), shot_time=None)
    resolved = mover._resolve_shot_datetime(file_path, parsed)
    assert resolved == datetime(2024, 1, 1, 0, 0, 0)

if __name__ == "__main__":
    pytest.main([os.path.abspath(__file__)])