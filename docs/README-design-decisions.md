# Design Decisions

## FastAPI Backend and Streamlit Frontend

The project uses FastAPI for API boundaries and Streamlit for a fast operational UI. This keeps backend behavior testable through endpoints while allowing the interface to evolve quickly without a separate frontend build system.

## SQLite for Local Persistence

SQLite stores users, chats, files, chunks, chat history, events, guest usage, and app state. This is a practical fit for a local or small-team RAG workspace because it avoids external database setup while still providing structured persistence.

## Role-Based Access

The role hierarchy is:

```text
admin > manager > analyst > viewer > guest
```

The app separates roles by responsibility:

- Admins can manage managers, analysts, viewers, and guests.
- Managers can manage analysts, viewers, and guests.
- Managers and analysts can ingest content.
- Viewers and guests can use available files and URLs.
- Guests have a daily query limit.

Backend endpoints enforce these rules even when the frontend hides unavailable controls.

## Reusable Files and URLs

Uploaded files and ingested URLs are recorded as file metadata. Viewer and guest users can select available sources and process them into their own chat. This preserves chat isolation while allowing a manager or analyst to publish reusable source material.

URL reuse is handled as first-class ingestion: when a selected source path starts with `http://` or `https://`, the backend fetches and indexes the URL content instead of treating it like a local upload path.

## Per-Chat Indexing

Chunks and FAISS indexes are scoped by `user_id` and `chat_id`. This keeps retrieval focused on the active chat and avoids accidental cross-chat context leakage.

## Hybrid Retrieval

Retrieval combines:

- FAISS semantic search over embeddings
- BM25 lexical search over stored chunks
- A small overlap-based reranking step

BM25 remains active even when FAISS is present. This improves exact-term matching and gives the app a fallback path if embeddings or FAISS indexing fail.

## Graceful Degradation

If embedding generation fails during ingestion, the app still stores text chunks. Retrieval can then fall back to BM25. This makes ingestion more resilient and avoids losing extracted content because one downstream service failed.

## Groq for Generation

Answer generation and chat summarization use Groq chat completions. The current model is `llama-3.1-8b-instant`, chosen for quick responses in an interactive workspace.

## Jinja Prompt Templates

Prompts live in `backend/rag/templates`. Keeping prompts as templates separates prompt wording from Python control flow and makes future prompt changes easier to review.

## Chat Memory

The app stores chat history and prepares summaries after a configurable threshold. Redis can be used for summary caching, but the app can still run without Redis because core chat history is persisted locally.

## Guest Query Limit

Guest query usage is tracked in SQLite by username and date. The backend returns usage metadata to the UI so guests can see how many of their daily queries have been used and when no more are available.

## Audit and Metrics

The backend logs uploads, selected sources, queries, retrieval quality proxies, latency, token usage, and errors. Managers and admins can use these views to monitor system behavior without inspecting logs directly.

## OCR Strategy

Image ingestion first tries local Tesseract OCR. If Tesseract is unavailable, the loader attempts RapidOCR and then a Groq vision fallback when configured. This layered approach supports local-first OCR while still allowing cloud fallback.

