from __future__ import annotations
import sys
import os

# Add the root directory of the project to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import subprocess
import logging
import argparse
import time
from pathlib import Path
from typing import List
from pydantic import BaseModel, Field, PrivateAttr, field_validator
from tqdm import tqdm
from scripts import setup_logging
from scripts.exceptions import ShouldTerminateException, TooFastException

logger = setup_logging()

DEFAULT_POST_METADATA_TEXT = "Caption: '{caption}' - Title: '{title}' - {mediacount} images - {likes} likes - {comments} comments - hashtags: {caption_hashtags} - mentions: {caption_mentions} - tagged: {tagged_users} - {url}"
DEFAULT_STORY_METADATA_TEXT = "Caption: '{caption}' - {date} - hashtags: {caption_hashtags} - mentions: {caption_mentions} - {url}"

class InstaloaderRunner(BaseModel):
    """
    Run instaloader commands for a list of Instagram profiles.

    - Reads profile names from a file or command-line arguments.
    - Runs the instaloader command for each profile.
    - Handles password prompts by providing the password from an environment variable.
    - Checks the output for successful execution.
    """
    profiles: List[str] = Field(default_factory=list)
    instaloader_args: List[str] = Field(default_factory=list)
    profiles_file: Path | None = None

    # Private attributes
    _username: str = Field(default='')
    _password: str = PrivateAttr(default='')
    _success_profiles: List[str] = PrivateAttr(default_factory=list)
    _failed_profiles: List[str] = PrivateAttr(default_factory=list)

    class Config:
        arbitrary_types_allowed = True

    @property
    def password(self) -> str:
        if not self._password:
            self._password = os.getenv('INSTALOADER_PASSWORD')            
            if not self._password:
                raise ShouldTerminateException("Password not found in environment variable 'INSTALOADER_PASSWORD'.")
        return self._password

    @property
    def username(self) -> str:
        if not self._username:
            self._username = os.getenv('INSTALOADER_USERNAME')
            if not self._username:
                raise ShouldTerminateException("Username not found in environment variable 'INSTALOADER_USERNAME'.")
        return self._username

    @field_validator('profiles', mode="before")
    def validate_profiles(cls, v, values):
        if v:
            return v
        
        if 'profiles_file' in values and values['profiles_file']:
            try:
                with open(values['profiles_file'], 'r') as f:
                    return [line.strip() for line in f if line.strip()]
            except Exception as e:
                raise ShouldTerminateException(f"Error reading profiles from file: {e}") from e

        raise ValueError("No profiles provided.")

    def run(self):
        logger.info("Starting Instaloader for %d profiles.", len(self.profiles))

        for profile in tqdm(self.profiles, desc="Profiles", unit="profile"):
            try:
                self.process_profile(profile)
            except TooFastException as e:
                logger.error(f"Sending requests too quickly. Waiting before retry: {e}")
                time.sleep(60)
                self.process_profile(profile)

            
        self.report()

    def process_profile(self, profile: str):
        command = ['instaloader', '--login', self.username] + self.instaloader_args + [profile]
        logger.debug("Executing command: %s", ' '.join(command))

        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        try:
            stdout, _ = process.communicate(input=self._password + '\n', timeout=300)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, _ = process.communicate()
            raise ShouldTerminateException(f"Command timed out for profile '{profile}'.")

        logger.debug("Command output for profile '%s':\n%s", profile, stdout)

        if process.returncode != 0:
            logger.error("Instaloader failed for profile '%s'. Return code: %d", profile, process.returncode)
            self._failed_profiles.append(profile)
            return

        if "HTTP error code 429" in stdout:
            logger.error("Too many requests error for profile '%s'.", profile)
            raise TooFastException(f"Too many requests for profile '{profile}'.")

        self._success_profiles.append(profile)
        logger.info("Successfully processed profile '%s'.", profile)

    def report(self):
        logger.info("Instaloader run completed.")
        logger.info("Successful profiles: %s", ', '.join(self._success_profiles))
        if self._failed_profiles:
            logger.warning("Failed profiles: %s", ', '.join(self._failed_profiles))

def main():
    try:
        parser = argparse.ArgumentParser(description='Archive Instagram profiles using Instaloader.')
        parser.add_argument('-p', '--profiles', nargs='*', help='List of Instagram profiles to archive.')
        parser.add_argument('-f', '--profiles-file', help='File containing Instagram profiles to archive, one per line.')
        parser.add_argument('-v', '--verbose', action='store_true', help='Increase verbosity.')
        args, unknown_args = parser.parse_known_args()

        if args.verbose:
            logger.setLevel(logging.DEBUG)

        instaloader_args = [
            '--stories',
            '--highlights',
            '--tagged',
            '--comments',
            f'--post-metadata-txt="{DEFAULT_POST_METADATA_TEXT}"',
            f'--storyitem-metadata-txt="{DEFAULT_STORY_METADATA_TEXT}"',
        ] + unknown_args

        runner = InstaloaderRunner(
            profiles			= args.profiles,
            profiles_file		= args.profiles_file,
            instaloader_args	= instaloader_args,
        )

        runner.run()
    except ShouldTerminateException as e:
        logger.critical(f"Critical error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.warning("Operation interrupted by user")
        sys.exit(1)

if __name__ == "__main__":
    main()
