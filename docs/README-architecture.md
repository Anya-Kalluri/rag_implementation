# Architecture Diagram

The application is split into a Streamlit UI, a FastAPI backend, local persistence, document ingestion, retrieval, and LLM generation.

```mermaid
flowchart TD
    User[User Browser] --> UI[Streamlit Frontend<br/>frontend/streamlit.py]
    UI -->|JWT login| AuthAPI[Auth Routes<br/>backend/auth/routes.py]
    UI -->|Chat, upload, URL, query| RagAPI[RAG Routes<br/>backend/rag/routes.py]

    AuthAPI --> Users[(SQLite users<br/>data/rag_app.sqlite3)]
    RagAPI --> DB[(SQLite app data<br/>chats, files, chunks, events, guest_usage)]
    RagAPI --> Uploads[(uploads/)]

    RagAPI --> Ingestion[Ingestion Pipeline<br/>backend/ingestion/pipeline.py]
    Ingestion --> Loaders[Loaders<br/>PDF, DOCX, HTML, images, URL content]
    Ingestion --> Chunking[Smart Chunking]
    Ingestion --> Embeddings[Sentence Transformer Embeddings]
    Ingestion --> Chunks[(SQLite chunks)]
    Ingestion --> VectorIndex[(FAISS indexes)]

    RagAPI --> Retrieval[Retrieval<br/>backend/rag/retrieval.py]
    Retrieval --> VectorIndex
    Retrieval --> Chunks
    Retrieval --> BM25[BM25 lexical fallback]

    RagAPI --> Memory[Chat Memory<br/>backend/utils/chat_memory.py]
    Memory --> Redis[(Optional Redis)]
    Memory --> History[(SQLite chat history)]

    RagAPI --> Generator[Generator<br/>backend/rag/generator.py]
    Generator --> Groq[Groq Chat Completion API]
    Generator --> Templates[Jinja Prompts<br/>backend/rag/templates]

    RagAPI --> Metrics[Metrics and Audit Logs<br/>backend/utils/metrics.py<br/>backend/utils/logger.py]
    Metrics --> DB
```

## Request Flow

### Authentication

1. The frontend posts credentials to `/login`.
2. The backend validates the password using Passlib.
3. A JWT is returned with `sub` and `role`.
4. Subsequent frontend requests send the JWT as a bearer token.

### File or URL Ingestion

1. A manager, analyst, or admin uploads a file or submits a URL.
2. The backend extracts text with the matching loader.
3. Text is split into chunks.
4. Chunks are embedded.
5. Chunk metadata is stored in SQLite.
6. Embeddings are appended to the chat's FAISS index.
7. File or URL metadata is recorded so other allowed users can select it later.

### Query Answering

1. The frontend posts a query and `chat_id` to `/query`.
2. Guest quota and rate limits are checked.
3. The backend loads chat memory and indexed chunks.
4. Retrieval combines FAISS semantic search with BM25 lexical scoring.
5. Top chunks are inserted into a Jinja prompt.
6. Groq generates the answer.
7. The answer, sources, telemetry, and guest usage metadata are returned to the frontend.

## Main Modules

- `backend/main.py`: FastAPI app setup and router registration.
- `backend/auth/`: login, JWTs, password hashing, role hierarchy, and user management.
- `backend/rag/routes.py`: upload, URL ingestion, query, audit, chat, and file APIs.
- `backend/ingestion/`: file loaders, chunking, embeddings, and FAISS indexing.
- `backend/rag/retrieval.py`: semantic and lexical retrieval.
- `backend/rag/generator.py`: prompt rendering and Groq generation.
- `backend/utils/`: persistence helpers, metrics, audit logs, guest limits, chat memory.
- `frontend/streamlit.py`: complete UI for login, chats, ingestion, dashboards, and querying.

