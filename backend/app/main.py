from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from azure.identity import InteractiveBrowserCredential
from azure.ai.projects import AIProjectClient

from pypdf import PdfReader
from docx import Document
from pydantic import BaseModel

from app.chunking_service import chunk_text
from app.indexing_service import index_chunks
from app.retrieval_service import search_documents
from app.rag_service import generate_rag_answer

import io


app = FastAPI(title="DocTalk API")


# ---------------------------------------------------------
# CORS
# ---------------------------------------------------------

# Allow the frontend to call this backend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------
# Azure AI Foundry project connection
# ---------------------------------------------------------

endpoint = "https://doctalk-korea.services.ai.azure.com/api/projects/DocTalk"

# This opens a browser login instead of depending on Azure CLI PATH.
credential = InteractiveBrowserCredential()

project_client = AIProjectClient(
    endpoint=endpoint,
    credential=credential,
)

openai_client = project_client.get_openai_client()

AGENT_NAME = "DocTalk-Agent"
AGENT_VERSION = "1"


# ---------------------------------------------------------
# Currently uploaded document
# ---------------------------------------------------------

current_document = {
    "filename": None,
    "text": "",
    "pages": []
}


# ---------------------------------------------------------
# Request models
# ---------------------------------------------------------

class SearchRequest(BaseModel):
    query: str
    top_k: int = 5


class RagChatRequest(BaseModel):
    question: str
    top_k: int = 5


# ---------------------------------------------------------
# Root endpoint
# ---------------------------------------------------------

@app.get("/")
def root():
    return {
        "app": "DocTalk",
        "status": "running",
        "document": current_document["filename"]
    }


# ---------------------------------------------------------
# Search endpoint
# ---------------------------------------------------------

@app.post("/search")
def search(request: SearchRequest):
    try:
        results = search_documents(
            request.query,
            top_k=request.top_k,
        )

        return {
            "query": request.query,
            "results": results,
        }

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(error)}",
        )


# ---------------------------------------------------------
# RAG chat endpoint
# ---------------------------------------------------------

@app.post("/rag/chat")
def rag_chat(request: RagChatRequest):
    try:
        result = generate_rag_answer(
            request.question,
            top_k=request.top_k,
        )

        return result

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"RAG chat failed: {str(error)}",
        )


# ---------------------------------------------------------
# Get current document details
# ---------------------------------------------------------

@app.get("/document")
def get_document():
    return {
        "filename": current_document["filename"],
        "uploaded": current_document["filename"] is not None,
        "pages": len(current_document["pages"]),
    }


# ---------------------------------------------------------
# Index uploaded document
# ---------------------------------------------------------

@app.post("/documents/{document_id}/index")
def index_document(document_id: str):
    filename = current_document["filename"]
    pages = current_document["pages"]

    if not filename or not pages:
        raise HTTPException(
            status_code=400,
            detail="No document is currently uploaded.",
        )

    all_chunks = []

    # Create chunks separately for each page.
    # This preserves the actual PDF page number.
    for page_number, page_text in enumerate(pages, start=1):

        page_chunks = chunk_text(
            text=page_text,
            document_id=document_id,
            document_name=filename,
            page_number=page_number,
        )

        all_chunks.extend(page_chunks)

    if not all_chunks:
        raise HTTPException(
            status_code=400,
            detail="Could not create document chunks.",
        )

    try:
        result = index_chunks(all_chunks)

        return {
            "document_id": document_id,
            "document_name": filename,
            "chunks": len(all_chunks),
            "pages": len(pages),
            "indexing": result,
        }

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Document indexing failed: {str(error)}",
        )


# ---------------------------------------------------------
# Upload document
# ---------------------------------------------------------

@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):

    filename = file.filename or ""
    extension = filename.lower().split(".")[-1]

    allowed_extensions = ["pdf", "docx", "txt"]

    if extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail="Only PDF, DOCX, and TXT files are supported."
        )

    file_bytes = await file.read()

    try:

        # -------------------------------------------------
        # TXT
        # -------------------------------------------------

        if extension == "txt":

            text = file_bytes.decode(
                "utf-8",
                errors="ignore"
            )

            # TXT is treated as one page.
            document_pages = [text]


        # -------------------------------------------------
        # PDF
        # -------------------------------------------------

        elif extension == "pdf":

            pdf_file = io.BytesIO(file_bytes)

            reader = PdfReader(pdf_file)

            document_pages = []

            # Keep every PDF page separately.
            for page in reader.pages:

                page_text = page.extract_text() or ""

                document_pages.append(page_text)

            # Keep combined text for compatibility
            # with the existing backend.
            text = "\n\n".join(document_pages)


        # -------------------------------------------------
        # DOCX
        # -------------------------------------------------

        else:

            docx_file = io.BytesIO(file_bytes)

            document = Document(docx_file)

            paragraphs = []

            for paragraph in document.paragraphs:

                paragraphs.append(paragraph.text)

            text = "\n".join(paragraphs)

            # DOCX is currently treated as one page.
            document_pages = [text]


        # -------------------------------------------------
        # Empty document validation
        # -------------------------------------------------

        if not text.strip():

            raise HTTPException(
                status_code=400,
                detail=(
                    "The document appears to be empty or "
                    "text could not be extracted."
                )
            )


        # -------------------------------------------------
        # Store uploaded document
        # -------------------------------------------------

        current_document["filename"] = filename

        current_document["text"] = text

        current_document["pages"] = document_pages


        # -------------------------------------------------
        # Upload response
        # -------------------------------------------------

        return {
            "message": "Document uploaded successfully.",
            "filename": filename,
            "characters": len(text),
            "pages": len(document_pages),
        }


    except HTTPException:

        raise


    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=f"Could not read the document: {str(error)}"
        )


# ---------------------------------------------------------
# Legacy chat endpoint
# ---------------------------------------------------------

@app.post("/chat")
def chat(message: str):

    document_name = current_document["filename"]

    document_text = current_document["text"]


    if not message.strip():

        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty."
        )


    if document_name and document_text:

        prompt = f"""
You are DocTalk, an AI document intelligence assistant.

The user has uploaded this document.

Filename:
{document_name}

Document content:
----------------
{document_text}
----------------

Answer the user's question using the document content above.

If the answer is not present in the document, clearly say:
"I could not find that information in the uploaded document."

User question:
{message}
"""

    else:

        prompt = message


    try:

        response = openai_client.responses.create(
            input=prompt,
            extra_body={
                "agent_reference": {
                    "name": AGENT_NAME,
                    "version": AGENT_VERSION,
                    "type": "agent_reference"
                }
            },
        )


        return {
            "response": response.output_text,
            "document": document_name
        }


    except Exception as error:

        print("\n========== CHAT ERROR ==========")

        print(repr(error))

        print("================================\n")


        raise HTTPException(
            status_code=500,
            detail=f"Chat request failed: {str(error)}"
        )