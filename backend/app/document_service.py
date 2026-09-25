"""
DocTalk — Document processing service.

Handles text extraction from PDF, DOCX, and TXT files using:
- Azure AI Document Intelligence for PDFs (OCR + layout-aware extraction)
- python-docx for DOCX files
- UTF-8 decode for TXT files

Falls back to pypdf if Document Intelligence is unavailable.
"""

import os
import io
import logging
import asyncio
from typing import Optional
from functools import lru_cache

from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest

from pypdf import PdfReader
from docx import Document as DocxDocument
from dotenv import load_dotenv

from app.document_models import PageInfo


load_dotenv()

logger = logging.getLogger(__name__)


# Configuration
DOC_INTELLIGENCE_ENDPOINT = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")
DOC_INTELLIGENCE_KEY = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY")

# Cache the Document Intelligence client as a singleton
_doc_intelligence_client = None
_doc_intelligence_checked = False

def _get_doc_intelligence_client() -> Optional[DocumentIntelligenceClient]:
    """
    Create a Document Intelligence client (cached singleton).
    Returns None if the endpoint is not configured.
    """
    global _doc_intelligence_client, _doc_intelligence_checked

    if _doc_intelligence_checked:
        return _doc_intelligence_client

    _doc_intelligence_checked = True

    if not DOC_INTELLIGENCE_ENDPOINT or not DOC_INTELLIGENCE_KEY:
        logger.warning(
            "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT or KEY not set. "
            "PDF extraction will fall back to pypdf."
        )
        return None

    try:
        credential = AzureKeyCredential(DOC_INTELLIGENCE_KEY)
        _doc_intelligence_client = DocumentIntelligenceClient(
            endpoint=DOC_INTELLIGENCE_ENDPOINT,
            credential=credential,
        )
        return _doc_intelligence_client

    except Exception as error:
        logger.warning(
            f"Could not create Document Intelligence client: {error}. "
            "Falling back to pypdf."
        )
        return None


async def process_pdf_with_intelligence(file_bytes: bytes) -> tuple[list[PageInfo], int]:
    """
    Extract text from a PDF using Azure AI Document Intelligence.

    Uses the prebuilt-layout model for:
    - Text extraction from normal PDFs
    - OCR for scanned documents
    - Page-aware extraction
    - Table extraction
    - Heading/section detection
    - Layout-aware processing

    Returns (pages, page_count).
    """
    client = _get_doc_intelligence_client()

    if client is None:
        return await process_pdf_with_pypdf(file_bytes)

    try:
        # Run the synchronous Document Intelligence call in a thread
        # to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            _run_doc_intelligence_sync,
            client,
            file_bytes,
        )

        # Build a set of table spans so we can mark table content
        table_texts_by_page = {}
        if result.tables:
            for table in result.tables:
                # Build a simple text representation of the table
                rows = {}
                for cell in table.cells:
                    row_idx = cell.row_index
                    if row_idx not in rows:
                        rows[row_idx] = {}
                    rows[row_idx][cell.column_index] = cell.content

                table_text = ""
                for row_idx in sorted(rows.keys()):
                    row_cells = rows[row_idx]
                    row_text = " | ".join(
                        row_cells.get(col, "") for col in sorted(row_cells.keys())
                    )
                    table_text += row_text + "\n"

                # Associate table with its bounding page
                if table.bounding_regions:
                    for region in table.bounding_regions:
                        pg = region.page_number
                        if pg not in table_texts_by_page:
                            table_texts_by_page[pg] = []
                        table_texts_by_page[pg].append(table_text.strip())

        pages = []

        if result.pages:
            for page in result.pages:
                page_number = page.page_number
                page_text = ""

                # Collect text from lines on this page
                if page.lines:
                    page_text = "\n".join(
                        line.content for line in page.lines
                    )

                # Append table content for this page
                if page_number in table_texts_by_page:
                    for tbl in table_texts_by_page[page_number]:
                        page_text += "\n\n[Table]\n" + tbl

                pages.append(PageInfo(
                    page_number=page_number,
                    text=page_text,
                ))

        page_count = len(pages)

        logger.info(
            f"Document Intelligence (layout) extracted {page_count} pages"
        )

        return pages, page_count

    except Exception as error:
        logger.warning(
            f"Document Intelligence failed: {error}. "
            "Falling back to pypdf."
        )
        return await process_pdf_with_pypdf(file_bytes)


def _run_doc_intelligence_sync(client, file_bytes: bytes):
    """Synchronous Document Intelligence call — run in executor."""
    poller = client.begin_analyze_document(
        model_id="prebuilt-read",
        body=AnalyzeDocumentRequest(
            bytes_source=file_bytes,
        ),
    )
    return poller.result()


def _extract_pdf_pypdf_sync(file_bytes: bytes) -> tuple[list[PageInfo], int]:
    """Synchronous pypdf extraction — run in executor."""
    pdf_file = io.BytesIO(file_bytes)
    reader = PdfReader(pdf_file)

    pages = []

    for i, page in enumerate(reader.pages):
        page_text = page.extract_text() or ""

        pages.append(PageInfo(
            page_number=i + 1,
            text=page_text,
        ))

    page_count = len(pages)

    logger.info(f"pypdf extracted {page_count} pages")

    return pages, page_count


async def process_pdf_with_pypdf(file_bytes: bytes) -> tuple[list[PageInfo], int]:
    """
    Fallback PDF extraction using pypdf.

    Preserves page information but does not support OCR.
    Runs synchronous pypdf in a thread to avoid blocking.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        _extract_pdf_pypdf_sync,
        file_bytes,
    )


def _extract_docx_sync(file_bytes: bytes) -> tuple[list[str], str]:
    """
    Synchronous DOCX extraction — run in executor.
    Returns (paragraph_list, full_text) in one parse.
    """
    docx_file = io.BytesIO(file_bytes)
    document = DocxDocument(docx_file)

    paragraphs = []
    for paragraph in document.paragraphs:
        if paragraph.text.strip():
            paragraphs.append(paragraph.text)

    full_text = "\n".join(paragraphs)
    return paragraphs, full_text


async def process_docx(file_bytes: bytes) -> tuple[Optional[list[PageInfo]], Optional[int], str]:
    """
    Extract text from a DOCX file using python-docx.

    DOCX files do not have true page numbers, so pages is None
    and page_count is None.

    Returns (pages, page_count, full_text) — text is extracted in one pass.
    """
    loop = asyncio.get_event_loop()
    paragraphs, full_text = await loop.run_in_executor(
        None,
        _extract_docx_sync,
        file_bytes,
    )

    # No true pages in DOCX — return None for pages/page_count
    return None, None, full_text


async def process_txt(file_bytes: bytes) -> tuple[Optional[list[PageInfo]], Optional[int]]:
    """
    Extract text from a TXT file.

    TXT files do not have pages, so pages is None
    and page_count is None.
    """
    # No true pages in TXT — return None for pages/page_count
    return None, None


async def extract_text(
    file_bytes: bytes,
    extension: str,
) -> dict:
    """
    Main entry point for document text extraction.

    Returns a dict with:
    - text: the full extracted text
    - pages: list of PageInfo or None
    - page_count: int or None
    """
    if extension == "pdf":
        pages, page_count = await process_pdf_with_intelligence(file_bytes)

        full_text = "\n\n".join(
            page.text for page in pages if page.text
        )

        return {
            "text": full_text,
            "pages": pages,
            "page_count": page_count,
        }

    elif extension == "docx":
        # Single parse — no more double-parsing
        pages, page_count, full_text = await process_docx(file_bytes)

        return {
            "text": full_text,
            "pages": pages,
            "page_count": page_count,
        }

    elif extension == "txt":
        pages, page_count = await process_txt(file_bytes)

        full_text = file_bytes.decode("utf-8", errors="ignore")

        return {
            "text": full_text,
            "pages": pages,
            "page_count": page_count,
        }

    else:
        raise ValueError(f"Unsupported extension: {extension}")
