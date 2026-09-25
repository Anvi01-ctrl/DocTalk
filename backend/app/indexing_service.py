import os
import logging
import time

from azure.search.documents import SearchClient

from app.embedding_service import generate_embeddings_batch
from app.search_service import get_search_client

logger = logging.getLogger(__name__)

def index_chunks(chunks: list[dict]) -> dict:
    """
    Generate embeddings for document chunks and upload them
    to Azure AI Search.

    Uses batch embedding for dramatically faster processing.
    """

    if not chunks:
        return {
            "uploaded": 0,
            "message": "No chunks provided.",
        }

    search_client = get_search_client()

    # Extract all content texts for batch embedding
    texts = [chunk["content"] for chunk in chunks]

    logger.info(f"Generating embeddings for {len(texts)} chunks in batch...")

    # Single batch call instead of N individual calls
    t0 = time.perf_counter()
    embeddings = generate_embeddings_batch(texts)
    t1 = time.perf_counter()
    logger.info(f"Embeddings generated in {t1 - t0:.2f}s")

    documents = []
    for chunk, embedding in zip(chunks, embeddings):
        document = {
            "chunk_id": chunk["chunk_id"],
            "document_id": chunk["document_id"],
            "document_name": chunk["document_name"],
            "page_number": chunk["page_number"],
            "content": chunk["content"],
            "content_vector": embedding,
        }
        documents.append(document)

    t2 = time.perf_counter()
    results = search_client.upload_documents(documents=documents)
    t3 = time.perf_counter()
    logger.info(f"Search index upload completed in {t3 - t2:.2f}s")

    successful = sum(
        1 for result in results if result.succeeded
    )

    failed = len(results) - successful

    return {
        "uploaded": successful,
        "failed": failed,
        "total": len(results),
    }