from groq import Groq
from backend.config.settings import GROQ_API_KEY
from backend.rag.prompt_loader import render_prompt

client = None


def get_client():
    global client

    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is missing. Check your .env file.")

    if client is None:
        client = Groq(api_key=GROQ_API_KEY)

    return client


def generate(query, chunks):
    metrics = {
        "model": "llama-3.1-8b-instant",
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "error": None,
    }

    # -------------------------------
    # SAFETY: NO CONTEXT
    # -------------------------------
    if not chunks or len(chunks) == 0:
        return "No relevant information found in the uploaded file.", metrics

    # -------------------------------
    # LIMIT CONTEXT SIZE (SAFE)
    # -------------------------------
    context_chunks = chunks[:5]  # prevent overload
    context = "\n\n".join([c["text"] for c in context_chunks])

    prompt = render_prompt("document_answer.jinja", context=context, query=query)

    try:
        res = get_client().chat.completions.create(
            model=metrics["model"],
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )

        usage = getattr(res, "usage", None)
        if usage:
            metrics["prompt_tokens"] = int(getattr(usage, "prompt_tokens", 0) or 0)
            metrics["completion_tokens"] = int(getattr(usage, "completion_tokens", 0) or 0)
            metrics["total_tokens"] = int(getattr(usage, "total_tokens", 0) or 0)

        answer = res.choices[0].message.content

        if not answer:
            return "No response generated.", metrics

        return answer.strip(), metrics

    except Exception as e:
        print("GENERATOR ERROR:", str(e))
        metrics["error"] = str(e)
        return "Error generating response. Please try again.", metrics
