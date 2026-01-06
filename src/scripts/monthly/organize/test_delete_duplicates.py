from __future__ import annotations

from pathlib import Path
import pytest

from scripts.monthly.organize.delete_duplicates import CleanerConfig, DuplicateVariantCleaner, Sha256Hasher


def _write(path: Path, content: bytes) -> None:
    path.write_bytes(content)


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
    )
    assert DuplicateVariantCleaner(config).run() == 0

    assert original.exists()
    assert v1.exists()
    assert v2.exists()
    assert v3.exists()


def test_deletes_identical_variants(tmp_path: Path) -> None:
    original = tmp_path / "PXL_20250103_182702167.MP~20250108-094004_0.jpg"
    _write(original, b"same")

    v1 = tmp_path / "PXL_20250103_182702167.MP~20250108-094004_0-2.jpg"
    v2 = tmp_path / "PXL_20250103_182702167.MP~20250108-094004_0-3-1.jpg"
    _write(v1, b"same")
    _write(v2, b"same")

    config = CleanerConfig(
        root=tmp_path,
        recursive=False,
        dry_run=False,
        hasher=Sha256Hasher(chunk_size_bytes=2),
        verbose=False,
    )
    assert DuplicateVariantCleaner(config).run() == 0

    assert original.exists()
    assert not v1.exists()
    assert not v2.exists()


def test_keeps_lowest_suffix_when_no_original_exists(tmp_path: Path) -> None:
    a = tmp_path / "foo~20250108-094625-2.jpg"
    b = tmp_path / "foo~20250108-094625-10.jpg"
    c = tmp_path / "foo~20250108-094625-2-1.jpg"
    _write(a, b"x")
    _write(b, b"x")
    _write(c, b"x")

    config = CleanerConfig(
        root=tmp_path,
        recursive=False,
        dry_run=False,
        hasher=Sha256Hasher(chunk_size_bytes=2),
        verbose=False,
    )
    assert DuplicateVariantCleaner(config).run() == 0

    assert a.exists()
    assert not b.exists()
    assert not c.exists()

if __name__ == "__main__":
    pytest.main([__file__])