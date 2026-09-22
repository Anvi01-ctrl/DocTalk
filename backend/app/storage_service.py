"""
DocTalk — Azure Blob Storage service.

Handles uploading, downloading, deleting, and listing documents
in Azure Blob Storage.

Authentication priority:
  1. Connection string (AZURE_STORAGE_CONNECTION_STRING)
  2. DefaultAzureCredential with account URL (AZURE_STORAGE_ACCOUNT_URL)
"""

import os
import logging
from typing import Optional

from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv


load_dotenv()

logger = logging.getLogger(__name__)


# Configuration from environment
STORAGE_ACCOUNT_URL = os.getenv("AZURE_STORAGE_ACCOUNT_URL")
STORAGE_CONTAINER = os.getenv("AZURE_STORAGE_CONTAINER", "documents")
CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")


def _get_blob_service_client() -> BlobServiceClient:
    """
    Create a BlobServiceClient.

    Tries connection string first, then falls back to
    DefaultAzureCredential with account URL.
    """
    if CONNECTION_STRING:
        return BlobServiceClient.from_connection_string(CONNECTION_STRING)

    if STORAGE_ACCOUNT_URL:
        from azure.identity import DefaultAzureCredential
        credential = DefaultAzureCredential()
        return BlobServiceClient(STORAGE_ACCOUNT_URL, credential=credential)

    raise RuntimeError(
        "Neither AZURE_STORAGE_CONNECTION_STRING nor "
        "AZURE_STORAGE_ACCOUNT_URL is set. "
        "Check your .env file or environment variables."
    )


def _get_container_client():
    """Get the container client for the documents container."""
    service_client = _get_blob_service_client()
    return service_client.get_container_client(STORAGE_CONTAINER)


async def upload_blob(document_id: str, filename: str, file_bytes: bytes) -> str:
    """
    Upload a file to Azure Blob Storage.

    Blob path: <document_id>/<filename>

    Each document gets its own folder keyed by UUID,
    so duplicate filenames never collide.

    Returns the blob path.
    """
    blob_path = f"{document_id}/{filename}"

    try:
        container_client = _get_container_client()
        blob_client = container_client.get_blob_client(blob_path)

        blob_client.upload_blob(file_bytes, overwrite=True)

        logger.info(f"Uploaded blob: {blob_path}")
        return blob_path

    except Exception as error:
        logger.error(f"Failed to upload blob {blob_path}: {error}")
        raise


async def download_blob(blob_path: str) -> Optional[bytes]:
    """
    Download a blob's contents from Azure Blob Storage.

    Returns the file bytes, or None if the blob is not found.
    """
    try:
        container_client = _get_container_client()
        blob_client = container_client.get_blob_client(blob_path)

        stream = blob_client.download_blob()
        return stream.readall()

    except Exception as error:
        error_code = getattr(error, "error_code", "")

        if error_code == "BlobNotFound":
            logger.warning(f"Blob not found: {blob_path}")
            return None

        logger.error(f"Failed to download blob {blob_path}: {error}")
        raise


async def delete_blob(blob_path: str) -> bool:
    """
    Delete a blob from Azure Blob Storage.

    Returns True if deleted, False if not found.
    """
    try:
        container_client = _get_container_client()
        blob_client = container_client.get_blob_client(blob_path)

        blob_client.delete_blob()

        logger.info(f"Deleted blob: {blob_path}")
        return True

    except Exception as error:
        error_code = getattr(error, "error_code", "")

        if error_code == "BlobNotFound":
            logger.warning(f"Blob not found: {blob_path}")
            return False

        logger.error(f"Failed to delete blob {blob_path}: {error}")
        raise


async def blob_exists(blob_path: str) -> bool:
    """Check if a blob exists in storage."""
    try:
        container_client = _get_container_client()
        blob_client = container_client.get_blob_client(blob_path)
        blob_client.get_blob_properties()
        return True

    except Exception:
        return False


def list_blobs(prefix: str = "") -> list[dict]:
    """
    List blobs in the container, optionally filtered by prefix.

    Returns a list of dicts with blob name and size.
    """
    try:
        container_client = _get_container_client()
        blobs = container_client.list_blobs(name_starts_with=prefix or None)

        return [
            {
                "name": blob.name,
                "size": blob.size,
                "last_modified": str(blob.last_modified) if blob.last_modified else None,
            }
            for blob in blobs
        ]

    except Exception as error:
        logger.error(f"Failed to list blobs: {error}")
        raise
