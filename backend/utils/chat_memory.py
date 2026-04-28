import time

from backend.config.settings import CHAT_SUMMARY_THRESHOLD, REDIS_URL
from backend.db import get_state, set_state
from backend.rag.generator import summarize_chat_messages


try:
    import redis  # type: ignore[import-not-found]
except Exception:
    redis = None


REDIS_PREFIX = "rag:chat_summary"


def _redis_client():
    if redis is None or not REDIS_URL:
        return None

    try:
        client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        client.ping()
        return client
    except Exception:
        return None


def _cache_key(user, chat_id):
    return f"{REDIS_PREFIX}:{user}:{chat_id}"


def _state_key(user, chat_id):
    return f"chat_summary:{user}:{chat_id}"


def _load_state(user, chat_id):
    return get_state(_state_key(user, chat_id), {}) or {}


def _save_state(user, chat_id, state):
    state["updated_at"] = time.time()
    set_state(_state_key(user, chat_id), state)

    client = _redis_client()
    if client and state.get("summary"):
        client.set(_cache_key(user, chat_id), state["summary"])


def _cached_summary(user, chat_id, fallback=""):
    client = _redis_client()
    if not client:
        return fallback

    try:
        return client.get(_cache_key(user, chat_id)) or fallback
    except Exception:
        return fallback


def user_prompt_count(history):
    return sum(1 for message in history if message.get("role") == "user")


def prepare_chat_memory(user, chat_id, history):
    threshold = max(int(CHAT_SUMMARY_THRESHOLD or 0), 1)
    state = _load_state(user, chat_id)
    summarized_prompts = int(state.get("summarized_prompts", 0) or 0)
    summary = _cached_summary(user, chat_id, state.get("summary", ""))
    prompt_count = user_prompt_count(history)

    metrics = {
        "summary_prompt_tokens": 0,
        "summary_completion_tokens": 0,
        "summary_total_tokens": 0,
        "summary_error": None,
        "chat_summary_used": bool(summary),
        "chat_summary_updated": False,
        "chat_summarized_prompts": summarized_prompts,
    }

    if prompt_count < threshold:
        metrics["chat_summarized_prompts"] = summarized_prompts
        return summary, metrics

    should_summarize_until = (prompt_count // threshold) * threshold
    if should_summarize_until <= summarized_prompts:
        metrics["chat_summarized_prompts"] = summarized_prompts
        return summary, metrics

    messages_to_summarize = []
    seen_user_prompts = 0
    for message in history:
        if message.get("role") == "user":
            if seen_user_prompts >= should_summarize_until:
                break
            seen_user_prompts += 1
        messages_to_summarize.append(message)

    summary, summary_metrics = summarize_chat_messages(
        messages_to_summarize,
        existing_summary=summary,
    )

    summarized_prompts = should_summarize_until
    _save_state(user, chat_id, {
        "summary": summary,
        "summarized_prompts": summarized_prompts,
    })

    metrics.update({
        "summary_prompt_tokens": summary_metrics.get("prompt_tokens", 0),
        "summary_completion_tokens": summary_metrics.get("completion_tokens", 0),
        "summary_total_tokens": summary_metrics.get("total_tokens", 0),
        "summary_error": summary_metrics.get("error"),
        "chat_summary_used": bool(summary),
        "chat_summary_updated": True,
        "chat_summarized_prompts": summarized_prompts,
    })

    return summary, metrics
