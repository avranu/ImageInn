#!/usr/bin/env python3
"""
A script to inspect “unknown” files (e.g. interrupted video dumps) and guess their real type.

Features:
- MIME detection via python-magic
- File-signature heuristics for common containers (MP4/MOV, MKV/WebM, AVI, FLV, TS)
- Deep scan for those signatures anywhere in the file
- FFprobe probing (if ffprobe is installed)
- Binwalk scanning (if binwalk is installed)
- File size and zero-filled detection
- Hex + ASCII dump of the first HEADER_BYTES
- Batch mode for directories
"""

import argparse
import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    SCAN_CHUNK = 1024 * 1024  # 1 MB
    SIGNATURES = {
        "MP4 (ftyp)": b"ftyp",
        "Matroska (1A45DFA3)": b"\x1A\x45\xDF\xA3",
        "AVI (RIFF…AVI )": b"AVI ",
        "FLV": b"FLV",
        "MPEG-TS (sync byte)": b"\x47",
        "JPEG (FFD8FFE0)": b"\xFF\xD8\xFF\xE0",
        "PNG": b"\x89PNG",
        "ZIP (PK)": b"PK\x03\x04",
    }

    def __init__(self, path: Path) -> None:
        self.path = path

    def run(self) -> None:
        """Inspect either a single file or all files in a directory."""
        if self.path.is_file():
            self.inspect(self.path)
        elif self.path.is_dir():
            for file in sorted(self.path.iterdir()):
                if file.is_file():
                    self.inspect(file)
        else:
            logger.error("Invalid path: %s", self.path)

    def inspect(self, file: Path) -> None:
        """Run all detection methods on a single file."""
        logger.info("=== Inspecting %s ===", file)
        logger.info("Size: %d bytes", file.stat().st_size)
        if self.is_all_zeros(file):
            logger.warning("File appears to be all zero bytes; likely unrecoverable or empty.")
        logger.info("MIME via magic: %s", self.detect_magic(file) or "n/a")
        logger.info("Header heuristic: %s", self.detect_by_header(file) or "n/a")
        logger.info("Deep signature scan: %s", self.deep_signature_scan(file) or "n/a")
        dump = self.dump_signature(file)
        logger.info("Signature dump (first %d bytes):\n%s", self.HEADER_BYTES, dump)
        ff = self.probe_ffmpeg(file)
        logger.info("ffprobe: %s", ff.get("format", {}).get("format_name") if ff else "n/a")
        bw = self.scan_binwalk(file)
        logger.info("binwalk: %s", bw.strip() if bw else "n/a")

    def detect_magic(self, file: Path) -> Optional[str]:
        if magic:
            try:
                m = magic.Magic(mime=True)
                return m.from_file(str(file))
            except Exception as e:
                logger.debug("libmagic error: %s", e)
        return None

    def detect_by_header(self, file: Path) -> Optional[str]:
        try:
            data = file.read_bytes()[: self.HEADER_BYTES]
        except Exception as e:
            logger.error("Header read error: %s", e)
            return None

        # MP4/MOV
        if len(data) >= 8 and data[4:8] == b"ftyp":
            brand = data[8:12].decode("ascii", errors="ignore")
            return f"video/mp4 (brand={brand})"
        # Matroska/WebM
        if data.startswith(self.SIGNATURES["Matroska (1A45DFA3)"]):
            return "video/x-matroska"
        # AVI
        if data.startswith(b"RIFF") and data[8:12] == b"AVI ":
            return "video/avi"
        # FLV
        if data.startswith(b"FLV"):
            return "video/x-flv"
        # TS (sync bytes at fixed interval)
        if data.startswith(b"\x47") and data[188:189] == b"\x47":
            return "video/mp2t"
        return None

    def deep_signature_scan(self, file: Path) -> Optional[List[str]]:
        """Scan the entire file in chunks for any known signature."""
        found: List[str] = []
        try:
            with file.open("rb") as fp:
                window = b""
                while True:
                    chunk = fp.read(self.SCAN_CHUNK)
                    if not chunk:
                        break
                    window += chunk
                    # only keep last len(longest signature) - 1 bytes
                    max_sig = max(len(s) for s in self.SIGNATURES.values())
                    if len(window) > self.SCAN_CHUNK + max_sig:
                        window = window[-max_sig:]
                    for name, sig in self.SIGNATURES.items():
                        if sig in window and name not in found:
                            found.append(name)
                return found if found else None
        except Exception as e:
            logger.error("Deep scan error: %s", e)
            return None

    def dump_signature(self, file: Path) -> str:
        try:
            raw = file.read_bytes()[: self.HEADER_BYTES]
        except Exception as e:
            return f"<error reading bytes: {e}>"
        hex_str = " ".join(f"{b:02x}" for b in raw)
        ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in raw)
        return f"HEX: {hex_str}\nASCII: {ascii_str}"

    def probe_ffmpeg(self, file: Path) -> Optional[Dict[str, Any]]:
        if not shutil.which("ffprobe"):
            return None
        cmd = [
            "ffprobe", "-v", "error",
            "-print_format", "json",
            "-show_format", "-show_streams",
            str(file)
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return json.loads(proc.stdout)
        except subprocess.CalledProcessError:
            return None

    def scan_binwalk(self, file: Path) -> Optional[str]:
        if not shutil.which("binwalk"):
            return None
        try:
            proc = subprocess.run(
                ["binwalk", "--quiet", "--summary", str(file)],
                capture_output=True,
                text=True,
                check=True
            )
            return proc.stdout
        except subprocess.CalledProcessError:
            return None

    def is_all_zeros(self, file: Path) -> bool:
        """Return True if the entire file is just zero bytes."""
        try:
            with file.open("rb") as fp:
                while True:
                    chunk = fp.read(self.SCAN_CHUNK)
                    if not chunk:
                        break
                    if any(b != 0 for b in chunk):
                        return False
            return True
        except Exception:
            return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect probable file types of unknown files")
    parser.add_argument("path", type=Path, help="File or directory to inspect")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    inspector = FileTypeInspector(args.path)
    inspector.run()


if __name__ == "__main__":
    main()
