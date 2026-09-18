import os

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery

from app.embedding_service import generate_embedding


SEARCH_ENDPOINT = os.getenv(
    "AZURE_SEARCH_ENDPOINT",
    "https://doctalk-search.search.windows.net",
)

SEARCH_API_KEY = os.getenv("AZURE_SEARCH_API_KEY")

INDEX_NAME = os.getenv(
    "AZURE_SEARCH_INDEX_NAME",
    "doctalk-documents",
)


def get_search_client() -> SearchClient:
    """Create an Azure AI Search client."""

    if not SEARCH_API_KEY:
        raise RuntimeError(
            "AZURE_SEARCH_API_KEY environment variable is not set."
        )

    return SearchClient(
        endpoint=SEARCH_ENDPOINT,
        index_name=INDEX_NAME,
        credential=AzureKeyCredential(SEARCH_API_KEY),
    )


def search_documents(
    query: str,
    top_k: int = 5,
) -> list[dict]:
    """
    Run hybrid search using keyword + vector search.
    """

    if not query.strip():
        raise ValueError("Search query cannot be empty.")

    search_client = get_search_client()

    # Generate an embedding for the user's question.
    query_vector = generate_embedding(query)

    # Search the content_vector field.
    vector_query = VectorizedQuery(
        vector=query_vector,
        k_nearest_neighbors=top_k,
        fields="content_vector",
        exhaustive=True,
    )

    # Hybrid search: keyword + vector search.
    results = search_client.search(
        search_text=query,
        vector_queries=[vector_query],
        select=[
            "chunk_id",
            "document_id",
            "document_name",
            "page_number",
            "content",
        ],
        top=top_k,
    )

    retrieved_chunks = []

    for result in results:
        retrieved_chunks.append(
            {
                "chunk_id": result["chunk_id"],
                "document_id": result["document_id"],
                "document_name": result["document_name"],
                "page_number": result["page_number"],
                "content": result["content"],
                "score": result["@search.score"],
            }
        )

    return retrieved_chunks