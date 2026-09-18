from app.retrieval_service import search_documents
from app.embedding_service import generate_embedding

import os

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import OpenAI


FOUNDRY_ACCOUNT = "doctalk-korea-ai"

CHAT_MODEL = "gpt-5-mini"

token_provider = get_bearer_token_provider(
    DefaultAzureCredential(),
    "https://cognitiveservices.azure.com/.default",
)

openai_client = OpenAI(
    base_url=f"https://{FOUNDRY_ACCOUNT}.services.ai.azure.com/openai/v1",
    api_key="placeholder",
    default_headers={
        "Authorization": f"Bearer {token_provider()}"
    },
)


def generate_rag_answer(
    question: str,
    top_k: int = 5,
) -> dict:
    """
    Retrieve relevant document chunks and generate an
    answer using GPT-5-mini.
    """

    if not question.strip():
        raise ValueError("Question cannot be empty.")

    # Retrieve relevant chunks from Azure AI Search.
    retrieved_chunks = search_documents(
        question,
        top_k=top_k,
    )

    # If nothing relevant was retrieved, don't ask the model
    # to invent an answer.
    if not retrieved_chunks:
        return {
            "answer": (
                "I could not find that information "
                "in the uploaded documents."
            ),
            "sources": [],
        }

    # Build the context that will be given to the model.
    context_parts = []

    for chunk in retrieved_chunks:
        context_parts.append(
            f"""
Document: {chunk['document_name']}
Page: {chunk['page_number']}

Content:
{chunk['content']}
"""
        )

    context = "\n---\n".join(context_parts)

    prompt = f"""
You are DocTalk, an AI document intelligence assistant.

Answer the user's question using ONLY the retrieved
document context below.

If the answer is not supported by the context, say:

"I could not find that information in the uploaded documents."

Do not invent facts or information.

Retrieved document context:
============================
{context}
============================

User question:
{question}
"""

    response = openai_client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
    )

    answer = response.choices[0].message.content

    sources = [
        {
            "document_name": chunk["document_name"],
            "page_number": chunk["page_number"],
            "chunk_id": chunk["chunk_id"],
        }
        for chunk in retrieved_chunks
    ]

    return {
        "answer": answer,
        "sources": sources,
    }