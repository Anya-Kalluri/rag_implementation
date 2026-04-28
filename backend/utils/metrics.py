import json
import os
import time


FILE = "metrics.json"
GROQ_LLAMA_3_1_8B_INPUT_PER_1M = 0.05
GROQ_LLAMA_3_1_8B_OUTPUT_PER_1M = 0.08


DEFAULT_METRICS = {
    "uploads": 0,
    "queries": 0,
    "errors": 0,
    "total_latency_ms": 0.0,
    "avg_latency_ms": 0.0,
    "last_latency_ms": 0.0,
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "estimated_cost_usd": 0.0,
    "model_calls": {},
    "retrieval": {
        "evaluated_queries": 0,
        "avg_precision_at_k": 0.0,
        "avg_recall_proxy": 0.0,
        "avg_response_relevance": 0.0,
        "last_precision_at_k": 0.0,
        "last_recall_proxy": 0.0,
        "last_response_relevance": 0.0,
    },
    "last_query": None,
    "last_upload": None,
    "updated_at": None,
}


def _merge_defaults(data, defaults):
    merged = defaults.copy()

    for key, value in data.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_defaults(value, merged[key])
        else:
            merged[key] = value

    return merged


def load():
    if not os.path.exists(FILE):
        return DEFAULT_METRICS.copy()

    try:
        with open(FILE, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return DEFAULT_METRICS.copy()

    return _merge_defaults(data, DEFAULT_METRICS)


def save(data):
    data["updated_at"] = time.time()
    with open(FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def estimate_cost(prompt_tokens=0, completion_tokens=0):
    input_cost = (prompt_tokens / 1_000_000) * GROQ_LLAMA_3_1_8B_INPUT_PER_1M
    output_cost = (completion_tokens / 1_000_000) * GROQ_LLAMA_3_1_8B_OUTPUT_PER_1M
    return input_cost + output_cost


def log_upload(file=None, user=None, chat_id=None, chunks=0, latency_ms=0.0):
    data = load()
    data["uploads"] += 1
    data["last_upload"] = {
        "file": file,
        "user": user,
        "chat_id": chat_id,
        "chunks": chunks,
        "latency_ms": round(float(latency_ms), 2),
        "time": time.time(),
    }
    save(data)


def log_query(stats=None):
    stats = stats or {}
    data = load()
    data["queries"] += 1

    latency_ms = float(stats.get("latency_ms", 0.0) or 0.0)
    data["last_latency_ms"] = round(latency_ms, 2)
    data["total_latency_ms"] = float(data.get("total_latency_ms", 0.0)) + latency_ms
    data["avg_latency_ms"] = round(data["total_latency_ms"] / max(data["queries"], 1), 2)

    prompt_tokens = int(stats.get("prompt_tokens", 0) or 0)
    completion_tokens = int(stats.get("completion_tokens", 0) or 0)
    total_tokens = int(stats.get("total_tokens", prompt_tokens + completion_tokens) or 0)

    data["prompt_tokens"] += prompt_tokens
    data["completion_tokens"] += completion_tokens
    data["total_tokens"] += total_tokens
    data["estimated_cost_usd"] = round(
        float(data.get("estimated_cost_usd", 0.0))
        + estimate_cost(prompt_tokens, completion_tokens),
        8,
    )

    model = stats.get("model") or "unknown"
    model_calls = data.setdefault("model_calls", {})
    model_calls[model] = model_calls.get(model, 0) + 1

    retrieval = data["retrieval"]
    retrieval["evaluated_queries"] += 1
    evaluated = retrieval["evaluated_queries"]

    precision = float(stats.get("retrieval_precision_at_k", 0.0) or 0.0)
    recall = float(stats.get("retrieval_recall_proxy", 0.0) or 0.0)
    relevance = float(stats.get("response_relevance", 0.0) or 0.0)

    retrieval["last_precision_at_k"] = round(precision, 4)
    retrieval["last_recall_proxy"] = round(recall, 4)
    retrieval["last_response_relevance"] = round(relevance, 4)
    retrieval["avg_precision_at_k"] = round(
        ((retrieval["avg_precision_at_k"] * (evaluated - 1)) + precision) / evaluated,
        4,
    )
    retrieval["avg_recall_proxy"] = round(
        ((retrieval["avg_recall_proxy"] * (evaluated - 1)) + recall) / evaluated,
        4,
    )
    retrieval["avg_response_relevance"] = round(
        ((retrieval["avg_response_relevance"] * (evaluated - 1)) + relevance) / evaluated,
        4,
    )

    data["last_query"] = {
        "user": stats.get("user"),
        "chat_id": stats.get("chat_id"),
        "query": stats.get("query"),
        "retrieved_chunks": stats.get("retrieved_chunks", 0),
        "latency_ms": round(latency_ms, 2),
        "total_tokens": total_tokens,
        "model": model,
        "time": time.time(),
    }

    save(data)


def log_error(error_type, detail=None):
    data = load()
    data["errors"] += 1
    data["last_error"] = {
        "type": error_type,
        "detail": detail,
        "time": time.time(),
    }
    save(data)
