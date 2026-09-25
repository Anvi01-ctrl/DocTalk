"""
DocTalk — Document API routes.

Implements the document ingestion and management endpoints:
- POST   /documents/upload    (multi-file upload)
- GET    /documents           (list all documents)
- GET    /documents/{id}      (document details)
- DELETE /documents/{id}      (delete document)
"""

import logging
import uuid
import mimetypes

from fastapi import APIRouter, BackgroundTasks, UploadFile, File, HTTPException

from app.document_models import (
    DocumentMetadata,
    DocumentSummary,
    UploadResult,
    UploadResponse,
)
from app import storage_service
from app import document_service
from app import metadata_store


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents"])


def _background_index(pages, text, document_id, filename):
    """
    Background task: chunk the document text, generate embeddings,
    and upload to Azure AI Search.

    Runs AFTER the upload HTTP response has been sent, so the user
    doesn't have to wait for indexing to complete.
    """
    try:
        from app.chunking_service import chunk_text
        from app.indexing_service import index_chunks

        all_chunks = []
        if pages:
            for page_info in pages:
                page_chunks = chunk_text(
                    text=page_info.text,
                    document_id=document_id,
                    document_name=filename,
                    page_number=page_info.page_number,
                )
                all_chunks.extend(page_chunks)
        else:
            all_chunks = chunk_text(
                text=text,
                document_id=document_id,
                document_name=filename,
                page_number=1,
            )

        if all_chunks:
            index_result = index_chunks(all_chunks)
            logger.info(
                f"Background-indexed {filename}: "
                f"{index_result.get('uploaded', 0)} chunks uploaded"
            )
    except Exception as index_err:
        logger.warning(
            f"Background indexing failed for {filename}: {index_err}. "
            f"Document uploaded but not searchable via RAG."
        )


# Supported file extensions
ALLOWED_EXTENSIONS = {"pdf", "docx", "txt"}

# Extension to MIME type mapping
MIME_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
}


def _get_extension(filename: str) -> str:
    """Extract lowercase file extension from filename."""
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower()


@router.post("/upload", response_model=UploadResponse)
async def upload_documents(
    files: list[UploadFile] = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """
    Upload one or multiple documents.

    Supported file types: PDF, DOCX, TXT.

    Files are processed concurrently for speed. Search indexing
    is deferred to a background task so uploads return quickly.
    """
    if not files:
        raise HTTPException(
            status_code=400,
            detail="No files provided.",
        )

    import asyncio

    async def _process_one(file: UploadFile) -> UploadResult:
        """Process a single file — runs concurrently via gather."""
        filename = file.filename or "unknown"
        extension = _get_extension(filename)

        # Validate extension
        if extension not in ALLOWED_EXTENSIONS:
            return UploadResult(
                filename=filename,
                status="failed",
                error=f"Unsupported file type: .{extension}. "
                      f"Only PDF, DOCX, and TXT are supported.",
            )

        try:
            # Read file bytes
            file_bytes = await file.read()

            if not file_bytes:
                return UploadResult(
                    filename=filename,
                    status="failed",
                    error="File is empty.",
                )

            # Generate unique document ID
            document_id = str(uuid.uuid4())
            content_type = MIME_TYPES.get(extension, "application/octet-stream")

            # -----------------------------------------------
            # Run blob upload and text extraction IN PARALLEL.
            # These are completely independent operations.
            # -----------------------------------------------
            blob_upload_task = storage_service.upload_blob(
                document_id=document_id,
                filename=filename,
                file_bytes=file_bytes,
            )
            text_extract_task = document_service.extract_text(
                file_bytes=file_bytes,
                extension=extension,
            )

            blob_path, extraction = await asyncio.gather(
                blob_upload_task,
                text_extract_task,
            )

            text = extraction["text"]
            pages = extraction["pages"]
            page_count = extraction["page_count"]

            if not text.strip():
                doc = DocumentMetadata(
                    document_id=document_id,
                    filename=filename,
                    content_type=content_type,
                    blob_path=blob_path,
                    status="failed",
                    page_count=page_count,
                    character_count=0,
                    pages=pages,
                    error="The document appears to be empty or "
                          "text could not be extracted.",
                )
                metadata_store.save_document(doc)

                return UploadResult(
                    document_id=document_id,
                    filename=filename,
                    status="failed",
                    error=doc.error,
                )

            # Success — save metadata
            doc = DocumentMetadata(
                document_id=document_id,
                filename=filename,
                content_type=content_type,
                blob_path=blob_path,
                status="processed",
                page_count=page_count,
                character_count=len(text),
                pages=pages,
            )
            metadata_store.save_document(doc)

            # -----------------------------------------------
            # Auto-index into Azure AI Search as BACKGROUND TASK.
            # The upload response returns immediately — indexing
            # continues in the background.
            # -----------------------------------------------
            if background_tasks is not None:
                background_tasks.add_task(
                    _background_index,
                    pages=pages,
                    text=text,
                    document_id=document_id,
                    filename=filename,
                )

            logger.info(
                f"Processed document: {filename} → {document_id} "
                f"({len(text)} chars, {page_count or 'N/A'} pages)"
            )

            return UploadResult(
                document_id=document_id,
                filename=filename,
                status="processed",
            )

        except Exception as error:
            logger.error(f"Failed to process {filename}: {error}")
            return UploadResult(
                filename=filename,
                status="failed",
                error=str(error),
            )

    # Process all files concurrently
    results = await asyncio.gather(*[_process_one(f) for f in files])

    return UploadResponse(documents=list(results))


@router.get("", response_model=list[DocumentSummary])
async def list_documents():
    """
    List all stored documents.

    Returns lightweight summaries (no full text bodies).
    Documents older than 30 days are automatically cleaned up
    and excluded from the response.
    """
    from datetime import datetime, timedelta

    # Auto-cleanup expired documents (30-day retention policy)
    expired_docs = metadata_store.get_expired_documents(days=30)
    for expired in expired_docs:
        try:
            # Delete blob from Azure Storage
            try:
                await storage_service.delete_blob(expired.blob_path)
            except Exception:
                pass  # Continue even if blob delete fails

            # Delete search index chunks
            try:
                from app.search_service import delete_document_chunks
                delete_document_chunks(expired.document_id)
            except Exception:
                pass

            # Delete metadata
            metadata_store.delete_document(expired.document_id)
            logger.info(
                f"Auto-deleted expired document: {expired.filename} "
                f"(uploaded {expired.uploaded_at})"
            )
        except Exception as e:
            logger.error(f"Failed to auto-delete {expired.document_id}: {e}")

    # Return only non-expired documents
    all_docs = metadata_store.get_all_documents()

    return [
        DocumentSummary(
            document_id=doc.document_id,
            filename=doc.filename,
            content_type=doc.content_type,
            status=doc.status,
            page_count=doc.page_count,
            character_count=doc.character_count,
            uploaded_at=doc.uploaded_at,
        )
        for doc in all_docs
    ]


@router.get("/{document_id}", response_model=DocumentMetadata)
async def get_document(document_id: str):
    """
    Get detailed metadata for a specific document.

    Includes extracted page information and text.
    """
    doc = metadata_store.get_document(document_id)

    if doc is None:
        raise HTTPException(
            status_code=404,
            detail=f"Document not found: {document_id}",
        )

    return doc


@router.delete("/all/bulk")
async def delete_all_documents():
    """
    Delete ALL documents — blobs, search index chunks, and metadata.
    Used to free up Azure Search quota quickly.
    """
    all_docs = metadata_store.get_all_documents()
    deleted_count = 0
    errors = []

    for doc in all_docs:
        try:
            # Delete blob
            try:
                await storage_service.delete_blob(doc.blob_path)
            except Exception:
                pass

            # Delete search chunks
            try:
                from app.search_service import delete_document_chunks
                delete_document_chunks(doc.document_id)
            except Exception:
                pass

            # Delete metadata
            metadata_store.delete_document(doc.document_id)
            deleted_count += 1
        except Exception as e:
            errors.append(f"{doc.filename}: {str(e)}")
            logger.error(f"Failed to delete {doc.document_id}: {e}")

    # Purge and recreate the entire search index to free all quota
    # (individual chunk deletes may leave orphaned data)
    try:
        from app.search_service import purge_search_index
        purge_search_index()
        logger.info("Search index purged and recreated successfully")
    except Exception as e:
        logger.error(f"Failed to purge search index: {e}")
        errors.append(f"Index purge: {str(e)}")

    return {
        "message": f"Deleted {deleted_count} of {len(all_docs)} documents. Search index purged.",
        "deleted": deleted_count,
        "total": len(all_docs),
        "errors": errors,
    }


@router.delete("/{document_id}")
async def delete_document(document_id: str):
    """
    Delete a document.

    Removes both the blob from Azure Storage and the metadata.
    """
    doc = metadata_store.get_document(document_id)

    if doc is None:
        raise HTTPException(
            status_code=404,
            detail=f"Document not found: {document_id}",
        )

    # Delete blob from Azure Storage
    try:
        await storage_service.delete_blob(doc.blob_path)
    except Exception as error:
        logger.error(
            f"Failed to delete blob for {document_id}: {error}"
        )
        # Continue with metadata deletion even if blob delete fails

    # Delete associated chunks from Azure AI Search
    try:
        from app.search_service import delete_document_chunks
        deleted_chunks = delete_document_chunks(document_id)
        logger.info(
            f"Deleted {deleted_chunks} Search chunks for {document_id}"
        )
    except Exception as error:
        logger.error(
            f"Failed to delete Search chunks for {document_id}: {error}"
        )
        # Continue with metadata deletion even if Search cleanup fails

    # Delete metadata
    metadata_store.delete_document(document_id)

    return {
        "message": "Document deleted successfully.",
        "document_id": document_id,
        "filename": doc.filename,
    }
