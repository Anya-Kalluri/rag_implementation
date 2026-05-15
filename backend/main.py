"""FastAPI application entry point.

This module keeps startup intentionally small: create the app object and mount
the feature routers. Route modules own the actual endpoint behavior.
"""

from fastapi import FastAPI
from backend.auth.routes import router as auth_router
from backend.rag.routes import router as rag_router


# Shared ASGI application used by uvicorn/FastAPI.
app = FastAPI()

# Authentication and RAG routes are mounted without prefixes, so endpoints such
# as /login, /upload, and /query are exposed directly.
app.include_router(auth_router)
app.include_router(rag_router)
