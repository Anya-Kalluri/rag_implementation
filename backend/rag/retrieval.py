import re

import numpy as np
from rank_bm25 import BM25Okapi

from backend.db import connect, decode, init_db
from backend.vector_index import read_index


TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def tokenize(text):
    return TOKEN_RE.findall(str(text or "").lower())


def load_chunks(user, chat):
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, text, roles_json
            FROM chunks
            WHERE user_id = ? AND chat_id = ?
            ORDER BY position ASC
            """,
            (str(user).strip(), str(chat).strip()),
        ).fetchall()

    return [
        {
            "id": row["id"],
            "text": row["text"],
            "roles": decode(row["roles_json"], []),
        }
        for row in rows
    ]


def load_store(user, chat):
    try:
        index = read_index(user, chat)
    except Exception as e:
        print("FAISS LOAD ERROR:", e)
        index = None

    if index is None:
        print("FAISS INDEX NOT FOUND; BM25 FALLBACK ENABLED")

    meta = load_chunks(user, chat)

    if not isinstance(meta, list):
        print("META ERROR: expected list, got", type(meta).__name__)
        return index, []

    return index, meta


def normalize_scores(scores):
    scores = np.asarray(scores, dtype="float32")

    if scores.size == 0:
        return scores

    min_score = float(np.min(scores))
    max_score = float(np.max(scores))

    if max_score <= min_score:
        return np.zeros_like(scores, dtype="float32")

    return (scores - min_score) / (max_score - min_score)


def build_bm25_scores(query, texts):
    try:
        tokenized_texts = [tokenize(text) for text in texts]
        tokenized_query = tokenize(query)

        if not tokenized_query or not any(tokenized_texts):
            return np.zeros(len(texts), dtype="float32")

        bm25 = BM25Okapi(tokenized_texts)
        return normalize_scores(bm25.get_scores(tokenized_query))
    except Exception as e:
        print("BM25 ERROR:", e)
        return np.zeros(len(texts), dtype="float32")


def build_query_embedding(query, expected_dim=None):
    try:
        from backend.ingestion.embeddings import get_embeddings

        q_emb = np.asarray(get_embeddings([query]), dtype="float32")
    except Exception as e:
        print("EMBEDDING ERROR:", e)
        return None

    if q_emb.ndim == 1:
        q_emb = q_emb.reshape(1, -1)

    if q_emb.ndim != 2 or q_emb.shape[0] != 1:
        print("EMBEDDING ERROR: bad shape", q_emb.shape)
        return None

    if expected_dim is not None and q_emb.shape[1] != expected_dim:
        print("EMBEDDING DIMENSION MISMATCH:", q_emb.shape[1], "!=", expected_dim)
        return None

    return q_emb


def rerank(query, docs):
    query_words = set(tokenize(query))

    for doc in docs:
        text_words = set(tokenize(doc.get("text", "")))
        overlap = len(query_words & text_words)
        doc["rerank_score"] = float(doc.get("score", 0)) + 0.05 * overlap

    return sorted(docs, key=lambda x: x.get("rerank_score", x.get("score", 0)), reverse=True)


def unique_docs(docs, limit):
    seen = set()
    unique = []

    for doc in docs:
        key = " ".join(str(doc.get("text", "")).split()).lower()
        if key in seen:
            continue

        seen.add(key)
        unique.append(doc)

        if len(unique) >= limit:
            break

    return unique


def retrieve(query, role, user, chat, k=5):
    print("\n========== RETRIEVE DEBUG ==========")
    print("USER:", user)
    print("ROLE:", role)
    print("CHAT:", chat)

    if not query or not str(query).strip():
        print("EMPTY QUERY")
        return []

    index, meta = load_store(user, chat)

    if not meta:
        print("NO META")
        return []

    valid_meta = []
    for pos, item in enumerate(meta):
        if not isinstance(item, dict):
            continue

        text = str(item.get("text", "")).strip()
        if not text:
            continue

        item_copy = item.copy()
        item_copy["_meta_index"] = pos
        valid_meta.append(item_copy)

    if not valid_meta:
        print("NO VALID TEXT CHUNKS")
        return []

    texts = [m["text"] for m in valid_meta]
    bm25_scores = build_bm25_scores(query, texts)

    candidate_scores = {}

    if index is not None and index.ntotal > 0:
        expected_dim = getattr(index, "d", None)
        q_emb = build_query_embedding(query, expected_dim)

        if q_emb is not None:
            try:
                search_k = min(max(k * 4, k), index.ntotal)
                distances, indices = index.search(q_emb, search_k)

                semantic_hits = []
                for rank, idx in enumerate(indices[0]):
                    idx = int(idx)
                    if idx < 0 or idx >= len(meta):
                        continue

                    distance = float(distances[0][rank])
                    if not np.isfinite(distance):
                        continue

                    semantic_hits.append((idx, 1.0 / (1.0 + max(distance, 0.0))))

                semantic_values = normalize_scores([score for _, score in semantic_hits])

                meta_to_valid = {m["_meta_index"]: i for i, m in enumerate(valid_meta)}
                for (meta_idx, _), semantic_score in zip(semantic_hits, semantic_values):
                    valid_idx = meta_to_valid.get(meta_idx)
                    if valid_idx is None:
                        continue

                    candidate_scores[valid_idx] = max(
                        candidate_scores.get(valid_idx, 0.0),
                        0.75 * float(semantic_score) + 0.25 * float(bm25_scores[valid_idx]),
                    )
            except Exception as e:
                print("FAISS SEARCH ERROR:", e)
    else:
        print("NO FAISS INDEX; USING BM25 ONLY")

    # Always add lexical candidates so retrieval still works if FAISS fails,
    # returns no usable ids, or misses exact document wording.
    lexical_order = np.argsort(-bm25_scores)[: max(k * 4, k)]
    for valid_idx in lexical_order:
        lexical_score = float(bm25_scores[valid_idx])
        if lexical_score <= 0 and candidate_scores:
            continue

        candidate_scores[int(valid_idx)] = max(
            candidate_scores.get(int(valid_idx), 0.0),
            lexical_score,
        )

    if not candidate_scores:
        print("NO SCORED CANDIDATES; RETURNING FIRST CHUNKS")
        candidate_scores = {i: 0.0 for i in range(min(k, len(valid_meta)))}

    results = []
    for valid_idx, score in candidate_scores.items():
        doc = valid_meta[valid_idx].copy()
        doc.pop("_meta_index", None)
        doc["score"] = float(score)
        results.append(doc)

    results = unique_docs(rerank(query, results), k)

    print("META LENGTH:", len(meta))
    print("VALID TEXT CHUNKS:", len(valid_meta))
    print("FINAL RETURN:", len(results))
    print("==================================\n")

    return results
