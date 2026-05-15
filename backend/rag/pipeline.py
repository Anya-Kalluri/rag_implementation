"""High-level RAG orchestration: retrieve context, then generate an answer."""

from .retrieval import retrieve
from .generator import generate


def rag(query, role, user, chat, chat_summary=""):
    """Run retrieval and generation with defensive fallbacks for route handlers."""

    # Retrieval should return a list, but keep this boundary resilient so one bad
    # retriever result does not break the API response shape.
    chunks = retrieve(query, role, user, chat)

    if chunks is None:
        chunks = []

    if not isinstance(chunks, list):
        chunks = []

    # Generation errors are converted into a user-safe answer and metrics error
    # so callers can still log telemetry consistently.
    try:
        answer, generation_metrics = generate(query, chunks, chat_summary=chat_summary)
    except Exception as e:
        answer = "Error generating response. Please try again."
        generation_metrics = {"error": str(e)}

    if answer is None:
        answer = "No response generated."

    return answer, chunks, generation_metrics
