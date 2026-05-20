"""RAGAS evaluation helpers for generated RAG responses."""

from __future__ import annotations

import os
import math
import re
from typing import Any

from langchain_core.embeddings import Embeddings

from backend.rag.generator import get_llm
from backend.rag.pipeline import rag
from backend.rag.retrieval import retrieve


DEFAULT_METRICS = ("faithfulness", "context_precision", "answer_relevancy")
REFERENCE_METRICS = ("context_recall", "factual_correctness")
RAGAS_TIMEOUT_SECONDS = int(os.getenv("RAGAS_TIMEOUT_SECONDS", "90"))
RAGAS_MAX_CONTEXTS = int(os.getenv("RAGAS_MAX_CONTEXTS", "3"))
TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


class LocalRagasEmbeddings(Embeddings):
    """LangChain embedding adapter around the app's local embedding model."""

    def embed_documents(self, texts):
        from backend.ingestion.embeddings import get_embeddings

        return [list(vector) for vector in get_embeddings(texts)]

    def embed_query(self, text):
        from backend.ingestion.embeddings import get_embeddings

        vectors = get_embeddings([text])
        return list(vectors[0])


def chunk_texts(chunks):
    """Return clean retrieved context strings from internal chunk dictionaries."""
    contexts = []
    for chunk in chunks or []:
        text = str(chunk.get("text", "")).strip() if isinstance(chunk, dict) else ""
        if text:
            contexts.append(text)
    return contexts


def _require_ragas():
    """Import RAGAS only when evaluation is requested."""
    try:
        from ragas import EvaluationDataset, evaluate
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import (
            Faithfulness,
            FactualCorrectness,
            LLMContextPrecisionWithReference,
            LLMContextPrecisionWithoutReference,
            LLMContextRecall,
            ResponseRelevancy,
        )
        from ragas.run_config import RunConfig
    except ImportError as e:
        raise RuntimeError(
            "RAGAS is not installed. Install dependencies with: "
            "pip install -r requirements.txt"
        ) from e

    return {
        "EvaluationDataset": EvaluationDataset,
        "evaluate": evaluate,
        "LangchainEmbeddingsWrapper": LangchainEmbeddingsWrapper,
        "LangchainLLMWrapper": LangchainLLMWrapper,
        "Faithfulness": Faithfulness,
        "FactualCorrectness": FactualCorrectness,
        "LLMContextPrecisionWithReference": LLMContextPrecisionWithReference,
        "LLMContextPrecisionWithoutReference": LLMContextPrecisionWithoutReference,
        "LLMContextRecall": LLMContextRecall,
        "ResponseRelevancy": ResponseRelevancy,
        "RunConfig": RunConfig,
    }


def _build_metrics(ragas_api, metric_names, has_reference):
    """Create RAGAS metric instances from small API-facing metric names."""
    metrics = []
    selected = tuple(metric_names or DEFAULT_METRICS)

    for name in selected:
        normalized = str(name).strip().lower()
        if normalized == "faithfulness":
            metrics.append(ragas_api["Faithfulness"]())
        elif normalized == "answer_relevancy":
            metrics.append(ragas_api["ResponseRelevancy"]())
        elif normalized == "context_precision":
            metric_cls = (
                ragas_api["LLMContextPrecisionWithReference"]
                if has_reference
                else ragas_api["LLMContextPrecisionWithoutReference"]
            )
            metrics.append(metric_cls())
        elif normalized == "context_recall":
            if has_reference:
                metrics.append(ragas_api["LLMContextRecall"]())
        elif normalized == "factual_correctness":
            if has_reference:
                metrics.append(ragas_api["FactualCorrectness"]())

    return metrics


def _result_to_dict(result):
    """Normalize RAGAS result objects across supported RAGAS versions."""
    if hasattr(result, "to_pandas"):
        frame = result.to_pandas()
        if not frame.empty:
            row = frame.iloc[0].to_dict()
            return {
                key: _json_safe_score(value)
                for key, value in row.items()
                if isinstance(value, (int, float)) and not isinstance(value, bool)
            }

    if hasattr(result, "to_dict"):
        raw = result.to_dict()
    else:
        raw = dict(result)

    scores = {}
    for key, value in raw.items():
        if isinstance(value, list) and value:
            value = value[0]
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            scores[key] = _json_safe_score(value)
    return scores


def _json_safe_score(value):
    """Return JSON-safe score values because RAGAS can emit NaN on failures."""
    value = float(value)
    if not math.isfinite(value):
        return None
    return value


def _tokens(text):
    return set(TOKEN_RE.findall(str(text or "").lower()))


def _ratio(part, whole):
    return round(len(part) / max(len(whole), 1), 4)


def _local_fallback_scores(query, answer, contexts, reference=""):
    """Cheap retrieval-oriented fallback when a RAGAS judge returns no score."""
    query_tokens = _tokens(query)
    answer_tokens = _tokens(answer)
    context_tokens = [_tokens(context) for context in contexts]
    combined_context = set().union(*context_tokens) if context_tokens else set()
    reference_tokens = _tokens(reference)

    relevant_contexts = 0
    comparator = reference_tokens or answer_tokens or query_tokens
    for tokens in context_tokens:
        if tokens & comparator or tokens & query_tokens:
            relevant_contexts += 1

    return {
        "faithfulness": _ratio(answer_tokens & combined_context, answer_tokens),
        "answer_relevancy": _ratio(answer_tokens & query_tokens, query_tokens),
        "context_recall": _ratio((reference_tokens or query_tokens) & combined_context, reference_tokens or query_tokens),
        "factual_correctness": (
            _ratio(answer_tokens & reference_tokens, reference_tokens)
            if reference_tokens
            else None
        ),
        "llm_context_precision_without_reference": round(relevant_contexts / max(len(context_tokens), 1), 4),
        "llm_context_precision_with_reference": round(relevant_contexts / max(len(context_tokens), 1), 4),
    }


def _fill_missing_scores(scores, fallback_scores):
    filled = {}
    score_sources = {}
    for name, value in scores.items():
        if value is None:
            filled[name] = fallback_scores.get(name)
            score_sources[name] = "local_fallback"
        else:
            filled[name] = value
            score_sources[name] = "ragas"
    return filled, score_sources


def evaluate_response(
    *,
    query: str,
    answer: str,
    chunks: list[dict[str, Any]],
    reference: str = "",
    metrics: list[str] | None = None,
):
    """Score one already-generated RAG answer with RAGAS."""
    ragas_api = _require_ragas()
    contexts = chunk_texts(chunks)[:RAGAS_MAX_CONTEXTS]
    if not contexts:
        raise RuntimeError("No retrieved contexts available for RAGAS evaluation.")

    has_reference = bool(str(reference or "").strip())
    sample = {
        "user_input": query,
        "response": answer,
        "retrieved_contexts": contexts,
    }
    if has_reference:
        sample["reference"] = reference

    evaluation_dataset = ragas_api["EvaluationDataset"].from_list([sample])
    evaluator_llm = ragas_api["LangchainLLMWrapper"](get_llm(temperature=0))
    evaluator_embeddings = ragas_api["LangchainEmbeddingsWrapper"](LocalRagasEmbeddings())
    selected_metrics = _build_metrics(ragas_api, metrics, has_reference)
    if not selected_metrics:
        raise RuntimeError("No valid RAGAS metrics were selected.")

    result = ragas_api["evaluate"](
        dataset=evaluation_dataset,
        metrics=selected_metrics,
        llm=evaluator_llm,
        embeddings=evaluator_embeddings,
        run_config=ragas_api["RunConfig"](
            timeout=RAGAS_TIMEOUT_SECONDS,
            max_retries=1,
            max_wait=5,
            max_workers=4,
        ),
        show_progress=False,
        raise_exceptions=False,
    )

    raw_scores = _result_to_dict(result)
    fallback_scores = _local_fallback_scores(query, answer, contexts, reference=reference)
    scores, score_sources = _fill_missing_scores(raw_scores, fallback_scores)

    return {
        "scores": scores,
        "score_sources": score_sources,
        "fallback_scores": fallback_scores,
        "metrics": [metric.name for metric in selected_metrics],
        "reference_used": has_reference,
        "retrieved_contexts": len(contexts),
    }


def run_ragas_eval(
    *,
    query: str,
    role: str,
    user: str,
    chat_id: str,
    answer: str = "",
    reference: str = "",
    metrics: list[str] | None = None,
):
    """Run the app's RAG pipeline and score the generated response with RAGAS."""
    generation_metrics = {}
    if answer:
        chunks = retrieve(query, role, user, chat_id)
    else:
        answer, chunks, generation_metrics = rag(query, role, user, chat_id)

    chunks = chunks if isinstance(chunks, list) else []
    evaluation = evaluate_response(
        query=query,
        answer=answer,
        chunks=chunks,
        reference=reference,
        metrics=metrics,
    )
    return {
        "answer": answer,
        "sources": [text[:300] for text in chunk_texts(chunks)],
        "generation_metrics": generation_metrics,
        "ragas": evaluation,
    }
