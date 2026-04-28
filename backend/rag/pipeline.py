from .retrieval import retrieve
from .generator import generate


def rag(query, role, user, chat):
    
    # 🔥 Safe retrieval (never allow None)
    chunks = retrieve(query, role, user, chat)
    
    if chunks is None:
        chunks = []

    # 🔥 Ensure chunks is always iterable
    if not isinstance(chunks, list):
        chunks = []

    # 🔥 Generate answer safely
    try:
        answer, generation_metrics = generate(query, chunks)
    except Exception as e:
        answer = "Error generating response. Please try again."
        generation_metrics = {"error": str(e)}

    # 🔥 Final safety (never return None)
    if answer is None:
        answer = "No response generated."

    return answer, chunks, generation_metrics
