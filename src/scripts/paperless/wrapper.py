"""*********************************************************************************************************************
*                                                                                                                      *
*                                                                                                                      *
    2025-02-26 - I tested get_tags() and get_document_with_tag() once, nothing else. Seems to be working fine.
*                                                                                                                      *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    METADATA:                                                                                                         *
*                                                                                                                      *
*        File:    wrapper.py                                                                                           *
*        Project: imageinn                                                                                             *
*        Version: 0.1.0                                                                                                *
*        Created: 2025-02-26                                                                                           *
*        Author:  Jess Mann                                                                                            *
*        Email:   jess.a.mann@gmail.com                                                                                *
*        Copyright (c) 2025 Jess Mann                                                                                  *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    LAST MODIFIED:                                                                                                    *
*                                                                                                                      *
*        2025-02-26     By Jess Mann                                                                                   *
*                                                                                                                      *
*********************************************************************************************************************"""
import asyncio
from typing import List, Optional
from pypaperless import Paperless
from pypaperless.models import Document, Tag

import argparse
import base64
from io import BytesIO
import json
from pathlib import Path
import re
import sys
import os
import logging
import colorlog
import requests
from alive_progress import alive_bar
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator
import openai
from openai import OpenAI
import fitz
from PIL import Image, UnidentifiedImageError
from jinja2 import Environment, FileSystemLoader
from datetime import datetime, date
import dateparser

logger = logging.getLogger(__name__)

class PaperlessWrapper:
    """
    Synchronous wrapper for the asynchronous pypaperless API.
    """

    def __init__(self, host: str, token: str):
        self._host = host
        self._token = token
        self._client = Paperless(host, token)

    def _run(self, coro):
        """
        Runs an asynchronous function synchronously.
        """
        return asyncio.run(coro)

    def get_documents(self) -> list[Document]:
        """
        Fetches all documents.

        Returns:
            list[Document]: A list of documents.
        """

        logger.info('Getting all documents')
        async def _fetch():
            async with self._client:
                return [doc async for doc in self._client.documents]

        return self._run(_fetch())

    def get_document_by_id(self, document_id: int) -> Optional[Document]:
        """
        Fetch a single document by ID.

        Args:
            document_id (int): The document ID.

        Returns:
            Optional[Document]: The document if found, else None.
        """
        logger.info('Getting document %s', document_id)
        async def _fetch():
            async with self._client:
                return await self._client.documents(document_id)

        return self._run(_fetch())

    def get_documents_by_tag(self, tag_name: str) -> list[Document]:
        """
        Fetches documents with a specific tag.

        Args:
            tag_name (str): The tag name.

        Returns:
            list[Document]: List of documents with the tag.
        """
        logger.info('Getting documents with tag %s', tag_name)
        async def _fetch():
            async with self._client:
                async for tag in self._client.tags:
                    if tag.name == tag_name:
                        return [doc async for doc in self._client.documents if tag.id in doc.tags]
                return []

        return self._run(_fetch())

    def get_tags(self) -> list[Tag]:
        """
        Fetches all available tags.

        Returns:
            list[Tag]: A list of tags.
        """
        logger.info('Getting all tags')
        async def _fetch():
            async with self._client:
                return [tag async for tag in self._client.tags]

        return self._run(_fetch())

    def add_tag_to_document(self, document_id: int, tag_id: int) -> Document:
        """
        Adds a tag to a document.

        Args:
            document_id (int): The document ID.
            tag_id (int): The tag ID.

        Returns:
            Document: The updated document.
        """
        logger.info("Adding tag '%s' to document '%s'", tag_id, document_id)
        async def _update():
            async with self._client:
                doc = await self._client.documents(document_id)
                new_tags = list(set(doc.tags + [tag_id]))
                return await doc.update(tags=new_tags)

        return self._run(_update())

    def remove_tag_from_document(self, document_id: int, tag_id: int) -> Document:
        """
        Removes a tag from a document.

        Args:
            document_id (int): The document ID.
            tag_id (int): The tag ID.

        Returns:
            Document: The updated document.
        """
        logger.info("Removing tag '%s' from document '%s'", tag_id, document_id)
        async def _update():
            async with self._client:
                doc = await self._client.documents(document_id)
                new_tags = [t for t in doc.tags if t != tag_id]
                return await doc.update(tags=new_tags)

        return self._run(_update())

    def update_document_title(self, document_id: int, title: str) -> Document:
        """
        Updates the title of a document.

        Args:
            document_id (int): The document ID.
            title (str): The new title.

        Returns:
            Document: The updated document.
        """
        logger.info("Updating document title for id '%s' to '%s'", document_id, title)
        async def _update():
            async with self._client:
                doc = await self._client.documents(document_id)
                return await doc.update(title=title)

        return self._run(_update())

    def update_document_date(self, document_id: int, created: str) -> Document:
        """
        Updates the created date of a document.

        Args:
            document_id (int): The document ID.
            created (str): The new created date (YYYY-MM-DD).

        Returns:
            Document: The updated document.
        """

        async def _update():
            async with self._client:
                doc = await self._client.documents(document_id)
                return await doc.update(created=created)

        return self._run(_update())

    def download_document(self, document_id: int) -> bytes:
        """
        Downloads a document.

        Args:
            document_id (int): The document ID.

        Returns:
            bytes: The document content as bytes.
        """

        async def _download():
            async with self._client:
                doc = await self._client.documents(document_id)
                return await doc.download()

        return self._run(_download())

    def create_tag(self, name: str) -> Tag:
        """
        Creates a new tag.

        Args:
            name (str): The tag name.

        Returns:
            Tag: The created tag.
        """

        async def _create():
            async with self._client:
                return await self._client.tags.create(name=name)

        return self._run(_create())

    def delete_tag(self, tag_id: int) -> None:
        """
        Deletes a tag.

        Args:
            tag_id (int): The tag ID.
        """

        async def _delete():
            async with self._client:
                await self._client.tags.delete(tag_id)

        self._run(_delete())

    def delete_document(self, document_id: int) -> None:
        """
        Deletes a document.

        Args:
            document_id (int): The document ID.
        """

        async def _delete():
            async with self._client:
                await self._client.documents.delete(document_id)

        self._run(_delete())

    def close(self):
        """
        Closes the Paperless session.
        """

        async def _close():
            await self._client.close()

        self._run(_close())

def setup_logging():
    logging.basicConfig(level=logging.INFO)

    # Define a custom formatter class
    class CustomFormatter(colorlog.ColoredFormatter):
        def format(self, record):
            self._style._fmt = "(%(log_color)s%(levelname)s%(reset)s) %(message)s"
            return super().format(record)

    # Configure colored logging with the custom formatter
    handler = colorlog.StreamHandler()
    handler.setFormatter(
        CustomFormatter(
            # Initial format string (will be overridden in the formatter)
            "",
            log_colors={
                "DEBUG": "green",
                "INFO": "blue",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "red,bg_white",
            },
        )
    )

    root_logger = logging.getLogger()
    root_logger.handlers = []  # Clear existing handlers
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)

    # Suppress logs from the 'requests' library below ERROR level
    logging.getLogger("urllib3").setLevel(logging.ERROR)
    logging.getLogger("requests").setLevel(logging.ERROR)

    return root_logger

if __name__ == "__main__":
    try:
        logger = setup_logging()
        logger.info('Starting...')
        load_dotenv()

        DEFAULT_URL = os.getenv("PAPERLESS_URL")
        DEFAULT_KEY = os.getenv("PAPERLESS_KEY")
        DEFAULT_TAG = "needs-description"
        OPENAI_URL = os.getenv('PAPERLESS_OPENAI_URL')
        OPENAI_KEY = os.getenv('PAPERLESS_OPENAI_API_KEY')

        parser = argparse.ArgumentParser(description="Fetch documents with a specific tag from Paperless NGX.")
        parser.add_argument('--url', type=str, default=DEFAULT_URL, help="The base URL of the Paperless NGX instance")
        parser.add_argument('--key', type=str, default=DEFAULT_KEY, help="The API key for the Paperless NGX instance")
        parser.add_argument('--tag', type=str, default=DEFAULT_TAG, help="Tag to filter documents (default: 'needs-description')")
        parser.add_argument('--prompt', type=str, default=None, help="Prompt to use for OpenAI")
        parser.add_argument('--force-openai', action='store_true', help="Force the use of OpenAI, instead of urls or models loaded from env vars or other parameters")
        parser.add_argument('--verbose', '-v', action='store_true', help="Verbose output")
        
        args = parser.parse_args()

        if args.verbose:
            logger.setLevel(logging.DEBUG)

        if not args.url:
            logger.error("PAPERLESS_URL environment variable is not set.")
            sys.exit(1)

        if not args.key:
            logger.error("PAPERLESS_KEY environment variable is not set.")
            sys.exit(1)

        paperless = PaperlessWrapper(
            host=args.url, 
            token=args.key
        )

        items = paperless.get_documents_by_tag('needs-description')
        logger.info('Found %s items', len(items))
        for i, item in enumerate(items):
            logger.info('Tag: %s', item)
            if i % 3 == 0:
                break

    except KeyboardInterrupt:
        logger.info("Script cancelled by user.")
        sys.exit(0)