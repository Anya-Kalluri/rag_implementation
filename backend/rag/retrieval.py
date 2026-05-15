"""Hybrid retrieval over chat-scoped RAG chunks.

Retrieval combines FAISS semantic search with BM25 keyword search, then applies
a lightweight overlap reranker before returning source chunks to the generator.
"""

import re
from typing import Any

import numpy as np
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict, Field

from backend.db import connect, decode, init_db
from backend.vector_index import read_index


TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def tokenize(text):
    """Tokenize text into lowercase alphanumeric terms for lexical matching."""
    return TOKEN_RE.findall(str(text or "").lower())


def load_chunks(user, chat):
    """Load chunk metadata for one user/chat from SQLite."""
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
    """Load the FAISS index and chunk metadata for one user/chat."""
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
    """Normalize a score array to the 0..1 range for score blending."""
    scores = np.asarray(scores, dtype="float32")

    if scores.size == 0:
        return scores

    min_score = float(np.min(scores))
    max_score = float(np.max(scores))

    if max_score <= min_score:
        return np.zeros_like(scores, dtype="float32")

    return (scores - min_score) / (max_score - min_score)


def build_query_embedding(query, expected_dim=None):
    """Embed the query and validate its shape/dimension for FAISS search."""
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


def _documents_from_meta(meta):
    """Convert saved chunk dictionaries into LangChain Document objects."""
    documents = []
    for pos, item in enumerate(meta):
        if not isinstance(item, dict):
            continue

        text = str(item.get("text", "")).strip()
        if not text:
            continue

        documents.append(
            Document(
                page_content=text,
                metadata={
                    "id": item.get("id"),
                    "roles": item.get("roles", []),
                    "meta_index": pos,
                },
            )
        )

    return documents


class FaissSemanticRetriever(BaseRetriever):
    """LangChain retriever that searches a FAISS index with query embeddings."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    index: Any = None
    documents: list[Document] = Field(default_factory=list)
    k: int = 20

    def _get_relevant_documents(self, query, *, run_manager=None):
        if self.index is None or getattr(self.index, "ntotal", 0) <= 0:
            return []

        expected_dim = getattr(self.index, "d", None)
        q_emb = build_query_embedding(query, expected_dim)
        if q_emb is None:
            return []

        try:
            search_k = min(max(self.k, 1), self.index.ntotal)
            distances, indices = self.index.search(q_emb, search_k)
        except Exception as e:
            print("FAISS SEARCH ERROR:", e)
            return []

        by_meta_index = {
            int(doc.metadata.get("meta_index")): doc
            for doc in self.documents
            if doc.metadata.get("meta_index") is not None
        }

        hits = []
        raw_scores = []
        for rank, idx in enumerate(indices[0]):
            idx = int(idx)
            doc = by_meta_index.get(idx)
            if doc is None:
                continue

            distance = float(distances[0][rank])
            if not np.isfinite(distance):
                continue

            score = 1.0 / (1.0 + max(distance, 0.0))
            raw_scores.append(score)
            hits.append((doc, score))

        normalized = normalize_scores(raw_scores)
        results = []
        for (doc, raw_score), semantic_score in zip(hits, normalized):
            copied = Document(page_content=doc.page_content, metadata=dict(doc.metadata))
            copied.metadata["semantic_score"] = float(semantic_score)
            copied.metadata["semantic_raw_score"] = float(raw_score)
            results.append(copied)

        return results


class LangChainBM25RankRetriever(BaseRetriever):
    """LangChain retriever that performs BM25 keyword ranking over chunks."""

    documents: list[Document] = Field(default_factory=list)
    k: int = 20

    def _get_relevant_documents(self, query, *, run_manager=None):
        query_tokens = set(tokenize(query))
        if not self.documents or not query_tokens:
            return []

        try:
            retriever = BM25Retriever.from_documents(
                self.documents,
                k=min(max(self.k, 1), len(self.documents)),
                preprocess_func=tokenize,
            )
            ranked_docs = retriever.invoke(query)
        except Exception as e:
            print("BM25 ERROR:", e)
            return []

        results = []
        total = max(len(ranked_docs), 1)
        for rank, doc in enumerate(ranked_docs):
            copied = Document(page_content=doc.page_content, metadata=dict(doc.metadata))
            doc_tokens = set(tokenize(doc.page_content))
            overlap_score = len(query_tokens & doc_tokens) / max(len(query_tokens), 1)
            rank_score = (total - rank) / total
            copied.metadata["lexical_score"] = float(max(overlap_score, 0.5 * rank_score))
            results.append(copied)

        return sorted(results, key=lambda doc: doc.metadata.get("lexical_score", 0.0), reverse=True)


class HybridRetriever(BaseRetriever):
    """Blend semantic and lexical candidates into one ranked list."""

    semantic_retriever: BaseRetriever | None = None
    keyword_retriever: BaseRetriever
    semantic_weight: float = 0.75
    keyword_weight: float = 0.25
    k: int = 5

    def _get_relevant_documents(self, query, *, run_manager=None):
        semantic_docs = []
        if self.semantic_retriever is not None:
            semantic_docs = self.semantic_retriever.invoke(query)

        keyword_docs = self.keyword_retriever.invoke(query)
        candidates = {}

        def add_doc(doc, score_key):
            doc_key = doc.metadata.get("id") or " ".join(doc.page_content.split()).lower()
            current = candidates.get(doc_key)
            if current is None:
                current = Document(page_content=doc.page_content, metadata=dict(doc.metadata))
                candidates[doc_key] = current

            score = float(doc.metadata.get(score_key, 0.0) or 0.0)
            current.metadata[score_key] = max(float(current.metadata.get(score_key, 0.0) or 0.0), score)

        for doc in semantic_docs:
            add_doc(doc, "semantic_score")

        for doc in keyword_docs:
            add_doc(doc, "lexical_score")

        if not candidates:
            return []

        results = []
        for doc in candidates.values():
            semantic_score = float(doc.metadata.get("semantic_score", 0.0) or 0.0)
            lexical_score = float(doc.metadata.get("lexical_score", 0.0) or 0.0)
            if semantic_docs:
                score = self.semantic_weight * semantic_score + self.keyword_weight * lexical_score
            else:
                score = lexical_score

            doc.metadata["score"] = float(score)
            results.append(doc)

        return sorted(results, key=lambda doc: doc.metadata.get("score", 0.0), reverse=True)


class OverlapReranker(BaseRetriever):
    """Add a small exact-term overlap boost after hybrid retrieval."""

    base_retriever: BaseRetriever
    k: int = 5

    def _get_relevant_documents(self, query, *, run_manager=None):
        docs = self.base_retriever.invoke(query)
        query_words = set(tokenize(query))

        for doc in docs:
            text_words = set(tokenize(doc.page_content))
            overlap = len(query_words & text_words)
            doc.metadata["rerank_score"] = float(doc.metadata.get("score", 0.0) or 0.0) + 0.05 * overlap

        return sorted(
            docs,
            key=lambda doc: doc.metadata.get("rerank_score", doc.metadata.get("score", 0.0)),
            reverse=True,
        )[: self.k]


def _doc_to_result(doc):
    """Convert a LangChain Document into the route-friendly chunk shape."""
    return {
        "id": doc.metadata.get("id"),
        "text": doc.page_content,
        "roles": doc.metadata.get("roles", []),
        "score": float(doc.metadata.get("score", 0.0) or 0.0),
        "semantic_score": float(doc.metadata.get("semantic_score", 0.0) or 0.0),
        "lexical_score": float(doc.metadata.get("lexical_score", 0.0) or 0.0),
        "rerank_score": float(doc.metadata.get("rerank_score", doc.metadata.get("score", 0.0)) or 0.0),
    }


def rerank(query, docs):
    """Legacy dictionary-based overlap reranker kept for compatibility."""
    query_words = set(tokenize(query))

    for doc in docs:
        text_words = set(tokenize(doc.get("text", "")))
        overlap = len(query_words & text_words)
        doc["rerank_score"] = float(doc.get("score", 0)) + 0.05 * overlap

    return sorted(docs, key=lambda x: x.get("rerank_score", x.get("score", 0)), reverse=True)


def unique_docs(docs, limit):
    """Keep the first unique chunk texts up to limit."""
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
    """Return the top retrieved chunks for one query/user/chat."""
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

    documents = _documents_from_meta(meta)

    if not documents:
        print("NO VALID TEXT CHUNKS")
        return []

    search_k = max(k * 4, k)
    semantic_retriever = None
    if index is not None and getattr(index, "ntotal", 0) > 0:
        semantic_retriever = FaissSemanticRetriever(index=index, documents=documents, k=search_k)
    else:
        print("NO FAISS INDEX; USING BM25 ONLY")

    keyword_retriever = LangChainBM25RankRetriever(documents=documents, k=search_k)
    hybrid_retriever = HybridRetriever(
        semantic_retriever=semantic_retriever,
        keyword_retriever=keyword_retriever,
        k=search_k,
    )
    reranking_retriever = OverlapReranker(base_retriever=hybrid_retriever, k=k)
    results = [_doc_to_result(doc) for doc in reranking_retriever.invoke(query)]

    if not results:
        print("NO SCORED CANDIDATES; RETURNING FIRST CHUNKS")
        results = [_doc_to_result(doc) for doc in documents[:k]]

    print("META LENGTH:", len(meta))
    print("VALID TEXT CHUNKS:", len(documents))
    print("FINAL RETURN:", len(results))
    print("==================================\n")

    return results
