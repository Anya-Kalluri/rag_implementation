# Setup Instructions

This project is a document-grounded RAG workspace with a FastAPI backend and a Streamlit frontend. It supports document upload, URL ingestion, reusable files/URLs across chats, role-based access, guest query limits, audit views, and telemetry.

## Prerequisites

- Python 3.10 or newer
- A Groq API key for answer generation
- Optional: Redis for chat-summary caching
- Optional: Tesseract OCR for local image text extraction

## Install

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Configure Environment

Create a `.env` file in the project root:

```env
GROQ_API_KEY=your_groq_api_key
SECRET_KEY=replace_this_for_jwt_signing
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin

REDIS_URL=redis://localhost:6379/0
CHAT_SUMMARY_THRESHOLD=5
GUEST_QUERY_LIMIT=5

# Optional OCR settings
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
IMAGE_OCR_MODEL=llama-3.2-11b-vision-preview
```

If `ADMIN_USERNAME` and `ADMIN_PASSWORD` are not set, the app bootstraps an `admin` / `admin` account when no users exist.

## Run Backend

```powershell
uvicorn backend.main:app --reload
```

The API runs at:

```text
http://127.0.0.1:8000
```

## Run Frontend

In a second terminal:

```powershell
streamlit run frontend/streamlit.py
```

If the backend is running somewhere else:

```powershell
$env:RAG_API_URL="http://127.0.0.1:8000"
streamlit run frontend/streamlit.py
```

## First Login

1. Open the Streamlit URL shown in the terminal.
2. Log in with the admin credentials.
3. Use the Admin panel to create managers, analysts, viewers, and guests.
4. Managers can create and delete analyst, viewer, and guest users from the Manager Dashboard.

## Data Storage

Runtime data is stored locally:

- SQLite database: `data/rag_app.sqlite3`
- Uploaded files: `uploads/`
- FAISS indexes: stored through `backend/vector_index.py`

## Common Workflows

Upload a document:

1. Log in as `admin`, `manager`, or `analyst`.
2. Create or open a chat.
3. Use the Ingestion panel to upload a supported file.
4. Ask questions in the chat input.

Ingest a URL:

1. Log in as `admin`, `manager`, or `analyst`.
2. Enter a web URL in the Ingestion panel.
3. The backend fetches, extracts, chunks, embeds, and indexes the URL content.
4. Other allowed users can select the URL from Available Files and use it in their own chat.

Guest usage:

- Guests can select available files or URLs.
- Guests are limited by `GUEST_QUERY_LIMIT`, which defaults to 5 queries per day.
- The UI shows how many guest queries have been used and when no more are available.

## Supported Ingestion Types

The backend supports PDF, DOCX, PPTX, CSV, JSON, TXT, Markdown, HTML, XLSX/XLS, XML, and common image formats. URL ingestion can process HTML pages and direct document links such as PDFs.

