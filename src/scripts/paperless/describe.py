"""*********************************************************************************************************************
*                                                                                                                      *
*                                                                                                                      *
    Run with:
        cd src
        python -m scripts.paperless.describe
*                                                                                                                      *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    METADATA:                                                                                                         *
*                                                                                                                      *
*        File:    describe.py                                                                                          *
*        Project: imageinn                                                                                             *
*        Version: 0.1.0                                                                                                *
*        Created: 2025-01-23                                                                                           *
*        Author:  Jess Mann                                                                                            *
*        Email:   jess.a.mann@gmail.com                                                                                *
*        Copyright (c) 2025 Jess Mann                                                                                  *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    LAST MODIFIED:                                                                                                    *
*                                                                                                                      *
*        2025-01-23     By Jess Mann                                                                                   *
*                                                                                                                      *
*********************************************************************************************************************"""
from __future__ import annotations

import argparse
import base64
from io import BytesIO
import json
from pathlib import Path
import re
import sys
import os
import logging
from typing import Any, AsyncIterator, Iterator, Optional, List
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

# Import pypaperless
from pypaperless.models import Document, Tag
from scripts.paperless.wrapper import PaperlessWrapper

logger = logging.getLogger(__name__)

OPENAI_ACCEPTED_FORMATS = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf']
MIME_TYPES = {
    'png': 'image/png',
    'jpeg': 'image/jpeg',
    'jpg': 'image/jpeg',
    'gif': 'image/gif',
    'webp': 'image/webp',
}

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
TAG_DESCRIBED = 162
TAG_NEEDS_DESCRIPTION = 161
TAG_NEEDS_TITLE = 190
TAG_NEEDS_DATE = 191
TAG_CLEANUP = 77
TAG_HRSH = 2
TAG_NYS_OMH = 229
DOCUMENT_TYPE_PHOTO = 8
DOCUMENT_TYPE_DETAIL_CLOSEUP = 30
DOCUMENT_TYPE_ITEMS = 11
VERSION = "0.2.2"

class DescribePhotos(BaseModel):
    """
    Describes photos in the Paperless NGX instance using an LLM (such as OpenAI's GPT-4o model).
    """
    max_threads: int = 0
    paperless_url: str = Field(..., env='PAPERLESS_URL')
    paperless_key: str | None = Field(..., env='PAPERLESS_KEY')
    paperless_tag: str | None = Field('needs-description', env='PAPERLESS_TAG')
    openai_key: str | None = Field(default=None, env='PAPERLESS_OPENAI_API_KEY')
    openai_url: str | None = Field(None, env='PAPERLESS_OPENAI_URL')
    openai_model: str = Field(default=DEFAULT_OPENAI_MODEL, env="PAPERLESS_OPENAI_MODEL")
    force_openai: bool = Field(default=False)
    prompt: str | None = Field(None)
    _jinja_env: Environment = PrivateAttr(default=None)
    _progress_bar = PrivateAttr(default=None)
    _progress_message: str | None = PrivateAttr(default=None)
    _openai: OpenAI | None = PrivateAttr(default=None)
    _paperless_client: PaperlessWrapper = PrivateAttr(default=None)
    
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def progress_bar(self) -> alive_bar:
        if not self._progress_bar:
            self._progress_bar = alive_bar(title='Running', unknown='waves')
        return self._progress_bar

    @property
    def paperless_client(self) -> PaperlessWrapper:
        """Return or initialize the Paperless instance."""
        if not self._paperless_client:
            self._paperless_client = PaperlessWrapper(self.paperless_url, self.paperless_key)
        return self._paperless_client

    @property
    def openai(self) -> OpenAI:
        if not self._openai:
            if self.force_openai:
                if self.openai_url:
                    # Reset the model for openai
                    self.openai_model = DEFAULT_OPENAI_MODEL
                    self.openai_url = None
                    
            if self.openai_url:
                logger.info('Using custom OpenAI URL: %s', self.openai_url)
                self._openai = OpenAI(api_key=self.openai_key, base_url=self.openai_url)
            else:
                logger.info('Using default OpenAI URL')
                self._openai = OpenAI()
        return self._openai

    @field_validator('max_threads', mode='before')
    def validate_max_threads(cls, value):
        # Sensible default
        if not value:
            # default is between 1-4 threads. More than 4 presumptively stresses the HDD non-optimally.
            return max(1, min(4, round(os.cpu_count() / 2)))
            
        if value < 1:
            raise ValueError('max_threads must be a positive integer.')
        return value

    @field_validator('openai_key', mode="before")
    def validate_openai_key(cls, value):
        if not value and not (value := os.getenv('OPENAI_API_KEY')):
            logger.warning('OPENAI_API_KEY environment variable is not set.')
            raise ValueError('OPENAI_API_KEY environment variable is not set.')
        return value

    @property
    def jinja_env(self) -> Environment:
        if not self._jinja_env:
            templates_path = Path(__file__).parent / 'templates'
            self._jinja_env = Environment(loader=FileSystemLoader(str(templates_path)), autoescape=True)
        return self._jinja_env

    def choose_template(self, document: Document) -> str:
        """
        Choose a jinja template for a document
        """
        # If the document type is NOT "photo", choose paperwork.jinja
        if document.document_type not in [DOCUMENT_TYPE_PHOTO, DOCUMENT_TYPE_DETAIL_CLOSEUP, DOCUMENT_TYPE_ITEMS]:
            return "paperwork.jinja"
        
        # If it has the "cleanup" tag, choose cleanup_photo.jinja
        if any(tag.id == TAG_CLEANUP for tag in document.tags):
            return "cleanup_photo.jinja"

        # If the date is prior to 2010, choose old_photo.jinja
        if document.created and document.created.year < 2010:
            return "old_photo.jinja"

        # Newer photos
        return "comparison_photo.jinja"

    def get_prompt(self, document: Document) -> str:
        """
        Generate a prompt to sent to openai using a jinja template.
        """
        if self.prompt:
            return self.prompt
        
        template_name = self.choose_template(document)
        template_path = f"output_json/{template_name}"
        logger.debug('Using template: %s', template_path)
        template = self.jinja_env.get_template(template_path)
        location = self.get_location(document)

        if not (description := template.render(document=document, location=location)):
            raise ValueError("Failed to generate prompt.")

        return description

    def get_location(self, document: Document) -> str | None:
        """
        Get the location of a document.
        """
        template = None

        if any(tag.id == TAG_HRSH for tag in document.tags):
            template = self.jinja_env.get_template("locations/hrsh.jinja")
        if any(tag.id == TAG_NYS_OMH for tag in document.tags):
            template = self.jinja_env.get_template("locations/nys_omh.jinja")

        if template:
            return template.render(document=document)
        return None
        
    def filter_documents(self, documents: List[Document]) -> Iterator[Document]:
        """
        Yields documents from the Paperless NGX instance that need description.

        Args:
            documents (List[Document]): The documents to filter

        Yields:
            Iterator[Document]: The filtered documents.
        """
        for document in documents:
            # If content includes "IMAGE DESCRIPTION", skip
            if document.content and "IMAGE DESCRIPTION" in document.content:
                logger.debug("Skipping document with existing description")
                continue

            # If tags include "described", skip
            if any(tag.id == TAG_DESCRIBED for tag in document.tags):
                logger.debug("Skipping document with 'described' tag")
                continue

            # If tags DO NOT include "needs-description", skip
            if not any(tag.id == TAG_NEEDS_DESCRIPTION for tag in document.tags):
                logger.debug("Skipping document without 'needs-description' tag")
                continue

            # Check it is a supported extension
            original_filename = document.original_filename or ""
            if not any(original_filename.lower().endswith(ext) for ext in OPENAI_ACCEPTED_FORMATS):
                logger.debug("Skipping document with unsupported extension: %s", original_filename)
                continue

            yield document

    def fetch_documents_with_tag(self, tag_name: str | None = None) -> AsyncIterator[Document]:
        """Fetches documents with the specified tag from Paperless NGX."""
        tag_name = tag_name or self.paperless_tag
        tag_id = None

        for tag in self.paperless_client.get_tags():
            if tag.name == tag_name:
                tag_id = tag.id
                break

        if tag_id is None:
            logger.error(f"Tag '{tag_name}' not found")
            return

        for doc in self.paperless_client.get_documents():
            if tag_id in doc.tags:
                yield doc

    def remove_tag(self, document: Document, tag_id: int) -> Document:
        """Removes a tag from a document."""
        updated_tags = [tag for tag in document.tags if tag.id != tag_id]
        return document.update(tags=updated_tags)


    def add_tag(self, document: Document, tag_id: int) -> Document:
        """Adds a tag to a document."""
        if tag_id not in document.tags:
            updated_tags = document.tags + [tag_id]
            return document.update(tags=updated_tags)
        return document

    def download_document(self, document: Document) -> bytes | None:
        """Downloads a document from Paperless NGX."""
        try:
            logger.debug(f"Downloading document {document.id} from Paperless...")
            content = document.download()
            logger.debug(f"Downloaded document {document.id}")
            return content
        except Exception as e:
            logger.error(f"Failed to download document {document.id}: {e}")
            return None

    def extract_images_from_pdf(self, pdf_bytes: bytes, max_images: int = 2) -> list[bytes]:
        """
        Extracts the first image from a PDF file.

        Args:
            pdf_bytes (bytes): The PDF file content as bytes.

        Returns:
            bytes | None: The first {max_images} images as bytes or None if no image is found.
        """
        results = []
        try:
            # Open the PDF from bytes
            pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")

            for page_number in range(len(pdf_document)):
                if len(results) >= max_images:
                    break
                
                page = pdf_document[page_number]
                images = page.get_images(full=True)
                
                if not images:
                    continue

                for image in images:
                    if len(results) >= max_images:
                        break

                    try:
                        xref = image[0]
                        base_image = pdf_document.extract_image(xref)
                        image_bytes = base_image["image"]
                        results.append(image_bytes)
                        logger.debug(f"Extracted image from page {page_number + 1} of the PDF.")
                    except Exception as e:
                        count = len(results)
                        logger.error(f"Failed to extract one image from page {page_number} of PDF. Result count {count}: {e}")
                        if count < 1:
                            raise
 
            if not results:
                raise ValueError("No images found in the PDF.")

        except Exception as e:
            logger.error(f"extract_images_from_pdf: Error extracting image from PDF: {e}")
            raise

        return results

    def append_document_content(self, document: Document, content: str) -> Document:
        """
        Appends content to a document.

        Args:
            document (Document): The document to append content to.
            content (str): The content to append.

        Returns:
            Document: The document with the content appended.
        """
        if not content:
            raise ValueError("Content should not be empty.")

        current_content = document.content or ""
        new_content = current_content + "\n\r\n\r" + content

        logger.debug(f"Appending content to document {document.id}")
        
        # Use pypaperless to update the document content
        updated_doc = self.paperless_client.documents.update(
            document.id,
            content=new_content
        )
        
        logger.debug(f"Successfully appended content to document {document.id}")
        return updated_doc

    def update_document_title(self, document: Document, title: str) -> Document:
        """
        Updates the title of a document.

        Args:
            document (Document): The document to update.
            title (str): The new title.

        Returns:
            Document: The updated document.
        """
        title = str(title).strip()
        if not title or len(title) < 10:
            raise ValueError("Title should be at least 10 characters.")
        
        logger.debug(f"Updating title of document {document.id} to '{title}'")
        
        # Use pypaperless to update the document title
        updated_doc = self.paperless_client.documents.update(
            document.id,
            title=title
        )
        
        logger.debug(f"Successfully updated title of document {document.id} to '{title}'")
        return updated_doc

    def parse_date(self, date_str: str) -> date | None:
        """
        Parses a date string.

        Args:
            date_str (str): The date string to parse.

        Returns:
            date: The parsed date.
        """
        if not date_str:
            return None
        
        date_str = str(date_str).strip()
        
        # "Date unknown" or "Unknown date" or "No date"
        if re.match(r"(date unknown|unknown date|no date|none|unknown|n/?a)$", date_str, re.IGNORECASE):
            return None
        
        # Handle "circa 1950"
        if matches := re.match(r"((around|circa|mid|early|late|before|after) *)?(\d{4})s?$", date_str, re.IGNORECASE):
            date_str = f'{matches.group(3)}-01-01'
        
        parsed_date = dateparser.parse(date_str)
        if not parsed_date:
            raise ValueError(f"Invalid date format: {date_str=}")
        return parsed_date.date()

    def update_document_date(self, document: Document, date: str | date | datetime) -> Document:
        """
        Updates the date of a document.

        Args:
            document (Document): The document to update.
            date (str): The new date in 'YYYY-MM-DD' format.

        Returns:
            Document: The updated document.
        """
        parsed_date = date
        if isinstance(parsed_date, str):
            parsed_date = self.parse_date(parsed_date)
        if isinstance(parsed_date, datetime):
            parsed_date = parsed_date.date()
            
        if not parsed_date:
            return document
        
        logger.debug(f"Updating date of document {document.id} to '{parsed_date}'")
        
        # Use pypaperless to update the document date
        updated_doc = self.paperless_client.documents.update(
            document.id,
            created=parsed_date.strftime("%Y-%m-%d")
        )
        
        logger.debug(f"Successfully updated date of document {document.id} to '{parsed_date}'")
        return updated_doc

    def standardize_image_contents(self, content: bytes) -> list[str]:
        """
        Standardize image contents to base64-encoded PNG format.
        """    
        try:
            return [self._convert_to_png(content)]
        except Exception as e:
            logger.debug(f"Failed to convert contents to png, will try other methods: {e}")

        # Interpret it as a pdf
        if (image_contents_list := self.extract_images_from_pdf(content)):
            return [self._convert_to_png(image) for image in image_contents_list]

        raise ValueError("Unable to standardize image.")

    def _convert_to_png(self, content: bytes) -> str:
        img = Image.open(BytesIO(content))

        # Resize large images
        if img.size[0] > 1024 or img.size[1] > 1024:
            img.thumbnail((1024, 1024))

        # Re-save it as PNG in-memory
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        # Convert to base64
        return base64.b64encode(buf.read()).decode("utf-8")
            
    def _send_describe_request(self, content: bytes | list[bytes], document: Document) -> str | None:
        """
        Send an image description request to OpenAI.

        Args:
            content: Document content as bytes or list of bytes
            document: The document to describe

        Returns:
            str: The description generated by OpenAI
        """
        description: str | None = None
        if not isinstance(content, list):
            content = [content]
            
        try:
            # Convert all images to standardized format
            images = []
            for image_content in content:
                images.extend(self.standardize_image_contents(image_content))

            message_contents = [
                {
                    "type": "text",
                    "text": self.get_prompt(document),
                }
            ]
            
            for image in images:
                message_contents.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image}"},
                })
            
            response = self.openai.chat.completions.create(
                model=self.openai_model,
                messages=[
                    {
                        "role": "user",
                        "content": message_contents
                    }
                ],
                max_tokens=500,
            )
            description = response.choices[0].message.content
            logger.debug(f"Generated description: {description}")

        except ValueError as ve:
            logger.warning("Failed to generate description for document #%s: %s. Continuing with next image -> %s", 
                document.id, document.original_filename, ve)

        except UnidentifiedImageError as uii:
            logger.warning('Failed to identify image format for document #%s: %s. Continuing with next image -> %s', 
                document.id, document.original_filename, uii)
        
        except Exception as e:
            logger.error("Unexpected Error generating description for document #%s: %s -> %s", 
                document.id, document.original_filename, e)
            raise

        return description

    def describe_document(self, document: Document) -> Document:
        """
        Describes a single document using OpenAI's GPT-4o model.

        Args:
            document (dict): The document to describe.

        Returns:
            dict: The document with the description added.
        """
        try:
            logger.debug(f"Describing document {document.id} using OpenAI...")
            
            if not (content := self.download_document(document)):
                logger.error("Failed to download document content.")
                return document

            # Ensure accepted format
            if not any(document.original_file_name.lower().endswith(ext) for ext in OPENAI_ACCEPTED_FORMATS):
                logger.error(f"Document {document.id} is not in an accepted format: {document.original_file_name}")
                return document

            try:
                if not (response := self._send_describe_request(content, document)):
                    logger.error(f"OpenAI returned empty description for document {document.id}.")
                    return document
            except openai.BadRequestError as e:
                if "invalid_image_format" not in str(e):
                    logger.error("Failed to generate description for document #%s: %s -> %s", document.id, document.original_file_name, e)
                    return document

                logger.debug("Bad format for document #%s: %s -> %s", document.id, document.original_file_name, e)
                return document
                    
            # Process the response
            self.process_response(response, document)
        except requests.RequestException as e:
            logger.error(f"Failed to describe document {document.id}: {e}")
            raise

        return document

    def parse_json(self, response: str, document: Document) -> dict | None:
        # Attempt to parse response as json
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            logger.debug("Failed to parse response as JSON. Saving response raw in document content. Document #%s: %s", 
                document.id, document.original_filename)

        # If "```json" is present, strip everything before it
        if "```json" in response:
            response = response[response.index("```json") + 7:]
            # Strip everything after "```"
            if "```" in response:
                response = response[:response.index("```")]

        # try again
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            logger.debug('Failed again after stripping json block')

        logger.error('Failed to parse response as JSON. Saving response raw in document content. Document #%s: %s', 
            document.id, document.original_filename)
        self.append_document_content(document, response)
        return None

    def process_response(self, response: str, document: Document) -> Document:
        """
        Process the response from OpenAI and update the document.
        
        Args:
            response (str): The response from OpenAI
            document (Document): The document to update
            
        Returns:
            Document: The updated document
        """
        # Attempt to parse response as json
        if not (parsed_response := self.parse_json(response, document)):
            logger.debug('Unable to process response after failed json parsing')
            return document

        # Check if parsed_response is a dictionary
        if not isinstance(parsed_response, dict):
            logger.error("Parsed response is not a dictionary. Saving response raw in document content. Document #%s: %s", 
                document.id, document.original_filename)
            self.append_document_content(document, response)
            return document
        
        # Attempt to grab "title", "description", "tags", "date" from parsed_response
        title = parsed_response.get("title", None)
        description = parsed_response.get("description", None)
        summary = parsed_response.get("summary", None)
        content = parsed_response.get("content", None)
        tags = parsed_response.get("tags", None)
        date = parsed_response.get("date", None)
        full_description = f"""AI IMAGE DESCRIPTION (v{VERSION}): 
            The following description was provided by an Artificial Intelligence (GPT-4o by OpenAI).
            It may not be fully accurate. Its purpose is to provide keywords and context
            so that the document can be more easily searched.
            Suggested Title: {title}
            Inferred Date: {date}
            Suggested Tags: {tags}
            Previous Title: {document.title}
            Previous Date: {document.created}
        """

        if summary:
            full_description += f"\n\nSummary: {summary}"
        if content:
            full_description += f"\n\nContent: {content}"
        if description:
            full_description += f"\n\nDescription: {description}"
        if not any([description, summary, content]):
            full_description += f"\n\nFull AI Response: {parsed_response}"

        updated_document = document
        
        if title and any(tag.id == TAG_NEEDS_TITLE for tag in document.tags):
            try:
                updated_document = self.update_document_title(updated_document, title)
                updated_document = self.remove_tag(updated_document, TAG_NEEDS_TITLE)
            except Exception as e:
                logger.error("Failed to update document title. Document #%s: %s -> %s", 
                    document.id, document.original_filename, e)

        if date and any(tag.id == TAG_NEEDS_DATE for tag in document.tags):
            try:
                updated_document = self.update_document_date(updated_document, date)
                updated_document = self.remove_tag(updated_document, TAG_NEEDS_DATE)
            except Exception as e:
                logger.error("Failed to update document date. Document #%s: %s -> %s", 
                    document.id, document.original_filename, e)

        # Append the description to the document
        updated_document = self.append_document_content(updated_document, full_description)
        updated_document = self.remove_tag(updated_document, TAG_NEEDS_DESCRIPTION)
        updated_document = self.add_tag(updated_document, TAG_DESCRIBED)
        
        logger.debug(f"Successfully described document {document.id}")
        return updated_document

    def describe_documents(self, documents: list[Document] | None = None) -> list[Document]:
        """
        Describes a list of documents using OpenAI's GPT-4o model.

        Args:
            documents (list[Document]): The documents to describe.

        Returns:
            list[Document]: The documents with the descriptions added.
        """
        if documents is None:
            documents = list(self.fetch_documents_with_tag())
        
        results = []
        with alive_bar(title='Running', unknown='waves') as self._progress_bar:
            for document in documents:
                if (updated_document := self.describe_document(document)):
                    results.append(updated_document)
                self.progress_bar()
        return results


def setup_logging():
    logging.basicConfig(level=logging.INFO)

    # Define a custom formatter class
    class CustomFormatter(colorlog.ColoredFormatter):
        def format(self, record):
            self._style._fmt = '(%(log_color)s%(levelname)s%(reset)s) %(message)s'
            return super().format(record)

    # Configure colored logging with the custom formatter
    handler = colorlog.StreamHandler()
    handler.setFormatter(CustomFormatter(
        # Initial format string (will be overridden in the formatter)
        '',
        log_colors={
            'DEBUG':    'green',
            'INFO':     'blue',
            'WARNING':  'yellow',
            'ERROR':    'red',
            'CRITICAL': 'red,bg_white',
        }
    ))

    root_logger = logging.getLogger()
    root_logger.handlers = []  # Clear existing handlers
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
    
    # Suppress logs from the 'requests' library below ERROR level
    logging.getLogger("urllib3").setLevel(logging.ERROR)
    logging.getLogger("requests").setLevel(logging.ERROR)

    return root_logger

class ArgNamespace(argparse.Namespace):
    """
    A custom namespace class for argparse.
    """
    verbose: bool = False
    tag: str
    url: str
    key: str
    model: str | None = None
    prompt: str | None = None
    force_openai: bool = False

def main():
    try:
        logger = setup_logging()
        load_dotenv()

        DEFAULT_URL = os.getenv("PAPERLESS_URL")
        DEFAULT_KEY = os.getenv("PAPERLESS_KEY")
        DEFAULT_TAG = "needs-description"
        OPENAI_URL = os.getenv('PAPERLESS_OPENAI_URL')
        OPENAI_KEY = os.getenv('PAPERLESS_OPENAI_API_KEY')
        OPENAI_MODEL = os.getenv('PAPERLESS_OPENAI_MODEL', DEFAULT_OPENAI_MODEL)

        parser = argparse.ArgumentParser(description="Fetch documents with a specific tag from Paperless NGX.")
        parser.add_argument('--url', type=str, default=DEFAULT_URL, help="The base URL of the Paperless NGX instance")
        parser.add_argument('--key', type=str, default=DEFAULT_KEY, help="The API key for the Paperless NGX instance")
        parser.add_argument('--model', type=str, default=OPENAI_MODEL, help=f"The OpenAI model to use (default: {DEFAULT_OPENAI_MODEL})")
        parser.add_argument('--tag', type=str, default=DEFAULT_TAG, help="Tag to filter documents (default: 'needs-description')")
        parser.add_argument('--prompt', type=str, default=None, help="Prompt to use for OpenAI")
        parser.add_argument('--force-openai', action='store_true', help="Force the use of OpenAI, instead of urls or models loaded from env vars or other parameters")
        parser.add_argument('--verbose', '-v', action='store_true', help="Verbose output")
        
        args = parser.parse_args(namespace=ArgNamespace())

        if args.verbose:
            logger.setLevel(logging.DEBUG)

        if not args.url:
            logger.error("PAPERLESS_URL environment variable is not set.")
            sys.exit(1)

        if not args.key:
            logger.error("PAPERLESS_KEY environment variable is not set.")
            sys.exit(1)

        paperless = DescribePhotos(
            paperless_url=args.url, 
            paperless_key=args.key, 
            paperless_tag=args.tag, 
            openai_key=OPENAI_KEY,
            openai_url=OPENAI_URL,
            openai_model=OPENAI_MODEL,
            prompt=args.prompt,
            force_openai=args.force_openai
        )
        results = paperless.describe_documents()
        if results:
            logger.info(f"Described {len(results)} documents")
        else:
            logger.info("No documents described.")

    except KeyboardInterrupt:
        logger.info("Script cancelled by user.")
        sys.exit(0)

if __name__ == "__main__":
    main()