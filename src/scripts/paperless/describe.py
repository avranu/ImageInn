"""*********************************************************************************************************************
*                                                                                                                      *
*                                                                                                                      *
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
from pathlib import Path
import sys
import os
import logging
import colorlog
import requests
from alive_progress import alive_bar
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator
from openai import OpenAI
import fitz

logger = logging.getLogger(__name__)

class Paperless(BaseModel):
    """
    Main class to handle the script's operations.
    """
    max_threads: int = 0
    paperless_url : str = Field(..., env='PAPERLESS_URL')
    paperless_key : str | None = Field(..., env='PAPERLESS_KEY')
    paperless_tag : str | None = Field('needs-description', env='PAPERLESS_TAG')
    openai_key : str | None = Field(..., env='OPENAI_API_KEY')
    openai_prompt : str | None = Field(..., env='OPENAI_PROMPT')
    _progress_bar = PrivateAttr(default=None)
    _progress_message: str | None = PrivateAttr(default=None)
    _openai : OpenAI | None = PrivateAttr(default=None)
    
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def progress_bar(self) -> alive_bar:
        if not self._progress_bar:
            self._progress_bar = alive_bar(title='Running', unknown='waves')
        return self._progress_bar

    @property
    def openai(self) -> OpenAI:
        if not self._openai:
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

    def get(self, url_path : str, params : dict | None = None) -> dict | None:
        """
        Fetches data from the Paperless NGX instance.

        Args:
            url_path (str): The URL path to fetch data from.
            params (dict): Query parameters to include in the request.

        Returns:
            dict: The response data as a dictionary.
        """
        try:
            logger.debug(f"Fetching data from '{self.paperless_url}'...")
            headers = {"Authorization": f"Token {self.paperless_key}"}
            response = requests.get(
                f"{self.paperless_url}/{url_path}",
                params=params,
                headers=headers
            )
            response.raise_for_status()
            data = response.json()
            logger.debug(f"Successfully fetched data from '{self.paperless_url}'")
            return data
        except requests.RequestException as e:
            logger.error(f"Failed to fetch data: {e}")
            
        return None

    def patch(self, url_path : str, payload : dict) -> dict | None:
        """
        Sends a PATCH request to the Paperless NGX instance.

        Args:
            url_path (str): The URL path to send the PATCH request to.
            payload (dict): The payload to send with the request.

        Returns:
            dict: The response data as a dictionary.
        """
        try:
            logger.debug(f"Sending PATCH request to '{self.paperless_url}'...")
            headers = {"Authorization": f"Token {self.paperless_key}"}
            response = requests.patch(
                f"{self.paperless_url}/{url_path}",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            data = response.json()
            logger.debug(f"Successfully sent PATCH request to '{self.paperless_url}'")
            return data
        except requests.RequestException as e:
            logger.error(f"Failed to send PATCH request: {e}")
            
        return None

    def fetch_documents_with_tag(self, tag_name: str | None = None) -> list[dict] | None:
        """
        Fetches documents with the specified tag from the Paperless NGX instance.

        Args:
            tag_name (str): The tag to filter documents by.

        Returns:
            list[dict]: A list of document objects with the specified tag.
        """
        tag_name = tag_name or self.paperless_tag
        results = []

        if not (data := self.get('api/documents/', params={"tag": tag_name})):
            return results
        
        results = data.get("results", [])
        logger.debug(f'Found {len(results)} documents with the tag "{tag_name}"')
        return results
    
    def add_note(self, document: dict, note: str) -> dict:
        """
        Adds a note to a document.

        NOTE: Not apparently working.

        Args:
            document (dict): The document to add the note to.
            note (str): The note to add.

        Returns:
            dict: The document with the note added.
        """
        logger.debug(f"Adding note to document {document['id']}: {note}")
        payload = {"notes": note}
        data = self.patch(f"api/documents/{document['id']}/", payload)
        logger.debug(f"Successfully added note to document {document['id']} -> {data}")
        return data

    def remove_tag(self, document: dict, tag_name: str) -> dict:
        """
        Removes a tag from a document.

        Args:
            document (dict): The document to remove the tag from.
            tag_name (str): The tag to remove.

        Returns:
            dict: The document with the tag removed.
        """
        logger.debug(f"Removing tag '{tag_name}' from document {document['id']}")
        tags = [tag for tag in document.get("tags", []) if tag != tag_name]
        payload = {"tags": tags}
        data = self.patch(f"api/documents/{document['id']}/", payload)
        logger.debug(f"Successfully removed tag '{tag_name}' from document {document['id']}")
        return data

    def add_tag(self, document: dict, tag_name: str) -> dict:
        """
        Adds a tag to a document.

        Args:
            document (dict): The document to add the tag to.
            tag_name (str): The tag to add.

        Returns:
            dict: The document with the tag added.
        """
        logger.debug(f"Adding tag '{tag_name}' to document {document['id']}")
        tags = document.get("tags", []) + [tag_name]
        payload = {"tags": tags}
        data = self.patch(f"api/documents/{document['id']}/", payload)
        logger.debug(f"Successfully added tag '{tag_name}' to document {document['id']}")
        return data

    def download_document(self, document: dict) -> bytes | None:
        """
        Downloads a document from Paperless NGX.

        Access /api/documents/{pk}/download

        Args:
            document (dict): The document to download.

        Returns:
            bytes: The content of the document.
        """
        try:
            logger.debug(f"Downloading document {document['id']} from Paperless...")

            response = requests.get(
                f"{self.paperless_url}/api/documents/{document['id']}/download/",
                headers={"Authorization": f"Token {self.paperless_key}"}
            )
            response.raise_for_status()
            content = response.content
            logger.debug(f"Downloaded document {document['id']} from Paperless")
            return content
        except requests.RequestException as e:
            logger.error(f"Failed to download document {document['id']}: {e}")

        return None

    def extract_first_image_from_pdf(self, pdf_bytes: bytes) -> bytes | None:
        """
        Extracts the first image from a PDF file.

        Args:
            pdf_bytes (bytes): The PDF file content as bytes.

        Returns:
            bytes | None: The first image as bytes or None if no image is found.
        """
        try:
            # Open the PDF from bytes
            pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")

            for page_number in range(len(pdf_document)):
                page = pdf_document[page_number]
                images = page.get_images(full=True)
                
                if not images:
                    continue

                # Extract the first image on the page
                first_image = images[0]
                xref = first_image[0]
                base_image = pdf_document.extract_image(xref)
                image_bytes = base_image["image"]

                logger.debug(f"Extracted first image from page {page_number + 1} of the PDF.")
                return image_bytes

            logger.warning("No images found in the PDF.")
        except Exception as e:
            logger.error(f"Error extracting image from PDF: {e}")

        return None

    def append_document_content(self, document: dict, content: str) -> dict:
        """
        Appends content to a document.

        Args:
            document (dict): The document to append content to.
            content (str): The content to append.

        Returns:
            dict: The document with the content appended.
        """
        logger.debug(f"Appending content to document {document['id']}")
        payload = {"content": document["content"] + "\n\r\n\r" + content}
        data = self.patch(f"api/documents/{document['id']}/", payload)
        logger.debug(f"Successfully appended content to document {document['id']} -> {data}")
        return data

    def describe_document(self, document: dict) -> dict:
        """
        Describes a single document using OpenAI's GPT-4o model.

        Args:
            document (dict): The document to describe.

        Returns:
            dict: The document with the description added.
        """
        try:
            logger.debug(f"Describing document {document['id']} using OpenAI...")
            
            if not (content := self.download_document(document)):
                logger.error("Failed to download document content.")
                return document

            # Determine if the document is a PDF
            if document['original_file_name'].lower().endswith('.pdf'):
                logger.debug(f"Document {document['id']} is a PDF. Extracting the first image...")
                if not (content := self.extract_first_image_from_pdf(content)):
                    logger.error(f"No images found in PDF for document {document['id']}.")
                    return document

            # Convert file content to base64
            base64_image = base64.b64encode(content).decode("utf-8")
            
            response = self.openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": self.openai_prompt,
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                            },
                        ],
                    }
                ],
                max_tokens=500,
            )
            description = f"IMAGE DESCRIPTION: {response.choices[0].message.content}"
            logger.debug(f"Generated description for document {document['id']}: {description}")

            # Add the description as a note
            updated_document = self.add_note(document, description)

            # Append the description to the document content
            updated_document = self.append_document_content(updated_document, description)

            # Remove the tag after processing
            updated_document = self.remove_tag(updated_document, self.paperless_tag)

            # Add the "described" tag
            updated_document = self.add_tag(updated_document, "described")

            return updated_document
        except requests.RequestException as e:
            logger.error(f"Failed to describe document {document['id']}: {e}")

        return document

    def describe_documents(self, documents : list[dict] | None = None) -> list[dict]:
        """
        Describes a list of documents using OpenAI's GPT-4o model.

        Args:
            documents (list[dict]): The documents to describe.

        Returns:
            list[dict]: The documents with the descriptions added.
        """
        documents = documents or self.fetch_documents_with_tag()
        
        results = []
        with alive_bar(title='Running', unknown='waves') as self._progress_bar:
            for document in documents:
                results.append(self.describe_document(document))
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

    return root_logger

class ArgNamespace(argparse.Namespace):
    """
    A custom namespace class for argparse.
    """
    verbose: bool = False
    tag: str
    url: str
    key: str
    prompt: str

def main():
    try:
        logger = setup_logging()
        load_dotenv()

        DEFAULT_URL = os.getenv("PAPERLESS_URL")
        DEFAULT_KEY = os.getenv("PAPERLESS_KEY")
        DEFAULT_TAG = "needs-description"
        DEFAULT_PROMPT = os.getenv('OPENAI_PROMPT', 'This image is from the Hudson River Psychiatric Center, taken when it was in operation. It may depict buildings, staff, or patients, and serves as a historical document that will be used to help document and research life in the asylum. Please describe it in detail. Ensure you use keywords that will help find the photo when searching. Describe everything in the image, transcribe any text you see, describe the tone, the colors, and whether the photo was taken indoors or outdoors. Be as thorough and detailed as you possibly can.')
        OPENAI_KEY = os.getenv('OPENAI_API_KEY')

        parser = argparse.ArgumentParser(description="Fetch documents with a specific tag from Paperless NGX.")
        parser.add_argument('--url', type=str, default=DEFAULT_URL, help="The base URL of the Paperless NGX instance")
        parser.add_argument('--key', type=str, default=DEFAULT_KEY, help="The API key for the Paperless NGX instance")
        parser.add_argument('--tag', type=str, default=DEFAULT_TAG, help="Tag to filter documents (default: 'needs-description')")
        parser.add_argument('--prompt', type=str, default=DEFAULT_PROMPT, help="The prompt to use for OpenAI's model")
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

        paperless = Paperless(
            paperless_url=args.url, 
            paperless_key=args.key, 
            paperless_tag=args.tag, 
            openai_key=OPENAI_KEY,
            openai_prompt=args.prompt
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