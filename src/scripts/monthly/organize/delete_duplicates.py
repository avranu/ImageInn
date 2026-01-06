#!/usr/bin/env python3
"""
Delete duplicate "-1", "-2", "-1-1" variants when they are byte-identical.

Targets filenames like:
  PXL_20250103_234246990.MP~20250108-094625.jpg
  PXL_20250103_234246990.MP~20250108-094625-1.jpg
  PXL_20250103_234246990.MP~20250108-094625-1-1.jpg
  PXL_20250103_182702167.MP~20250108-094004_0.jpg
  PXL_20250103_182702167.MP~20250108-094004_0-2.jpg

It groups files by stripping a trailing "-<digits>" or "-<digits>-<digits>" where each
suffix is 1–2 digits (so it will NOT confuse timestamps like "-094625" as a dup suffix).

If the group has an "original" (no trailing suffix), it keeps that; otherwise it keeps the
lowest-suffix filename in the group.

Only deletes a candidate if its SHA-256 checksum matches the kept file's checksum.

Python: 3.12
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from alive_progress import alive_bar
from typing import Iterator, Protocol

LOGGER = logging.getLogger(__name__)

# Only treat the trailing "-N" or "-N-M" as a duplicate marker when N/M are 1–2 digits.
# This avoids stripping timestamp parts like "-094625".
_DUP_SUFFIX_RE = re.compile(r"^(?P<base>.+?)(?:[-_](?P<n1>\d{1,2})(?:[-_](?P<n2>\d{1,2}))?)$")


class Hasher(Protocol):
    """Hasher interface for file checksumming."""

    def checksum(self, path: Path) -> str:
        """Return a hex digest for the given file."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class Sha256Hasher:
    """SHA-256 hasher (streaming)."""

    chunk_size_bytes: int = 8 * 1024 * 1024

    def checksum(self, path: Path) -> str:
        hasher = hashlib.sha256()
        with path.open("rb") as file_handle:
            while True:
                chunk = file_handle.read(self.chunk_size_bytes)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()


def _iter_files(root: Path, recursive: bool) -> Iterator[Path]:
    if recursive:
        yield from (p for p in root.rglob("*") if p.is_file())
        return
    yield from (p for p in root.iterdir() if p.is_file())


def _group_key_for(path: Path) -> tuple[Path, str, str]:
    """
    Groups by:
      (parent_directory, base_stem_without_dup_suffix, extension_lower)
    """
    stem = path.stem
    match = _DUP_SUFFIX_RE.match(stem)
    base = match.group("base") if match else stem
    return (path.parent, base, path.suffix.lower())


def _dup_rank(path: Path, base_stem: str) -> tuple[int, int, str]:
    """
    Sort key for selecting the kept file when no "original" exists.

    Lower is better:
      1) Prefer the file whose stem exactly equals base_stem
      2) Then prefer smaller numeric suffixes (e.g., -1 before -2, -2 before -10, -2 before -2-1)
      3) Tie-break by filename
    """
    stem = path.stem
    if stem == base_stem:
        return (0, 0, path.name)

    match = _DUP_SUFFIX_RE.match(stem)
    if not match:
        return (2_000_000_000, 2_000_000_000, path.name)

    n1 = int(match.group("n1") or 2_000_000_000)
    n2 = int(match.group("n2") or 0)
    # Combine for stable ordering across single/double suffix forms.
    return (1, n1 * 1_000_000 + n2, path.name)


@dataclass(frozen=True, slots=True)
class CleanerConfig:
    root: Path
    recursive: bool
    dry_run: bool
    hasher: Hasher
    verbose: bool


class DuplicateVariantCleaner:
    """Cleans duplicate numbered variants in a directory tree."""

    def __init__(self, config: CleanerConfig) -> None:
        self._config = config

    def run(self) -> int:
        root = self._config.root
        if not root.exists():
            LOGGER.error("Path does not exist: %s", root)
            return 2
        if not root.is_dir():
            LOGGER.error("Path is not a directory: %s", root)
            return 2

        groups: dict[tuple[Path, str, str], list[Path]] = {}
        LOGGER.info("Scanning files under %s...", root)
        with alive_bar(title="Scanning", unit="files", unknown="waves") as bar:
            for file_path in _iter_files(root, recursive=self._config.recursive):
                groups.setdefault(_group_key_for(file_path), []).append(file_path)
                bar()
        if not groups:
            LOGGER.info("No files found under %s", root)
            return 0

        checksum_cache: dict[Path, str] = {}

        deleted_count = 0
        kept_groups = 0
        skipped_groups = 0

        files_total = sum(len(items) for items in groups.values())
        LOGGER.info("Processing %d file(s) in %d group(s)...", files_total, len(groups))

        with alive_bar(title="Processing", unit="files", total=files_total) as bar:
            for (_parent, base_stem, _ext_lower), files in groups.items():
                try:
                    if len(files) < 2:
                        for _ in files:
                            bar()
                        continue

                    files_sorted = sorted(files, key=lambda p: _dup_rank(p, base_stem))
                    kept_file = files_sorted[0]

                    try:
                        kept_checksum = checksum_cache.get(kept_file)
                        if kept_checksum is None:
                            kept_checksum = self._config.hasher.checksum(kept_file)
                            checksum_cache[kept_file] = kept_checksum
                    except OSError as exc:
                        LOGGER.warning("Failed to hash kept file %s: %s", kept_file, exc)
                        skipped_groups += 1
                        for _ in files:
                            bar()
                        continue

                    deletions: list[Path] = []
                    mismatches: list[Path] = []

                    for candidate in files_sorted[1:]:
                        try:
                            candidate_checksum = checksum_cache.get(candidate)
                            if candidate_checksum is None:
                                candidate_checksum = self._config.hasher.checksum(candidate)
                                checksum_cache[candidate] = candidate_checksum
                        except OSError as exc:
                            LOGGER.warning("Failed to hash candidate %s: %s", candidate, exc)
                            mismatches.append(candidate)
                            bar()
                            continue

                        if candidate_checksum == kept_checksum:
                            deletions.append(candidate)
                        else:
                            mismatches.append(candidate)
                        bar()

                    # Count the kept file in progress.
                    bar()

                    if mismatches:
                        skipped_groups += 1
                        LOGGER.info(
                            "Not deleting for base=%s (kept=%s). %d mismatching candidate(s): %s",
                            base_stem,
                            kept_file.name,
                            len(mismatches),
                            ", ".join(p.name for p in mismatches[:8]) + ("..." if len(mismatches) > 8 else ""),
                        )
                        continue

                    if not deletions:
                        kept_groups += 1
                        continue

                    for delete_path in deletions:
                        if self._config.dry_run:
                            LOGGER.info("[dry-run] Would delete %s", delete_path)
                            deleted_count += 1
                            continue

                        try:
                            delete_path.unlink()
                            LOGGER.info("Deleted %s", delete_path)
                            deleted_count += 1
                        except OSError as exc:
                            LOGGER.warning("Failed to delete %s: %s", delete_path, exc)

                    kept_groups += 1
                finally:
                    pass

        LOGGER.info(
            "Done. Kept groups: %d | Deleted files: %d | Skipped groups (mismatches/errors): %d",
            kept_groups,
            deleted_count,
            skipped_groups,
        )
        return 0


def _progress_bar(total: int):
    try:
        from tqdm import tqdm  # type: ignore

        return tqdm(total=total, unit="file")
    except Exception:  # pragma: no cover
        return _BasicProgress(total=total)


class _BasicProgress:
    def __init__(self, total: int) -> None:
        self._total = max(total, 1)
        self._done = 0

    def update(self, n: int) -> None:
        self._done += n
        if self._done % 250 == 0 or self._done >= self._total:
            percent = int(self._done * 100 / self._total)
            sys.stderr.write(f"\rProgress: {percent:3d}% ({self._done}/{self._total})")
            sys.stderr.flush()

    def close(self) -> None:
        sys.stderr.write("\n")
        sys.stderr.flush()


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Delete numbered -1/-2/-1-1 variants when checksums match the kept original."
    )
    parser.add_argument("root", type=Path, help="Directory to scan.")
    parser.add_argument("--recursive", action="store_true", help="Recurse into subdirectories.")
    parser.add_argument("--dry-run", action="store_true", help="Log what would be deleted, but do not delete.")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    _configure_logging(verbose=args.verbose)

    config = CleanerConfig(
        root=args.root,
        recursive=args.recursive,
        dry_run=args.dry_run,
        hasher=Sha256Hasher(),
        verbose=args.verbose,
    )
    return DuplicateVariantCleaner(config).run()


if __name__ == "__main__":
    raise SystemExit(main())
