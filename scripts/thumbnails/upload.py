import subprocess
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def authenticate(url: str, api_key: str):
    try:
        subprocess.run(["immich", "login-key", url, api_key], check=True)
        logger.info("Authenticated successfully.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Authentication failed: {e}")
        exit(1)

def upload_files(directory: Path, recursive: bool = True):
    command = ["immich", "upload"]
    if recursive:
        command.append("--recursive")
    command.append(str(directory))

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

    if not url or not api_key or not thumbnails_dir:
        logger.error("IMMICH_URL, IMMICH_API_KEY, and CLOUD_THUMBNAILS_DIR must be set.")
        exit(1)

    authenticate(url, api_key)
    upload_files(Path(thumbnails_dir))

if __name__ == "__main__":
    main()
