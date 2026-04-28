import os
import re
import shutil
import time

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from backend.auth.routes import get_current_user
from backend.ingestion.pipeline import process_file
from backend.rag.pipeline import rag
from backend.utils.chat_history import load_history, save_history
from backend.utils.chat_registry import create_chat, delete_chat, get_chats, rename_chat
from backend.utils.file_metadata import add_file, get_files
from backend.utils.logger import log_event
from backend.utils.metrics import load as load_metrics
from backend.utils.metrics import log_error, log_query, log_upload


router = APIRouter()
TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


class QueryRequest(BaseModel):
    query: str
    chat_id: str


class RenameRequest(BaseModel):
    chat_id: str
    title: str


def tokenize(text):
    return set(TOKEN_RE.findall(str(text or "").lower()))


def score_retrieval(query, chunks, answer):
    query_tokens = tokenize(query)
    answer_tokens = tokenize(answer)

    if not chunks or not query_tokens:
        return {
            "retrieval_precision_at_k": 0.0,
            "retrieval_recall_proxy": 0.0,
            "response_relevance": 0.0,
        }

    relevant_chunks = 0
    covered_query_tokens = set()

    for chunk in chunks:
        chunk_tokens = tokenize(chunk.get("text", ""))
        overlap = query_tokens & chunk_tokens
        if overlap:
            relevant_chunks += 1
            covered_query_tokens |= overlap

    return {
        "retrieval_precision_at_k": relevant_chunks / len(chunks),
        "retrieval_recall_proxy": len(covered_query_tokens) / len(query_tokens),
        "response_relevance": (
            len(query_tokens & answer_tokens) / len(query_tokens)
            if answer_tokens
            else 0.0
        ),
    }


@router.get("/health")
def health():
    return {
        "status": "ok",
        "service": "rag-app",
        "time": time.time(),
    }


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    file_type: str = "",
    chat_id: str = "",
    user=Depends(get_current_user),
):
    start_time = time.time()
    username = user["sub"].strip()
    role = user["role"].strip()

    if not file_type:
        raise HTTPException(status_code=400, detail="file_type required")

    if not chat_id:
        raise HTTPException(status_code=400, detail="chat_id required")

    temp_path = f"temp_{file.filename}"

    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        save_dir = os.path.join("uploads", username, chat_id)
        os.makedirs(save_dir, exist_ok=True)
        file_path = os.path.join(save_dir, file.filename)

        with open(temp_path, "rb") as temp_file:
            with open(file_path, "wb") as f:
                shutil.copyfileobj(temp_file, f)

        with open(file_path, "rb") as f:
            chunks = process_file(
                f,
                file_type=file_type,
                user_id=username,
                chat_id=chat_id,
                roles=[role],
            )

        if chunks <= 0:
            raise HTTPException(
                status_code=400,
                detail="No text chunks were created. Check the file type/content and backend logs.",
            )

        add_file(file.filename, username, role, chat_id, file_path)

        latency_ms = (time.time() - start_time) * 1000
        log_upload(
            file=file.filename,
            user=username,
            chat_id=chat_id,
            chunks=chunks,
            latency_ms=latency_ms,
        )
        log_event("upload", {
            "user": username,
            "file": file.filename,
            "chat_id": chat_id,
            "chunks": chunks,
            "latency_ms": round(latency_ms, 2),
        })

        return {
            "message": "File processed",
            "file": file.filename,
            "chat_id": chat_id,
            "chunks": chunks,
            "latency_ms": round(latency_ms, 2),
        }

    except HTTPException as e:
        log_error("upload_http_error", str(e.detail))
        log_event("error", {
            "type": "upload_http_error",
            "user": username,
            "chat_id": chat_id,
            "file": file.filename,
            "detail": str(e.detail),
        })
        raise
    except Exception as e:
        log_error("upload_error", str(e))
        log_event("error", {
            "type": "upload_error",
            "user": username,
            "chat_id": chat_id,
            "file": file.filename,
            "detail": str(e),
        })
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@router.post("/query")
def query_rag(req: QueryRequest, user=Depends(get_current_user)):
    username = user["sub"].strip()
    role = user["role"].strip()

    if not req.query:
        raise HTTPException(status_code=400, detail="Query required")

    if not req.chat_id:
        raise HTTPException(status_code=400, detail="chat_id required")

    if role == "guest":
        from backend.utils.guest_limit import check_limit

        if not check_limit(username):
            raise HTTPException(status_code=403, detail="Guest query limit reached")

    try:
        history = load_history(username, req.chat_id) or []
        start = time.time()

        answer, chunks, generation_metrics = rag(req.query, role, username, req.chat_id)
        chunks = chunks if isinstance(chunks, list) else []

        latency_ms = (time.time() - start) * 1000
        evaluation = score_retrieval(req.query, chunks, answer)

        telemetry = {
            **generation_metrics,
            **evaluation,
            "user": username,
            "chat_id": req.chat_id,
            "query": req.query,
            "retrieved_chunks": len(chunks),
            "latency_ms": latency_ms,
        }
        log_query(telemetry)

        log_event("query", {
            "user": username,
            "chat_id": req.chat_id,
            "latency_ms": round(latency_ms, 2),
            "query": req.query,
            "retrieved_chunks": len(chunks),
            "tokens": generation_metrics.get("total_tokens", 0),
            "retrieval_precision_at_k": evaluation["retrieval_precision_at_k"],
            "retrieval_recall_proxy": evaluation["retrieval_recall_proxy"],
            "response_relevance": evaluation["response_relevance"],
            "error": generation_metrics.get("error"),
        })

        history.append({"role": "user", "content": req.query})
        history.append({
            "role": "assistant",
            "content": answer,
            "sources": [c["text"][:200] for c in chunks],
            "telemetry": {
                "latency_ms": round(latency_ms, 2),
                "retrieved_chunks": len(chunks),
                "prompt_tokens": generation_metrics.get("prompt_tokens", 0),
                "completion_tokens": generation_metrics.get("completion_tokens", 0),
                "total_tokens": generation_metrics.get("total_tokens", 0),
                "retrieval_precision_at_k": round(evaluation["retrieval_precision_at_k"], 4),
                "retrieval_recall_proxy": round(evaluation["retrieval_recall_proxy"], 4),
                "response_relevance": round(evaluation["response_relevance"], 4),
            },
        })
        save_history(username, req.chat_id, history)

        return {
            "answer": answer,
            "sources": [c["text"][:300] for c in chunks],
            "telemetry": history[-1]["telemetry"],
        }

    except Exception as e:
        log_error("query_error", str(e))
        log_event("error", {
            "type": "query_error",
            "user": username,
            "chat_id": req.chat_id,
            "query": req.query,
            "detail": str(e),
        })
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create-chat")
def create_new_chat(user=Depends(get_current_user)):
    chat_id = create_chat(user["sub"].strip())
    return {"chat_id": chat_id}


@router.get("/get-chats")
def list_chats(user=Depends(get_current_user)):
    return {"chats": get_chats(user["sub"].strip())}


@router.delete("/delete-chat/{chat_id}")
def delete_chat_api(chat_id: str, user=Depends(get_current_user)):
    delete_chat(user["sub"].strip(), chat_id)
    return {"message": "Chat deleted"}


@router.post("/rename-chat")
def rename_chat_api(req: RenameRequest, user=Depends(get_current_user)):
    rename_chat(user["sub"].strip(), req.chat_id, req.title)
    return {"message": "Chat renamed"}


@router.get("/files")
def list_files(chat_id: str, user=Depends(get_current_user)):
    return {"files": get_files(user["sub"].strip(), chat_id)}


@router.get("/chat-history/{chat_id}")
def get_chat_history(chat_id: str, user=Depends(get_current_user)):
    return {"history": load_history(user["sub"].strip(), chat_id) or []}


@router.get("/metrics")
def get_metrics(user=Depends(get_current_user)):
    if user["role"] not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not allowed")

    return load_metrics()
