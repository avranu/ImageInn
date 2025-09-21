import os
from datetime import date
from pathlib import Path

import pytest

from scripts.monthly.organize.fix_metadata import AppConfig, FilenameParser, PhotoMover, CompositeUpdater

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
def test_parse_date_ok(name, expected):
    assert FilenameParser.parse_date(name) == expected

@pytest.mark.parametrize(
    "name",
    [
        "IMG_20231_1.jpg",
        "signal-2023-13-40-foo.jpg",
        "random.jpg",
        "IMG_20231001.jpg",
    ],
)
def test_parse_date_fail(name):
    assert FilenameParser.parse_date(name) is None

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

if __name__ == "__main__":
    pytest.main([os.path.abspath(__file__)])