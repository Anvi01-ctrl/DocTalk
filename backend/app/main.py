from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from azure.identity import InteractiveBrowserCredential
from azure.ai.projects import AIProjectClient

from pypdf import PdfReader
from docx import Document

import io


app = FastAPI(title="DocTalk API")


# Allow the frontend to call this backend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Azure AI Foundry project connection
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


# Currently uploaded document
current_document = {
    "filename": None,
    "text": ""
}


@app.get("/")
def root():
    return {
        "app": "DocTalk",
        "status": "running",
        "document": current_document["filename"]
    }


@app.get("/document")
def get_document():
    return {
        "filename": current_document["filename"],
        "uploaded": current_document["filename"] is not None
    }


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
        if extension == "txt":
            text = file_bytes.decode("utf-8", errors="ignore")

        elif extension == "pdf":
            pdf_file = io.BytesIO(file_bytes)
            reader = PdfReader(pdf_file)

            pages = []

            for page in reader.pages:
                page_text = page.extract_text() or ""
                pages.append(page_text)

            text = "\n\n".join(pages)

        else:
            docx_file = io.BytesIO(file_bytes)
            document = Document(docx_file)

            paragraphs = []

            for paragraph in document.paragraphs:
                paragraphs.append(paragraph.text)

            text = "\n".join(paragraphs)

        if not text.strip():
            raise HTTPException(
                status_code=400,
                detail="The document appears to be empty or text could not be extracted."
            )

        current_document["filename"] = filename
        current_document["text"] = text

        return {
            "message": "Document uploaded successfully.",
            "filename": filename,
            "characters": len(text)
        }

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Could not read the document: {str(error)}"
        )


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