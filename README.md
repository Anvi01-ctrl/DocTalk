# DocTalk

DocTalk is an AI-powered document intelligence assistant. Users can upload PDF, DOCX, or TXT documents and ask questions about the uploaded document through a chatbot interface.

## Features

- Upload PDF documents
- Upload DOCX documents
- Upload TXT documents
- Extract text from uploaded documents
- Ask questions about the uploaded document
- Receive AI-generated responses
- Web-based frontend
- FastAPI backend
- Azure AI Foundry agent integration

## Technology Stack

### Frontend

- HTML
- CSS
- JavaScript

### Backend

- Python
- FastAPI
- Uvicorn

### Document Processing

- pypdf
- python-docx

### AI and Cloud

- Azure AI Foundry
- GPT-5-mini model
- Azure AI Projects SDK
- Azure Identity

## Project Structure

```text
DocTalk/
├── backend/
│   ├── app/
│   │   └── main.py
│   ├── requirements.txt
│   └── .gitignore
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── script.js
├── .gitignore
└── README.md
```

## Requirements

Install the following before running the project:

- Python 3.10 or newer
- Git
- Azure CLI, or access to the Azure login browser flow
- An Azure account with access to the DocTalk Azure AI Foundry project

## Installation

Clone the repository:

```powershell
git clone YOUR_GITHUB_REPOSITORY_URL
```

Move into the project folder:

```powershell
cd DocTalk
```

Create a virtual environment:

```powershell
python -m venv .venv
```

Activate the virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install backend dependencies:

```powershell
cd backend
pip install -r requirements.txt
```

## Azure Login

The backend uses Azure authentication.

If Azure CLI is installed, run:

```powershell
az login
```

Sign in using the Azure account that has access to the DocTalk Azure AI Foundry project.

Alternatively, the application may open a browser login window automatically when the chat request is made.

## Run the Backend

Open PowerShell and run:

```powershell
cd C:\Users\YOUR_USERNAME\DocTalk\backend
python -m uvicorn app.main:app --reload
```

The backend will run at:

```text
http://127.0.0.1:8000
```

FastAPI documentation is available at:

```text
http://127.0.0.1:8000/docs
```

## Run the Frontend

Open a second PowerShell terminal.

Run:

```powershell
cd C:\Users\YOUR_USERNAME\DocTalk\frontend
python -m http.server 5500
```

Open the frontend in your browser:

```text
http://127.0.0.1:5500
```

## Usage

1. Start the backend.
2. Start the frontend.
3. Open `http://127.0.0.1:5500`.
4. Upload a PDF, DOCX, or TXT document.
5. Ask a question about the document.
6. Read the AI-generated response.

## Backend API Endpoints (Core AI)

### Check server status

```http
GET /
```

### Check uploaded document

```http
GET /document
```

### Upload a document (Legacy - single file)

```http
POST /upload
```

### Ask a question

```http
POST /chat?message=YOUR_QUESTION
```

## Backend API Endpoints (Document Ingestion & Storage)

### Upload Documents (Multi-file)
Uploads files to Azure Blob Storage and extracts text using Azure AI Document Intelligence.

```http
POST /documents/upload
```

### List all documents
Returns metadata for all documents stored persistently.

```http
GET /documents
```

### Get Document Details
Returns full extracted text and page info for a specific document.

```http
GET /documents/{document_id}
```

### Delete Document
Deletes a document from Azure Blob Storage and the metadata store.

```http
DELETE /documents/{document_id}
```

## Current Limitations

- Large documents may exceed the model context limit.
- The current version does not yet use a vector database or retrieval-augmented generation.
- Each team member needs access to the Azure AI Foundry project.

## Future Improvements

- Vector database integration (Azure AI Search)
- Retrieval-augmented generation
- Better chunking for large documents
- User authentication
- Chat history
- Image generation support
- Deployment to Azure