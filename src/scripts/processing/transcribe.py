"""*********************************************************************************************************************
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    METADATA:                                                                                                         *
*                                                                                                                      *
*        File:    transcribe.py                                                                                        *
*        Project: imageinn                                                                                             *
*        Version: 0.1.0                                                                                                *
*        Created: 2025-03-17                                                                                           *
*        Author:  Jess Mann                                                                                            *
*        Email:   jess@jmann.me                                                                                        *
*        Copyright (c) 2025 Jess Mann                                                                                  *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    LAST MODIFIED:                                                                                                    *
*                                                                                                                      *
*        2025-03-17     By Jess Mann                                                                                   *
*                                                                                                                      *
*********************************************************************************************************************"""

import argparse
import logging
import os
import signal
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Generator, Literal, Optional, Dict, List, Any, Union, Iterator, Tuple

import ffmpeg
import psutil
import pysrt
import whisper
from tqdm import tqdm

import sys
import platform

if platform.system() != "Windows":
    import resource


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("transcription.log", mode="a", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


@dataclass
class TranscriptionConfig:
    """Configuration options for the transcription process."""
    model_size: Literal["tiny", "base", "small", "medium", "large"] = "small"
    device: Optional[str] = None
    language: Optional[str] = None
    cpu_limit: int = 2  # Number of CPU cores to use
    memory_limit_mb: int = 2048  # Memory limit in MB
    threads: int = 2  # Number of threads for processing
    max_workers: int = 1  # Max workers for parallel processing
    keep_audio: bool = False  # Whether to keep temporary audio files
    temp_dir: Optional[Path] = None  # Directory for temporary files


class ResourceManager:
    """Manages system resources for child processes."""

    @staticmethod
    def set_resource_limits(cpu_limit: int, memory_limit_mb: int) -> None:
        """
        Set CPU and memory limits for the current process.
        
        Args:
            cpu_limit: Maximum number of CPU cores to use
            memory_limit_mb: Maximum memory usage in MB
        """
        # Set CPU affinity on supported platforms
        try:
            process = psutil.Process()
            if hasattr(process, "cpu_affinity"):
                all_cpus = list(range(psutil.cpu_count(logical=True)))
                process.cpu_affinity(all_cpus[:cpu_limit])
                logger.debug(f"Set CPU affinity to use {cpu_limit} cores")
        except Exception as e:
            logger.warning(f"Failed to set CPU affinity: {e}")

        # Set memory limits
        if platform.system() != "Windows":
            try:
                if hasattr(resource, "RLIMIT_AS"):
                    memory_bytes = memory_limit_mb * 1024 * 1024
                    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
                    logger.debug(f"Set memory limit to {memory_limit_mb}MB")
            except Exception as e:
                logger.warning(f"Failed to set memory limit: {e}")
        else:
            logger.info("Memory limits not enforced on Windows.")


    @contextmanager
    def limit_resources(self, cpu_limit: int, memory_limit_mb: int) -> Generator[None, None, None]:
        """
        Context manager to apply resource limits for a block of code.
        
        Args:
            cpu_limit: Maximum number of CPU cores to use
            memory_limit_mb: Maximum memory usage in MB
            
        Yields:
            None
        """
        try:
            self.set_resource_limits(cpu_limit, memory_limit_mb)
            yield
        finally:
            # Reset to defaults if possible
            pass


class SignalHandler:
    """Handles system signals for graceful termination."""
    
    def __init__(self) -> None:
        self.original_sigint = signal.getsignal(signal.SIGINT)
        self.original_sigterm = signal.getsignal(signal.SIGTERM)
        self.keep_running = True
    
    def __enter__(self) -> 'SignalHandler':
        signal.signal(signal.SIGINT, self._handler)
        signal.signal(signal.SIGTERM, self._handler)
        return self
    
    def __exit__(self, *args: Any) -> None:
        signal.signal(signal.SIGINT, self.original_sigint)
        signal.signal(signal.SIGTERM, self.original_sigterm)
    
    def _handler(self, signum: int, frame: Any) -> None:
        logger.warning(f"Received signal {signum}, initiating graceful shutdown")
        self.keep_running = False


class AudioExtractor:
    """Handles extraction of audio from video files."""
    
    def __init__(self, config: TranscriptionConfig) -> None:
        """
        Initialize the audio extractor.
        
        Args:
            config: Configuration options for extraction
        """
        self.config = config
        self.resource_manager = ResourceManager()
    
    def extract_audio(self, video_path: Path, audio_path: Path) -> None:
        """
        Extract audio from a video file.
        
        Args:
            video_path: Path to the video file
            audio_path: Path to output the audio file
            
        Raises:
            RuntimeError: If audio extraction fails
        """
        logger.info(f"Extracting audio from {video_path.name}...")
        if audio_path.exists():
            logger.warning(f"Temporary audio file {audio_path.name} already exists. Overwriting.")
            audio_path.unlink()
        
        try:
            with self.resource_manager.limit_resources(
                self.config.cpu_limit, self.config.memory_limit_mb
            ):
                # Apply resource constraints to ffmpeg
                ffmpeg_args = {
                    "acodec": "pcm_s16le",
                    "ar": "16000",
                    "threads": min(2, self.config.cpu_limit),
                }
                
                global_args = [
                    "-filter_threads", str(min(1, self.config.cpu_limit)),
                    "-thread_queue_size", "512",
                    "-nostats",
                    "-cpuflags", "-all",
                ]
                
                # Add memory limit
                if self.config.memory_limit_mb > 0:
                    mem_bytes = self.config.memory_limit_mb * 1024 * 1024
                    global_args.extend(["-max_muxing_queue_size", str(min(1024, mem_bytes // 1024))])
                
                process = (
                    ffmpeg.input(str(video_path))
                    .output(str(audio_path), **ffmpeg_args)
                    .global_args(*global_args)
                )
                
                process.run(
                    overwrite_output=True,
                    capture_stderr=True,
                    quiet=True
                )
                
            logger.info(f"Audio extraction completed: {audio_path.name}")
            
        except ffmpeg.Error as e:
            error_message = e.stderr.decode("utf-8") if e.stderr else str(e)
            logger.error(f"FFmpeg failed: {error_message}")
            raise RuntimeError(f"FFmpeg audio extraction failed: {error_message}") from e


class SubtitleFormatter:
    """Handles formatting and saving of subtitle files."""
    
    @staticmethod
    def format_srt_time(seconds: float) -> str:
        """
        Format seconds into SRT time format.
        
        Args:
            seconds: Time in seconds
            
        Returns:
            Formatted time string in SRT format
        """
        millisec = int((seconds % 1) * 1000)
        return f"{timedelta(seconds=int(seconds))},{millisec:03d}"
    
    @classmethod
    def create_srt_file(cls, segments: list[dict[str, Any]], output_path: Path) -> None:
        """
        Create an SRT file from transcription segments.
        
        Args:
            segments: List of transcription segments
            output_path: Path to save the SRT file
        """
        logger.info(f"Saving subtitles to {output_path.name}...")
        subs = pysrt.SubRipFile()
        
        for i, segment in enumerate(segments, start=1):
            sub = pysrt.SubRipItem(
                index=i,
                start=cls.format_srt_time(segment["start"]),
                end=cls.format_srt_time(segment["end"]),
                text=segment["text"].strip(),
            )
            subs.append(sub)
        
        try:
            subs.save(output_path, encoding="utf-8")
            logger.info(f"Subtitle file saved: {output_path}")
        except Exception as e:
            logger.error(f"Failed to save subtitle file: {e}")
            raise


class WhisperTranscriber:
    """Uses Whisper model to transcribe audio."""
    
    def __init__(self, config: TranscriptionConfig) -> None:
        """
        Initialize the transcriber.
        
        Args:
            config: Configuration options for transcription
        """
        self.config = config
        self.model = None
    
    def load_model(self) -> None:
        """Load the Whisper model if not already loaded."""
        if self.model is None:
            logger.info(f"Loading Whisper model: {self.config.model_size} on device: {self.config.device or 'default'}")
            try:
                self.model = whisper.load_model(
                    self.config.model_size, 
                    #device=self.config.device
                )
                logger.debug(f"Model loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load Whisper model: {e}")
                raise
    
    def transcribe(self, audio_path: Path) -> list[dict[str, Any]]:
        """
        Transcribe audio file to text.
        
        Args:
            audio_path: Path to the audio file
            
        Returns:
            List of transcription segments
            
        Raises:
            RuntimeError: If transcription fails
        """
        self.load_model()
        logger.info(f"Transcribing audio: {audio_path.name}...")
        
        try:
            with ResourceManager().limit_resources(
                self.config.cpu_limit, self.config.memory_limit_mb
            ):
                # Pass in the audio file path as str
                transcribe_options = {}
                if self.config.language:
                    transcribe_options["language"] = self.config.language
                
                result = self.model.transcribe(
                    str(audio_path), 
                    **transcribe_options
                )
                
                segments = result.get("segments", [])
                logger.info(f"Transcription completed: {len(segments)} segments")
                return segments
                
        except Exception as e:
            logger.exception(f"Transcription failed: {e}")
            raise RuntimeError(f"Whisper transcription failed: {e}") from e


class VideoTranscriber:
    """Handles video transcription using Whisper and generates SRT subtitles."""

    def __init__(self, video_path: Path, config: TranscriptionConfig) -> None:
        """
        Initialize the transcriber with a given video file.

        Args:
            video_path: Path to the video file
            config: Configuration options for transcription
        """
        self.video_path = video_path.resolve()
        self.config = config
        
        # Create temporary directory if specified
        temp_dir = self.config.temp_dir or Path(tempfile.gettempdir())
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Set up audio and subtitle paths
        self.audio_path = self._generate_unique_audio_path(temp_dir)
        self.srt_path = self.video_path.with_stem(f"{self.video_path.stem}.US").with_suffix(".srt")
        
        # Initialize components
        self.audio_extractor = AudioExtractor(config)
        self.transcriber = WhisperTranscriber(config)
        
        logger.debug(f"Initialized transcriber for {video_path.name}")

    def _generate_unique_audio_path(self, temp_dir: Path) -> Path:
        """
        Generate a unique path for the temporary audio file.
        
        Args:
            temp_dir: Directory for temporary files
            
        Returns:
            Unique path for audio file
        """
        filename = f"{self.video_path.stem}_{os.getpid()}.wav"
        audio_path = temp_dir / filename
        counter = 1
        
        while audio_path.exists():
            filename = f"{self.video_path.stem}_{os.getpid()}_{counter}.wav"
            audio_path = temp_dir / filename
            counter += 1
            
        return audio_path

    def process(self) -> Path:
        """
        Process the video: extract audio, transcribe, and save subtitles.
        
        Returns:
            Path to the saved subtitle file
            
        Raises:
            RuntimeError: If processing fails
        """
        logger.info(f"Processing video: {self.video_path.name}")
        
        try:
            # Extract audio
            self.audio_extractor.extract_audio(self.video_path, self.audio_path)
            
            # Transcribe audio
            segments = self.transcriber.transcribe(self.audio_path)
            
            # Save as SRT
            SubtitleFormatter.create_srt_file(segments, self.srt_path)
            
            return self.srt_path
            
        except Exception as e:
            logger.error(f"Failed to process {self.video_path.name}: {e}")
            raise
        finally:
            self.cleanup()

    def cleanup(self) -> None:
        """Clean up temporary files."""
        if self.audio_path.exists() and not self.config.keep_audio:
            try:
                self.audio_path.unlink()
                logger.debug(f"Deleted temporary audio file: {self.audio_path.name}")
            except Exception as e:
                logger.warning(f"Failed to delete temporary audio file: {e}")
                raise


class VideoProcessor:
    """Processes videos in batches or individually."""
    
    def __init__(self, config: TranscriptionConfig) -> None:
        """
        Initialize the video processor.
        
        Args:
            config: Configuration options for processing
        """
        self.config = config
    
    def process_file(self, video_file: Path) -> Optional[Path]:
        """
        Process a single video file.
        
        Args:
            video_file: Path to the video file
            
        Returns:
            Path to the generated subtitle file or None if skipped/failed
        """
        srt_path = video_file.with_stem(f"{video_file.stem}.US").with_suffix(".srt")
        if srt_path.exists():
            logger.info(f"Skipping {video_file.name}, SRT already exists.")
            return None
        
        logger.info(f"Processing {video_file.name}")
        try:
            transcriber = VideoTranscriber(video_file, self.config)
            return transcriber.process()
        except Exception as e:
            logger.error(f"Failed to process {video_file.name}: {e}")
            raise

    def find_video_files(self, directory: Path) -> Generator[Path, None, None]:
        """
        Find video files in a directory recursively.
        
        Args:
            directory: Directory to search
            
        Yields:
            Paths to video files
        """
        # Support more video formats
        video_extensions = [".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv"]
        
        for ext in video_extensions:
            yield from directory.rglob(f"*{ext}")

    def process_directory(self, directory: Path) -> list[Path]:
        """
        Process all video files in a directory.
        
        Args:
            directory: Directory containing video files
            
        Returns:
            List of paths to generated subtitle files
        """
        # Get total count for progress bar
        video_files = list(self.find_video_files(directory))
        
        if not video_files:
            logger.warning(f"No video files found in {directory}")
            return []
        
        results: list[Path] = []
        logger.info(f"Found {len(video_files)} video files to process")
        
        # Use ThreadPoolExecutor for parallel processing if configured
        if self.config.max_workers > 1:
            with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
                futures = [executor.submit(self.process_file, video_file) 
                          for video_file in video_files]
                
                for future in tqdm(futures, desc="Processing videos", unit="file"):
                    result = future.result()
                    if result:
                        results.append(result)
        else:
            # Sequential processing with progress bar
            for video_file in tqdm(video_files, desc="Processing videos", unit="file"):
                result = self.process_file(video_file)
                if result:
                    results.append(result)
        
        return results


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Transcribe video audio to an SRT subtitle file using Whisper.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("input_path", type=str, help="Path to the input video file or directory.")
    parser.add_argument(
        "--size",
        type=str,
        choices=["tiny", "base", "small", "medium", "large"],
        default="small",
        help="Whisper model size to use."
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="Device to use for the model (e.g., 'cpu', 'cuda')."
    )
    parser.add_argument(
        "--language",
        type=str,
        default=None,
        help="Language code for transcription (use Whisper's default if not specified)."
    )
    parser.add_argument(
        "--cpu-limit",
        type=int,
        default=2,
        help="Maximum number of CPU cores to use."
    )
    parser.add_argument(
        "--memory-limit",
        type=int,
        default=10240,
        help="Maximum memory usage in MB."
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=2,
        help="Number of threads for processing."
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of parallel workers for directory processing."
    )
    parser.add_argument(
        "--keep-audio",
        action="store_true",
        help="Keep temporary audio files."
    )
    parser.add_argument(
        "--temp-dir",
        type=str,
        default=None,
        help="Directory for temporary files."
    )
    parser.add_argument(
        "--verbose", 
        "-v", 
        action="store_true", 
        help="Enable verbose logging."
    )
    
    return parser.parse_args()


def create_config_from_args(args: argparse.Namespace) -> TranscriptionConfig:
    """
    Create a configuration object from command-line arguments.
    
    Args:
        args: Parsed command-line arguments
        
    Returns:
        Configuration object
    """
    return TranscriptionConfig(
        model_size=args.size,
        device=args.device,
        language=args.language,
        cpu_limit=args.cpu_limit,
        memory_limit_mb=args.memory_limit,
        threads=args.threads,
        max_workers=args.workers,
        keep_audio=args.keep_audio,
        temp_dir=Path(args.temp_dir) if args.temp_dir else None
    )


def main() -> int:
    """Main entry point for the program."""
    args = parse_args()
    
    # Set up logging level
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled")

    # Handle path
    input_path = Path(args.input_path)
    if not input_path.exists():
        logger.error(f"Path not found: {input_path}")
        return 1

    # Create configuration
    config = create_config_from_args(args)
    processor = VideoProcessor(config)
    
    # Handle input path
    try:
        with SignalHandler() as sh:
            if input_path.is_file():
                logger.info(f"Processing single file: {input_path}")
                result = processor.process_file(input_path)
                if result:
                    logger.info(f"Successfully created subtitle file: {result}")
                else:
                    logger.warning("No subtitle file was created")
            elif input_path.is_dir():
                logger.info(f"Processing directory: {input_path}")
                results = processor.process_directory(input_path)
                logger.info(f"Successfully processed {len(results)} video files")
            else:
                logger.error(f"Invalid path: {input_path}")
                return 1
                
            if not sh.keep_running:
                logger.warning("Processing was interrupted by user")
                return 130  # Standard exit code for SIGINT
                
    except KeyboardInterrupt:
        logger.warning("Processing interrupted by user")
        return 130
    except Exception as e:
        logger.exception(f"An error occurred during processing: {e}")
        return 1
    
    logger.info("Processing completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
