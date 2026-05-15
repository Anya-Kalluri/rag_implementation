"""Chat-summary memory helpers.

Long chats are summarized every few user prompts so the generator can keep
useful conversation context without sending the entire history each time.
"""

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
    """Return a live Redis client when Redis is configured and reachable."""
    if redis is None or not REDIS_URL:
        return None

    try:
        client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        client.ping()
        return client
    except Exception:
        return None


def _cache_key(user, chat_id):
    """Build the Redis cache key for one chat summary."""
    return f"{REDIS_PREFIX}:{user}:{chat_id}"


def _state_key(user, chat_id):
    """Build the SQLite app_state key for one chat summary."""
    return f"chat_summary:{user}:{chat_id}"


def _load_state(user, chat_id):
    """Load persisted summary state from SQLite."""
    return get_state(_state_key(user, chat_id), {}) or {}


def _save_state(user, chat_id, state):
    """Persist summary state and mirror the latest summary into Redis."""
    state["updated_at"] = time.time()
    set_state(_state_key(user, chat_id), state)

    client = _redis_client()
    if client and state.get("summary"):
        client.set(_cache_key(user, chat_id), state["summary"])


def _cached_summary(user, chat_id, fallback=""):
    """Read the Redis summary cache, falling back to SQLite state."""
    client = _redis_client()
    if not client:
        return fallback

    try:
        return client.get(_cache_key(user, chat_id)) or fallback
    except Exception:
        return fallback


def user_prompt_count(history):
    """Count user turns, which drive the summarization threshold."""
    return sum(1 for message in history if message.get("role") == "user")


def prepare_chat_memory(user, chat_id, history):
    """Return the current chat summary and metrics, updating it when needed."""
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
        # Below the threshold, reuse the existing summary and skip an LLM call.
        metrics["chat_summarized_prompts"] = summarized_prompts
        return summary, metrics

    should_summarize_until = (prompt_count // threshold) * threshold
    if should_summarize_until <= summarized_prompts:
        # This chat has already been summarized through the current threshold.
        metrics["chat_summarized_prompts"] = summarized_prompts
        return summary, metrics

    messages_to_summarize = []
    seen_user_prompts = 0
    for message in history:
        # Include complete turns up to the threshold boundary so the summary is
        # stable and does not repeatedly summarize the same partial window.
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
