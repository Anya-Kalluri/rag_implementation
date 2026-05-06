from backend.config.settings import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_PROVIDER,
    RAG_LLM_MODEL,
    RAG_LLM_MODEL_EXPLICIT,
)
from backend.rag.prompt_loader import render_prompt

llm_clients = {}
OPENAI_COMPATIBLE_PROVIDERS = {
    "openai",
    "openai-compatible",
    "openrouter",
    "together",
    "fireworks",
    "deepseek",
    "xai",
}


def _missing_package_error(provider, package):
    return RuntimeError(
        f"LLM_PROVIDER='{provider}' requires the '{package}' package. "
        "Install dependencies with: pip install -r requirements.txt"
    )


def _chat_model_class(provider):
    if provider == "groq":
        try:
            from langchain_groq import ChatGroq
        except ImportError as e:
            raise _missing_package_error(provider, "langchain-groq") from e

        return ChatGroq

    if provider in OPENAI_COMPATIBLE_PROVIDERS:
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as e:
            raise _missing_package_error(provider, "langchain-openai") from e

        return ChatOpenAI

    if provider == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as e:
            raise _missing_package_error(provider, "langchain-anthropic") from e

        return ChatAnthropic

    if provider in {"google", "gemini"}:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as e:
            raise _missing_package_error(provider, "langchain-google-genai") from e

        return ChatGoogleGenerativeAI

    supported = "groq, openai, anthropic, google, openai-compatible"
    raise RuntimeError(f"Unsupported LLM_PROVIDER='{provider}'. Use one of: {supported}.")


def _chat_model_kwargs(provider, model, temperature):
    kwargs = {
        "api_key": LLM_API_KEY,
        "model": model,
        "temperature": temperature,
    }

    if provider in OPENAI_COMPATIBLE_PROVIDERS and provider != "openai":
        if not LLM_BASE_URL:
            raise RuntimeError(
                f"LLM_PROVIDER='{provider}' requires LLM_BASE_URL. "
                "Set the provider's OpenAI-compatible API base URL in .env."
            )
        if not RAG_LLM_MODEL_EXPLICIT:
            raise RuntimeError(
                f"LLM_PROVIDER='{provider}' requires RAG_LLM_MODEL. "
                "Set the exact model name expected by that provider."
            )
        kwargs["base_url"] = LLM_BASE_URL
    elif provider == "openai" and LLM_BASE_URL:
        kwargs["base_url"] = LLM_BASE_URL

    return kwargs


def get_llm(temperature=0.2, model=RAG_LLM_MODEL):
    provider = LLM_PROVIDER
    if not LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY is missing. Check your .env file.")

    cache_key = (provider, model, temperature, LLM_BASE_URL)
    if cache_key not in llm_clients:
        chat_model = _chat_model_class(provider)
        llm_clients[cache_key] = chat_model(**_chat_model_kwargs(provider, model, temperature))

    return llm_clients[cache_key]


def _empty_metrics(model=RAG_LLM_MODEL):
    return {
        "model": model,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "error": None,
    }


def _record_usage(metrics, message):
    usage = getattr(message, "usage_metadata", None) or {}
    if usage:
        metrics["prompt_tokens"] = int(usage.get("input_tokens", 0) or 0)
        metrics["completion_tokens"] = int(usage.get("output_tokens", 0) or 0)
        metrics["total_tokens"] = int(usage.get("total_tokens", 0) or 0)
        return

    response_metadata = getattr(message, "response_metadata", None) or {}
    token_usage = response_metadata.get("token_usage") or {}
    if token_usage:
        metrics["prompt_tokens"] = int(token_usage.get("prompt_tokens", 0) or 0)
        metrics["completion_tokens"] = int(token_usage.get("completion_tokens", 0) or 0)
        metrics["total_tokens"] = int(token_usage.get("total_tokens", 0) or 0)


def _message_content(message):
    content = getattr(message, "content", "")
    if isinstance(content, list):
        return "".join(str(part.get("text", part)) if isinstance(part, dict) else str(part) for part in content)
    return content or ""


def summarize_chat_messages(messages, existing_summary=""):
    metrics = _empty_metrics()

    if not messages:
        return existing_summary or "", metrics

    lines = []
    if existing_summary:
        lines.append("Existing summary:")
        lines.append(existing_summary)
        lines.append("")

    lines.append("Messages to summarize:")
    for message in messages:
        role = message.get("role", "unknown")
        content = str(message.get("content", "")).strip()
        if content:
            lines.append(f"{role}: {content}")

    prompt = render_prompt(
        "chat_summary.jinja",
        transcript="\n".join(lines),
    )

    try:
        message = get_llm(temperature=0.1, model=metrics["model"]).invoke(prompt)
        _record_usage(metrics, message)

        summary = _message_content(message)
        return (summary or existing_summary or "").strip(), metrics
    except Exception as e:
        print("SUMMARY ERROR:", str(e))
        metrics["error"] = str(e)
        return existing_summary or "", metrics


def generate(query, chunks, chat_summary=""):
    metrics = _empty_metrics()

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

    prompt = render_prompt(
        "document_answer.jinja",
        context=context,
        query=query,
        chat_summary=chat_summary or "",
    )

    try:
        message = get_llm(temperature=0.2, model=metrics["model"]).invoke(prompt)
        _record_usage(metrics, message)

        answer = _message_content(message)

        if not answer:
            return "No response generated.", metrics

        return answer.strip(), metrics

    except Exception as e:
        print("GENERATOR ERROR:", str(e))
        metrics["error"] = str(e)
        return "Error generating response. Please try again.", metrics
