"""*********************************************************************************************************************
*                                                                                                                      *
    BUG: Clones the saved views, but does not update the owner correctly. This script can be run to create the views,
    and the owner can be changed in the django admin.

    Examples:
    python src/scripts/paperless/copy_saved_views.py --source-user-id 3 --target-user-ids 7 10 9 8
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    METADATA:                                                                                                         *
*                                                                                                                      *
*        File:    copy_saved_views.py                                                                                 *
*        Project: imageinn                                                                                             *
*        Version: 0.1.0                                                                                                *
*        Created: 2025-01-23                                                                                           *
*        Author:  Jess Mann                                                                                            *
*        Email:   jess.a.mann@gmail.com                                                                                *
*        Copyright (c) 2025 Jess Mann                                                                                  *
*                                                                                                                      *
*********************************************************************************************************************"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Any, Iterator, List

import requests
from alive_progress import alive_bar
from colorlog import ColoredFormatter
from dotenv import load_dotenv
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

VIEWS_TO_REPLICATE = [
    #"Books, Magazines, Reports",
    #"CRIS",
    #"Default View",
    #"HRSH",
    #"HRSH - Before Closure",
    #"HRSH - Morgue",
    #"HRSH - Refreshment Stand",
    #"HHRSH - Tailor Shop",
    #"Maps, Blueprints, Aerials",
    #"My Files",
    #"Paperwork",
    #"Photography",
    #"Unknown Building",
    #"HRSH - 38 - Straight View of Stage",
    "Example: Everything Except HRSH",
	"Example: HRSH Auditorium - Photos",
	"Example: HRSH Auditorium - Straight View of Stage",
	"Example: HRSH Auditorium - Straight View of Stage	Alyssa",
	"Example: HRSH Morgue - 2nd Floor",
	"Example: Photos of Building Exteriors",
	"Example: Tags and Metadata Visible",
]

class Paperless(BaseModel):
    """
    Main class for interacting with the Paperless NGX API.
    """
    paperless_url: str = Field(..., env="PAPERLESS_URL")
    paperless_key: str = Field(..., env="PAPERLESS_KEY")

    class Config:
        arbitrary_types_allowed = True

    def get(self, url_path: str, params: dict | None = None) -> Any:
        """Send a GET request to the Paperless NGX API."""
        # If url begins with http, do not append the url_path
        if url_path.startswith("http"):
            address = url_path
        else:
            address = f"{self.paperless_url}/{url_path}"
        
        headers = {"Authorization": f"Token {self.paperless_key}"}
        logger.debug(f'GET: {address} with params: {params}')
        response = requests.get(address, headers=headers, params=params)
        logger.debug(f"Response Status: {response.status_code}")
        logger.debug(f"Response Content: {response.text}")
        response.raise_for_status()
        return response.json()

    def post(self, url_path: str, payload: dict) -> Any:
        """Send a POST request to the Paperless NGX API."""
        headers = {"Authorization": f"Token {self.paperless_key}"}
        logger.debug(f'POST: {self.paperless_url}/{url_path} with payload: {payload}')
        response = requests.post(f"{self.paperless_url}/{url_path}", headers=headers, json=payload)
        logger.debug(f"Response Status: {response.status_code}")
        logger.debug(f"Response Content: {response.text}")
        response.raise_for_status()
        return response.json()

    def fetch_saved_views(self, user_id: int | None = None) -> Iterator[dict]:
        """Fetch all saved views for a specific user."""
        data = self.get("api/saved_views/")
        if not data or "results" not in data:
            logger.warning("No saved views found.")
            return []

        results = data["results"]
        while results:
            if user_id is None:
                yield from results
            else: 
                yield from (view for view in results if view["owner"] == user_id)

            # Not another page
            if "next" not in data or not data["next"]:
                logger.info("No more saved views found.")
                break

            logger.info('Fetching next page of saved views... %s', data["next"])
            data = self.get(data["next"])
            if not data or "results" not in data:
                logger.debug("No more saved views found.")
                break
            results = data["results"]

        return

    def create_saved_view(self, view_data: dict, user_id: int) -> dict:
        """Create a new saved view for a user."""
        view_data.pop("id", None)  # Remove ID from the original view
        view_data["owner"] = user_id  # Assign to the new owner
        logger.debug(f'view_data: {view_data}')
        return self.post("api/saved_views/", view_data)


    def replicate_saved_views(self, source_user_id: int, target_user_ids: list[int]) -> None:
        """Replicate saved views from one user to others."""
        saved_views = self.fetch_saved_views() #source_user_id)
        if not saved_views:
            logger.warning(f"No saved views found for source user ID {source_user_id}.")
            return

        for target_user_id in target_user_ids:
            for view in saved_views:
                if view["name"] not in VIEWS_TO_REPLICATE:
                    logger.info(f"Skipping view '{view['name']}' for user {target_user_id}")
                    continue

                try:
                    self.create_saved_view(view, target_user_id)
                    logger.info(f"Replicated view '{view['name']}' to user {target_user_id}")
                except Exception as e:
                    logger.error(f"Failed to replicate view '{view['name']}': {e}")


def setup_logging(verbose: bool):
    """Set up logging with colored output."""
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)
    formatter = ColoredFormatter(
        "%(log_color)s%(levelname)s%(reset)s - %(message)s",
        log_colors={
            "DEBUG": "green",
            "INFO": "blue",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "red,bg_white",
        },
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.addHandler(handler)
    return logger

def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Replicate saved views between users in Paperless NGX.")
    parser.add_argument("--source-user-id", type=int, required=True, help="User ID to copy views from")
    parser.add_argument("--target-user-ids", type=int, nargs="+", required=True, help="List of user IDs to copy views to")
    parser.add_argument("--url", type=str, default=None, help="The base URL of the Paperless NGX instance")
    parser.add_argument("--key", type=str, default=None, help="The API key for the Paperless NGX instance")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()

    setup_logging(args.verbose)

    if not args.url:
        args.url = os.getenv("PAPERLESS_URL")
        if not args.url:
            logger.error("PAPERLESS_URL environment variable is not set.")
            sys.exit(1)

    if not args.key:
        args.key = os.getenv("PAPERLESS_KEY")
        if not args.key:
            logger.error("PAPERLESS_KEY environment variable is not set.")
            sys.exit(1)

    paperless = Paperless(paperless_url=args.url, paperless_key=args.key)
    paperless.replicate_saved_views(args.source_user_id, args.target_user_ids)

if __name__ == "__main__":
    main()