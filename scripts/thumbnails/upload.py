import subprocess
import os
import logging
from pathlib import Path
from dotenv import load_dotenv
import argparse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Immich:
    url : str
    api_key : str
    thumbnails_dir : Path
    _authenticated : bool = False
    
    def __init__(self, url: str, api_key: str, thumbnails_dir : Path | str):
        self.url = url
        self.api_key = api_key
        self.thumbnails_dir = Path(thumbnails_dir)

        if not self.thumbnails_dir.exists():
            logger.error(f"Thumbnails directory {self.thumbnails_dir} does not exist.")
            raise FileNotFoundError

    def authenticate(self):
        if self._authenticated:
            return
        
        try:
            subprocess.run(["immich", "login-key", self.url, self.api_key], check=True)
            self._authenticated = True
            logger.info("Authenticated successfully.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Authentication failed: {e}")
            raise

    def upload_files(self, recursive: bool = True):
        if not self._authenticated:
            self.authenticate()
        
        command = ["immich", "upload", "-i", "*.mp4"]

        if recursive:
            command.append("--recursive")
            
        command.append(self.thumbnails_dir.as_posix())

        try:
            subprocess.run(command, check=True)
            logger.info("Files uploaded successfully.")
        except subprocess.CalledProcessError as e:
            logger.error(f"File upload failed: {e}")

def main():
    # Load environment variables from .env file
    load_dotenv()
    
    url = os.getenv("IMMICH_URL")
    api_key = os.getenv("IMMICH_API_KEY")
    thumbnails_dir = os.getenv("CLOUD_THUMBNAILS_DIR")

    try:
        parser = argparse.ArgumentParser(description="Upload JPG files to Immich.")
        parser.add_argument("--url", help="Immich URL", default=url)
        parser.add_argument("--api-key", help="Immich API key", default=api_key)
        parser.add_argument("--thumbnails-dir", '-d', help="Cloud thumbnails directory", default=thumbnails_dir)
        args = parser.parse_args()

        if not args.url or not args.api_key or not args.thumbnails_dir:
            logger.error("IMMICH_URL, IMMICH_API_KEY, and CLOUD_THUMBNAILS_DIR must be set.")
            exit(1)

        immich = Immich(args.url, args.api_key, args.thumbnails_dir)
        immich.authenticate()
        immich.upload_files()
    except KeyboardInterrupt:
        logger.info("Upload cancelled by user.")

if __name__ == "__main__":
    main()
