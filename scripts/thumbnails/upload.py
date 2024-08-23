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
    _ignore_extensions : list[str]
    _authenticated : bool = False
    
    def __init__(self, url: str, api_key: str, thumbnails_dir : Path | str, ignore_extensions : list[str] | None = None):
        self.url = url
        self.api_key = api_key
        self.thumbnails_dir = Path(thumbnails_dir)
        self.ignore_extensions = ignore_extensions or []

        if not self.thumbnails_dir.exists():
            logger.error(f"Thumbnails directory {self.thumbnails_dir} does not exist.")
            raise FileNotFoundError

    @property
    def ignore_extensions(self) -> list[str]:
        return self._ignore_extensions

    @ignore_extensions.setter
    def ignore_extensions(self, value: list[str] | str | None):
        if not value:
            self._ignore_extensions = []
            return

        if isinstance(value, str):
            self._ignore_extensions = [value]
            return
        
        self._ignore_extensions = value

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

    def find_large_files(self, directory : Path | None = None, size : int = 1024 * 1024 * 100) -> list[Path]:
        if not directory:
            directory = self.thumbnails_dir
            
        large_files = []
        for file in directory.rglob("**/*"):
            if file.stat().st_size > size:
                large_files.append(file)
        return large_files

    def upload_files(self, recursive: bool = True, ignore_extensions : list[str] | None = None, directory : Path | None = None):
        if not self._authenticated:
            self.authenticate()
            
        ignore_extensions = ignore_extensions or []
        directory = directory or self.thumbnails_dir

        command = ["immich", "upload"]

        # Ignore files 
        ignore_patterns = []
        
        for ext in ignore_extensions:
            # Handle not (!)
            if ext.startswith("!"):
                ignore_patterns.append(f'!*.{ext[1:]}')
            else:
                ignore_patterns.append(f'*.{ext}')

        if large_files := self.find_large_files(directory):
            logger.warning("%d Large files found, which will be skipped.", len(large_files))
            ignore_patterns.extend([file.as_posix() for file in large_files])

        if ignore_patterns:
            ignore_string = "|".join(ignore_patterns)
            command.extend(["-i", f'({ignore_string})'])

        if recursive:
            command.append("--recursive")
            
        command.append(directory.as_posix())

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
        parser.add_argument("--ignore-extensions", "-i", help="Ignore files with these extensions", nargs='+')
        args = parser.parse_args()

        if not args.url or not args.api_key or not args.thumbnails_dir:
            logger.error("IMMICH_URL, IMMICH_API_KEY, and CLOUD_THUMBNAILS_DIR must be set.")
            exit(1)

        immich = Immich(args.url, args.api_key, args.thumbnails_dir, args.ignore_extensions)
        immich.authenticate()
        immich.upload_files()
    except KeyboardInterrupt:
        logger.info("Upload cancelled by user.")

if __name__ == "__main__":
    main()
