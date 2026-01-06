from __future__ import annotations

import os
from pathlib import Path
import pytest

from scripts.monthly.organize.delete_duplicates import CleanerConfig, DuplicateVariantCleaner, Sha256Hasher


def _write(path: Path, content: bytes) -> None:
    path.write_bytes(content)


def test_deletes_identical_variants_multithreaded(tmp_path: Path) -> None:
    original = tmp_path / "PXL_20250103_182702167.MP~20250108-094004.jpg"
    _write(original, b"same")

    v1 = tmp_path / "PXL_20250103_182702167.MP~20250108-094004_0-2.jpg"
    v2 = tmp_path / "PXL_20250103_182702167.MP~20250108-094004_1-2.jpg"
    v3 = tmp_path / "PXL_20250103_182702167.MP~20250108-094004_0_4.jpg"
    v4 = tmp_path / "PXL_20250103_182702167.MP~20250108-094004_5_1.jpg"
    v5 = tmp_path / "PXL_20250103_182702167.MP~20250108-094004 (2).jpg"
    v6 = tmp_path / "PXL_20250103_182702167.MP~20250108-094004_0 (2).jpg"
    _write(v1, b"same")
    _write(v2, b"same")
    _write(v3, b"same")
    _write(v4, b"same")
    _write(v5, b"same")
    _write(v6, b"same")

    config = CleanerConfig(
        root=tmp_path,
        recursive=False,
        dry_run=False,
        hasher=Sha256Hasher(chunk_size_bytes=2),
        verbose=False,
        workers=4,
    )
    assert DuplicateVariantCleaner(config).run() == 0

    assert original.exists()
    assert not v1.exists()
    assert not v2.exists()
    assert not v3.exists()
    assert not v4.exists()
    assert not v5.exists()
    assert not v6.exists()

def test_does_not_delete_if_any_variant_differs(tmp_path: Path) -> None:
    original = tmp_path / "PXL_20250103_234246990.MP~20250108-094625.jpg"
    _write(original, b"same")

    v1 = tmp_path / "PXL_20250103_234246990.MP~20250108-094625-1.jpg"
    v2 = tmp_path / "PXL_20250103_234246990.MP~20250108-094625-1-1.jpg"
    v3 = tmp_path / "PXL_20250103_234246990.MP~20250108-094625-2.jpg"
    _write(v1, b"same")
    _write(v2, b"same")
    _write(v3, b"DIFFERENT")

    config = CleanerConfig(
        root=tmp_path,
        recursive=False,
        dry_run=False,
        hasher=Sha256Hasher(chunk_size_bytes=2),
        verbose=False,
        workers=4,
    )
    assert DuplicateVariantCleaner(config).run() == 0

    assert original.exists()
    assert v1.exists()
    assert v2.exists()
    assert v3.exists()

def test_does_not_delete_different_names(tmp_path: Path) -> None:
    original = tmp_path / "PXL_20250103_234246990.MP~20250108-094625.jpg"
    _write(original, b"same")

    v1 = tmp_path / "PXL_20250103_234246990.MP~20250108-094625-1.jpg"
    v2 = tmp_path / "DIFFERENT_NAME.jpg"
    _write(v1, b"same")
    _write(v2, b"same")

    config = CleanerConfig(
        root=tmp_path,
        recursive=False,
        dry_run=False,
        hasher=Sha256Hasher(chunk_size_bytes=2),
        verbose=False,
        workers=4,
    )
    assert DuplicateVariantCleaner(config).run() == 0

    assert original.exists()
    assert not v1.exists()
    assert v2.exists()

def test_does_not_delete_dry_run(tmp_path: Path) -> None:
    original = tmp_path / "PXL_20250103_182702167.MP~20250108-094004_0.jpg"
    _write(original, b"same")

    v1 = tmp_path / "PXL_20250103_182702167.MP~20250108-094004_0-2.jpg"
    v2 = tmp_path / "PXL_20250103_182702167.MP~20250108-094004_0-3-1.jpg"
    _write(v1, b"same")
    _write(v2, b"same")

    config = CleanerConfig(
        root=tmp_path,
        recursive=False,
        dry_run=True,
        hasher=Sha256Hasher(chunk_size_bytes=2),
        verbose=False,
        workers=4,
    )
    assert DuplicateVariantCleaner(config).run() == 0

    assert original.exists()
    assert v1.exists()
    assert v2.exists()

if __name__ == "__main__":
    pytest.main([os.path.abspath(__file__)])