"""
Intended to archive Instagram profiles using Instaloader.

Work in progress. Not yet functional.

Version: 0.1a
Date: 2024-09-25
Status: WIP
"""
from __future__ import annotations
import sys
import os

# Add the root directory of the project to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import logging
import argparse
import time
import random
from pathlib import Path
from typing import List
from pydantic import BaseModel, Field, PrivateAttr, field_validator
from tqdm import tqdm
from scripts import setup_logging
from scripts.exceptions import ShouldTerminateException
import instaloader
import instaloader.exceptions

logger = setup_logging()

DEFAULT_POST_METADATA_TEXT = "Caption: '{caption}' - Title: '{title}' - {mediacount} images - {likes} likes - {comments} comments - hashtags: {caption_hashtags} - mentions: {caption_mentions} - tagged: {tagged_users} - {url}"
DEFAULT_STORY_METADATA_TEXT = "Caption: '{caption}' - {date} - hashtags: {caption_hashtags} - mentions: {caption_mentions} - {url}"

class InstaloaderRunner(BaseModel):
    """
    Run instaloader commands for a list of Instagram profiles.

    - Reads profile names from a file or command-line arguments.
    - Uses the instaloader module directly for better control.
    - Handles retries with exponential backoff.
    - Manages login using username and password from environment variables.
    """
    profiles: List[str] = Field(default_factory=list)
    profiles_file: Path | None = None
    max_retries: int = 5
    delay: int = 1  # Initial delay between retries in seconds

    # Private attributes
    _username: str = PrivateAttr(default='')
    _password: str = PrivateAttr(default='')
    _success_profiles: List[str] = PrivateAttr(default_factory=list)
    _failed_profiles: List[str] = PrivateAttr(default_factory=list)
    _instaloader: instaloader.Instaloader = PrivateAttr()

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

    def setup_instaloader(self):
        # Set up instaloader instance with desired options
        self._instaloader = instaloader.Instaloader(
            download_stories=True,
            download_comments=True,
            download_videos=True,
            save_metadata=True,
            post_metadata_txt_pattern=DEFAULT_POST_METADATA_TEXT,
            storyitem_metadata_txt_pattern=DEFAULT_STORY_METADATA_TEXT,
            max_connection_attempts=1,
        )
        try:
            self._instaloader.login(self.username, self.password)
            logger.info("Logged in as '%s'.", self.username)
        except instaloader.exceptions.BadCredentialsException:
            raise ShouldTerminateException("Invalid username or password.")
        except instaloader.exceptions.ConnectionException as e:
            raise ShouldTerminateException(f"Connection error: {e}")
        except instaloader.exceptions.TwoFactorAuthRequiredException:
            raise ShouldTerminateException("Two-factor authentication is required but not supported in this script.")
        except Exception as e:
            raise ShouldTerminateException(f"An unexpected error occurred during login: {e}")

    def run(self):
        logger.info("Starting Instaloader for %d profiles.", len(self.profiles))

        self.setup_instaloader()

        for profile_name in tqdm(self.profiles, desc="Profiles", unit="profile"):
            self.process_profile(profile_name)
            
        self.report()

    def process_profile(self, profile_name: str):
        retries = 0
        delay = self.delay
        while retries <= self.max_retries:
            try:
                self.send_request(profile_name)
                self._success_profiles.append(profile_name)
                break
            
            except instaloader.exceptions.ConnectionException as e:
                if retries >= self.max_retries:
                    self._profile_error(profile_name, f"Max retries exceeded for profile '{profile_name}'.")
                    break
                
                sleep_time = delay + random.uniform(0, 1)
                logger.warning(f"Connection error for profile '{profile_name}': {e}. Retrying in {sleep_time:.2f} seconds...")
                time.sleep(sleep_time)
                retries += 1
                # Exponential backoff
                delay *= 2
                
            except instaloader.exceptions.QueryReturnedNotFoundException:
                self._profile_error(profile_name, f"Profile {profile_name} not found.")
                self._failed_profiles.append(profile_name)
                break
            
            except instaloader.exceptions.PrivateProfileNotFollowedException:
                self._profile_error(profile_name, f"Profile {profile_name} is private and not followed.")
                break
            
            except instaloader.exceptions.TooManyRequestsException as e:
                sleep_time = delay + random.uniform(0, 1)
                logger.warning(f"Too many requests error for profile '{profile_name}': {e}. Sleeping for {sleep_time:.2f} seconds...")
                time.sleep(sleep_time)
                retries += 1
                # Exponential backoff
                delay *= 2
                
            except Exception as e:
                self._profile_error(profile_name, f"An unexpected error occurred for profile '{profile_name}': {e}")
                break
        else:
            logger.error(f"Failed to process profile '{profile_name}' after {self.max_retries} retries.")

    def _profile_error(self, profile_name: str, error_message : str):
        logger.error(f"Error processing profile '{profile_name}': {error_message}")
        self._failed_profiles.append(profile_name)

    def send_request(self, profile_name: str):
        _profile = instaloader.Profile.from_username(self._instaloader.context, profile_name)
        logger.info(f"Processing profile '{profile_name}'")
        self._instaloader.download_profile(
            profile_name,
            profile_pic=True,
            stories=True,
            highlights=True,
            tagged=True,
            posts=True,
            fast_update=True
        )

        '''
        Raw output options:
            * JSON Query to graphql/query: 401 Unauthorized - "fail" status, message "Please wait a few minutes before you try again." when accessing https://www.instagram.com/graphql/query?query_hash=2b0673e0dc4580674a88d426fe00ea90&variables=%7B%22shortcode%22%3A%22C0hnmIOvnda%22%7D
            * Login required to access comments of a post
            * username/2024-01-10_21-13-19_UTC_1.jpg exists username/2024-01-10_21-13-19_UTC_2.jpg exists [Caption: 'some caption…] updated [Caption: 'some caption…] Download <Post C8DML5XPKOi> of username: Login required to access comments of a post.
            * username: 400 Bad Request - "fail" status, message "challenge_required" when accessing https://i.instagram.com/api/v1/users/web_profile_info/?username=username
            * username/2021-01-20_15-29-55_UTC.jpg [Caption: 'some caption i…] comments json
            * username/2021-01-20_13-58-25_UTC.jpg [Caption: 'some caption …] Download <Post CRtmKDgoR9b> of username: 400 Bad Request - "fail" status, message "feedback_required" when accessing https://i.instagram.com/api/v1/media/2624921974557712219/comments/18302300596044615/child_comments/?max_id=
        '''

    def report(self):
        logger.info("Instaloader run completed.")
        if self._success_profiles:
            logger.info("Successful profiles: %s", ', '.join(self._success_profiles))
        if self._failed_profiles:
            logger.warning("Failed profiles: %s", ', '.join(self._failed_profiles))

def main():
    try:
        parser = argparse.ArgumentParser(description='Archive Instagram profiles using Instaloader.')
        parser.add_argument('-p', '--profiles', nargs='*', help='List of Instagram profiles to archive.')
        parser.add_argument('-f', '--profiles-file', help='File containing Instagram profiles to archive, one per line.')
        parser.add_argument('-v', '--verbose', action='store_true', help='Increase verbosity.')
        args = parser.parse_args()

        if args.verbose:
            logger.setLevel(logging.DEBUG)

        runner = InstaloaderRunner(
            profiles=args.profiles,
            profiles_file=args.profiles_file,
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
