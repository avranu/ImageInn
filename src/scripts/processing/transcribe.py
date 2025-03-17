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
import sys
from datetime import timedelta
from pathlib import Path

import ffmpeg
import pysrt
import whisper

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

class VideoTranscriber:
    """Handles video transcription using Whisper and generates SRT subtitles."""

    def __init__(self, video_path: Path):
        """
        Initializes the transcriber with a given video file.

        Args:
            video_path (Path): Path to the video file.
        """
        self.video_path: Path = video_path.resolve()
        self.audio_path: Path = self.video_path.with_suffix(".wav")
        self.srt_path: Path = self.video_path.with_stem(f"{self.video_path.stem}.US").with_suffix(".srt")
        self.model = whisper.load_model("small")  # Change to 'medium' or 'large' if needed

    def extract_audio(self) -> None:
        """Extracts audio from the video using FFmpeg and saves it as a WAV file."""
        logging.info(f"Extracting audio from {self.video_path.name}...")

        if self.audio_path.exists():
            logging.warning(f"Temporary audio file {self.audio_path.name} already exists. Overwriting.")
            self.audio_path.unlink()

        try:
            ffmpeg.input(str(self.video_path)).output(
                str(self.audio_path),
                acodec="pcm_s16le",
                ar="16000"
            ).run(overwrite_output=True, quiet=True)
        except ffmpeg.Error as e:
            logging.error(f"FFmpeg failed: {e}")
            sys.exit(1)

    def transcribe_audio(self) -> list[dict]:
        """
        Transcribes extracted audio using Whisper.

        Returns:
            list[dict]: A list of subtitle segments.
        """
        logging.info("Transcribing audio...")
        try:
            result = self.model.transcribe(str(self.audio_path))
            return result.get("segments", [])
        except Exception as e:
            logging.error(f"Transcription failed: {e}")
            sys.exit(1)

    def save_srt(self, subtitles: list[dict]) -> None:
        """
        Saves transcribed subtitles as an SRT file.

        Args:
            subtitles (list[dict]): The transcribed subtitle segments.
        """
        logging.info(f"Saving subtitles to {self.srt_path.name}...")

        subs = pysrt.SubRipFile()

        for i, segment in enumerate(subtitles, start=1):
            sub = pysrt.SubRipItem(
                index=i,
                start=self._format_srt_time(segment["start"]),
                end=self._format_srt_time(segment["end"]),
                text=segment["text"],
            )
            subs.append(sub)

        subs.save(self.srt_path, encoding="utf-8")
        logging.info(f"Subtitle file saved: {self.srt_path}")

    def cleanup(self) -> None:
        """Removes the temporary audio file after transcription."""
        if self.audio_path.exists():
            self.audio_path.unlink()
            logging.info(f"Deleted temporary audio file: {self.audio_path.name}")

    @staticmethod
    def _format_srt_time(seconds: float) -> str:
        """
        Converts a time value in seconds to SRT timestamp format.

        Args:
            seconds (float): Time in seconds.

        Returns:
            str: Formatted time in hh:mm:ss,ms format.
        """
        millisec = int((seconds % 1) * 1000)
        return f"{timedelta(seconds=int(seconds))},{millisec:03d}"

    def process(self) -> None:
        """Runs the full transcription pipeline."""
        self.extract_audio()
        subtitles = self.transcribe_audio()
        self.save_srt(subtitles)
        self.cleanup()


def parse_args() -> argparse.Namespace:
    """Parses command-line arguments."""
    parser = argparse.ArgumentParser(description="Transcribe video audio to an SRT subtitle file using Whisper.")
    parser.add_argument("video_file", type=Path, help="Path to the input video file.")
    return parser.parse_args()

def main() -> None:
    """Main function to handle argument parsing and transcription."""
    args = parse_args()
    
    if not args.video_file.exists():
        logging.error(f"File not found: {args.video_file}")
        sys.exit(1)

    transcriber = VideoTranscriber(args.video_file)
    transcriber.process()


if __name__ == "__main__":
    main()
