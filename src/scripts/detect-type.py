#!/usr/bin/env python3
"""
A script to inspect unknown files (e.g., interrupted video dumps) and guess their real type.

Features:
- MIME detection via python-magic
- File-signature heuristics for common video formats
- FFprobe probing (if ffprobe is installed)
- Binwalk scanning (if binwalk is installed)
- Hex + ASCII dump of header bytes
- Batch mode for directories
"""

import argparse
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any

try:
    import magic
except ImportError:
    magic = None  # type: ignore

LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


class FileTypeInspector:
    """Inspect a file to guess its type using multiple strategies."""

    HEADER_BYTES = 32

    def __init__(self, path: Path) -> None:
        """
        Args:
            path: A file or directory to inspect.
        """
        self.path = path

    def run(self) -> None:
        """Inspect the path (file or all files in a directory)."""
        if self.path.is_file():
            self.inspect(self.path)
        elif self.path.is_dir():
            for file in sorted(self.path.iterdir()):
                if file.is_file():
                    self.inspect(file)
        else:
            logger.error("Path %s is not valid", self.path)

    def inspect(self, file: Path) -> None:
        """
        Run all detection methods on a single file.

        Args:
            file: Path to the file.
        """
        logger.info("Inspecting %s", file)
        results: Dict[str, Any] = {}
        results["magic"] = self.detect_magic(file)
        results["header_heuristic"] = self.detect_by_header(file)
        results["signature_dump"] = self.dump_signature(file)
        results["ffprobe"] = self.probe_ffmpeg(file)
        results["binwalk"] = self.scan_binwalk(file)
        self.log_results(results)

    def detect_magic(self, file: Path) -> Optional[str]:
        """
        Detect MIME type via libmagic.

        Args:
            file: Path to the file.

        Returns:
            The MIME type string, or None if not available.
        """
        if magic:
            try:
                m = magic.Magic(mime=True)
                return m.from_file(str(file))
            except Exception as e:
                logger.warning("libmagic error on %s: %s", file, e)
        else:
            logger.warning("python-magic not installed; skipping MIME detection")
        return None

    def detect_by_header(self, file: Path) -> Optional[str]:
        """
        Inspect the first bytes for known video/container signatures.

        Args:
            file: Path to the file.

        Returns:
            A string guess (e.g., "video/mp4") or None.
        """
        try:
            data = file.read_bytes()[:self.HEADER_BYTES]
        except Exception as e:
            logger.error("Failed to read header of %s: %s", file, e)
            return None

        # MP4/MOV
        if len(data) >= 8 and data[4:8] == b"ftyp":
            brand = data[8:12].decode("ascii", errors="ignore")
            return f"video/mp4 (brand {brand})"
        # MKV/WebM
        if data.startswith(b"\x1A\x45\xDF\xA3"):
            return "video/x-matroska"
        # AVI
        if data.startswith(b"RIFF") and data[8:12] == b"AVI ":
            return "video/avi"
        # FLV
        if data.startswith(b"FLV"):
            return "video/x-flv"
        # MPEG-TS
        if data[:1] == b'\x47' and data[188:189] == b'\x47':
            return "video/mp2t"
        return None

    def dump_signature(self, file: Path) -> str:
        """
        Return a hex + ASCII dump of the first HEADER_BYTES.

        Args:
            file: Path to the file.

        Returns:
            A formatted string.
        """
        try:
            raw = file.read_bytes()[: self.HEADER_BYTES]
        except Exception as e:
            return f"Error reading bytes: {e}"

        hex_str = " ".join(f"{b:02x}" for b in raw)
        ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in raw)
        return f"HEX: {hex_str}\nASCII: {ascii_str}"

    def probe_ffmpeg(self, file: Path) -> Optional[Dict[str, Any]]:
        """
        Run ffprobe to get format and stream info.

        Args:
            file: Path to the file.

        Returns:
            Parsed JSON info, or None if ffprobe is unavailable or fails.
        """
        if not shutil.which("ffprobe"):
            return None
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(file),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
            import json

            return json.loads(proc.stdout)
        except subprocess.CalledProcessError as e:
            logger.debug("ffprobe failed on %s: %s", file, e.stderr.strip())
        except Exception as e:
            logger.warning("Error running ffprobe on %s: %s", file, e)
        return None

    def scan_binwalk(self, file: Path) -> Optional[str]:
        """
        Run binwalk to search for known embedded signatures.

        Args:
            file: Path to the file.

        Returns:
            The raw binwalk output, or None.
        """
        if not shutil.which("binwalk"):
            return None
        try:
            proc = subprocess.run(
                ["binwalk", "--quiet", "--summary", str(file)],
                capture_output=True,
                text=True,
                check=True,
            )
            return proc.stdout.strip()
        except subprocess.CalledProcessError as e:
            logger.debug("binwalk error on %s: %s", file, e.stderr.strip())
        except Exception as e:
            logger.warning("Error running binwalk on %s: %s", file, e)
        return None

    def log_results(self, results: Dict[str, Any]) -> None:
        """
        Log a summary of all findings.

        Args:
            results: Dictionary of detection outputs.
        """
        logger.info("  MIME via magic: %s", results.get("magic") or "n/a")
        logger.info("  Header heuristic: %s", results.get("header_heuristic") or "n/a")
        logger.info("  Signature dump:\n%s", results.get("signature_dump"))
        if results.get("ffprobe") is not None:
            logger.info("  ffprobe format: %s", results["ffprobe"].get("format", {}).get("format_name"))
        else:
            logger.info("  ffprobe: n/a")
        if results.get("binwalk") is not None:
            logger.info("  binwalk summary:\n%s", results["binwalk"])
        else:
            logger.info("  binwalk: n/a")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Detect probable file types of unknown files"
    )
    parser.add_argument(
        "path", type=Path, help="File or directory to inspect"
    )
    return parser.parse_args()


def main() -> None:
    """Entry point."""
    args = parse_args()
    inspector = FileTypeInspector(args.path)
    inspector.run()


if __name__ == "__main__":
    main()
