import json
import os
import logging
from typing import Optional
from datetime import datetime, timedelta

from app.document_models import DocumentMetadata


logger = logging.getLogger(__name__)


# Metadata file location (next to the backend folder)
METADATA_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "documents_metadata.json",
)


def _load_metadata() -> dict[str, dict]:
    """Load all document metadata from the JSON file."""
    if not os.path.exists(METADATA_FILE):
        return {}

    try:
        with open(METADATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    except (json.JSONDecodeError, IOError) as error:
        logger.error(f"Failed to load metadata: {error}")
        return {}


def _save_metadata(metadata: dict[str, dict]) -> None:
    """Save all document metadata to the JSON file."""
    try:
        with open(METADATA_FILE, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

    except IOError as error:
        logger.error(f"Failed to save metadata: {error}")
        raise


def save_document(doc: DocumentMetadata) -> None:
    """Save or update a single document's metadata."""
    metadata = _load_metadata()
    metadata[doc.document_id] = doc.model_dump()
    _save_metadata(metadata)

    logger.info(f"Saved metadata for document: {doc.document_id}")


def get_document(document_id: str) -> Optional[DocumentMetadata]:
    """Retrieve a single document's metadata by ID."""
    metadata = _load_metadata()
    doc_data = metadata.get(document_id)

    if doc_data is None:
        return None

    return DocumentMetadata(**doc_data)


def get_all_documents() -> list[DocumentMetadata]:
    """Retrieve all document metadata."""
    metadata = _load_metadata()

    return [
        DocumentMetadata(**doc_data)
        for doc_data in metadata.values()
    ]


def delete_document(document_id: str) -> bool:
    """
    Delete a document's metadata by ID.
    Returns True if deleted, False if not found.
    """
    metadata = _load_metadata()

    if document_id not in metadata:
        return False

    del metadata[document_id]
    _save_metadata(metadata)

    logger.info(f"Deleted metadata for document: {document_id}")
    return True


def get_expired_documents(days: int = 30) -> list[DocumentMetadata]:
    """
    Retrieve all documents whose uploaded_at timestamp
    is older than the specified number of days.

    Used by the 30-day retention policy to find documents
    that should be automatically cleaned up.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    metadata = _load_metadata()
    expired = []

    for doc_data in metadata.values():
        uploaded_at = doc_data.get("uploaded_at", "")
        if uploaded_at:
            try:
                upload_date = datetime.fromisoformat(uploaded_at)
                if upload_date < cutoff:
                    expired.append(DocumentMetadata(**doc_data))
            except (ValueError, TypeError):
                # If timestamp is unparseable, skip it
                continue

    return expired
