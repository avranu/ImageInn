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
suffix is 1-2 digits (so it will NOT confuse timestamps like "-094625" as a dup suffix).

If the group has an "original" (no trailing suffix), it keeps that; otherwise it keeps the
lowest-suffix filename in the group.

Only deletes a candidate if its SHA-256 checksum matches the kept file's checksum.

Python: 3.12
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import logging
import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Protocol

from alive_progress import alive_bar

logger = logging.getLogger(__name__)

# Only treat the trailing "-N" or "-N-M" as a duplicate marker when N/M are 1–2 digits.
# This avoids stripping timestamp parts like "-094625".
_DUP_SUFFIX_RE = re.compile(
    r"^(?P<base>.+?)(?:[-_\s(]+(?P<n1>\d{1,2})[)\s]*(?:[-_\s(]+(?P<n2>\d{1,2})[)\s]*)?)$"
)


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
      2) Then prefer smaller numeric suffixes
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
    return (1, n1 * 1_000_000 + n2, path.name)


def _default_workers() -> int:
    cpu_count = os.cpu_count() or 4
    # Hashing is usually a mix of IO + C-accelerated hashing; threads often help.
    return min(32, cpu_count * 2)


@dataclass(frozen=True, slots=True)
class CleanerConfig:
    root: Path
    recursive: bool
    dry_run: bool
    hasher: Hasher
    verbose: bool
    workers: int


class DuplicateVariantCleaner:
    """Cleans duplicate numbered variants in a directory tree."""

    def __init__(self, config: CleanerConfig) -> None:
        self._config = config
        self._checksum_cache: dict[Path, str] = {}
        self._checksum_lock = threading.Lock()

    def _compute_checksum(self, path: Path) -> str:
        """
        Compute checksum with a threadsafe cache.

        Raises:
            OSError: If the file cannot be read.
        """
        with self._checksum_lock:
            cached = self._checksum_cache.get(path)
        if cached is not None:
            return cached

        checksum = self._config.hasher.checksum(path)

        with self._checksum_lock:
            self._checksum_cache[path] = checksum
        return checksum

    def run(self) -> int:
        root = self._config.root
        if not root.exists():
            logger.error("Path does not exist: %s", root)
            return 2
        if not root.is_dir():
            logger.error("Path is not a directory: %s", root)
            return 2

        groups: dict[tuple[Path, str, str], list[Path]] = {}
        logger.debug("Scanning files under %s...", root)
        with alive_bar(title="Scanning", unit="files", unknown="waves") as bar:
            for file_path in _iter_files(root, recursive=self._config.recursive):
                groups.setdefault(_group_key_for(file_path), []).append(file_path)
                bar()

        if not groups:
            logger.info("No files found under %s", root)
            return 0

        # Only hash files that are in groups with potential duplicates.
        files_to_hash: list[Path] = []
        for files in groups.values():
            if len(files) >= 2:
                files_to_hash.extend(files)

        if not files_to_hash:
            logger.info("No duplicate candidates found under %s", root)
            return 0

        # Deduplicate paths while preserving stability.
        seen: set[Path] = set()
        unique_files_to_hash: list[Path] = []
        for file_path in files_to_hash:
            if file_path in seen:
                continue
            seen.add(file_path)
            unique_files_to_hash.append(file_path)

        logger.info(
            "Hashing %d file(s) with %d worker(s)...",
            len(unique_files_to_hash),
            self._config.workers,
        )

        hash_failures: dict[Path, str] = {}

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self._config.workers,
            thread_name_prefix="hash",
        ) as executor, alive_bar(
            title="Hashing", unit="files", total=len(unique_files_to_hash)
        ) as bar:
            future_to_path = {
                executor.submit(self._compute_checksum, path): path for path in unique_files_to_hash
            }
            for future in concurrent.futures.as_completed(future_to_path):
                path = future_to_path[future]
                try:
                    future.result()
                except OSError as exc:
                    hash_failures[path] = str(exc)
                    logger.warning("Failed to hash %s: %s", path, exc)
                finally:
                    bar()

        deleted_count = 0
        kept_groups = 0
        skipped_groups = 0

        files_total = sum(len(items) for items in groups.values())
        logger.info("Processing %d file(s) in %d group(s)...", files_total, len(groups))

        with alive_bar(title="Processing", unit="files", total=files_total) as bar:
            for (_parent, base_stem, _ext_lower), files in groups.items():
                if len(files) < 2:
                    for _ in files:
                        bar()
                    continue

                # If any file in this group failed hashing, skip deletions for safety.
                if any(path in hash_failures for path in files):
                    skipped_groups += 1
                    logger.debug(
                        "Skipping base=%s due to hashing errors in group.",
                        base_stem,
                    )
                    for _ in files:
                        bar()
                    continue

                files_sorted = sorted(files, key=lambda p: _dup_rank(p, base_stem))
                kept_file = files_sorted[0]

                kept_checksum = self._checksum_cache.get(kept_file)
                if kept_checksum is None:
                    # Shouldn't happen (hashed earlier), but be safe.
                    try:
                        kept_checksum = self._compute_checksum(kept_file)
                    except OSError as exc:
                        logger.warning("Failed to hash kept file %s: %s", kept_file, exc)
                        skipped_groups += 1
                        for _ in files:
                            bar()
                        continue

                deletions: list[Path] = []
                mismatches: list[Path] = []

                for candidate in files_sorted[1:]:
                    candidate_checksum = self._checksum_cache.get(candidate)
                    if candidate_checksum is None:
                        try:
                            candidate_checksum = self._compute_checksum(candidate)
                        except OSError as exc:
                            logger.warning("Failed to hash candidate %s: %s", candidate, exc)
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
                    logger.debug(
                        "Not deleting for base=%s (kept=%s). %d mismatching candidate(s): %s",
                        base_stem,
                        kept_file.name,
                        len(mismatches),
                        ", ".join(p.name for p in mismatches[:8])
                        + ("..." if len(mismatches) > 8 else ""),
                    )
                    continue

                if not deletions:
                    kept_groups += 1
                    continue

                for delete_path in deletions:
                    if self._config.dry_run:
                        logger.debug("[dry-run] Would delete %s", delete_path)
                        deleted_count += 1
                        continue

                    try:
                        delete_path.unlink()
                        logger.debug("Deleted %s", delete_path)
                        deleted_count += 1
                    except OSError as exc:
                        logger.warning("Failed to delete %s: %s", delete_path, exc)

                kept_groups += 1

        logger.info(
            "Done. Kept groups: %d | Deleted files: %d | Skipped groups (mismatches/errors): %d",
            kept_groups,
            deleted_count,
            skipped_groups,
        )
        return 0


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
    parser.add_argument(
        "--workers",
        type=int,
        default=_default_workers(),
        help="Number of hashing threads (default: %(default)s).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    _configure_logging(verbose=args.verbose)

    if args.workers < 1:
        logger.error("--workers must be >= 1")
        return 2

    config = CleanerConfig(
        root=args.root,
        recursive=args.recursive,
        dry_run=args.dry_run,
        hasher=Sha256Hasher(),
        verbose=args.verbose,
        workers=args.workers,
    )
    return DuplicateVariantCleaner(config).run()


if __name__ == "__main__":
    raise SystemExit(main())
