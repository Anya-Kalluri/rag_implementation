import json
import os
import uuid

import faiss
import numpy as np

from .chunking import smart_chunk
from .embeddings import get_embeddings
from .loaders import *


def _load_existing_meta(meta_path):
    if not os.path.exists(meta_path):
        return []

    try:
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        return meta if isinstance(meta, list) else []
    except Exception as e:
        print("META LOAD ERROR:", e)
        return []


def _append_meta(meta, chunks, roles):
    for chunk in chunks:
        meta.append({
            "id": str(uuid.uuid4()),
            "text": chunk,
            "roles": roles,
        })


def _save_meta(meta_path, meta):
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)


def process_file(file, file_type, user_id, chat_id, roles):
    base = os.path.join("vectorstore", str(user_id).strip(), str(chat_id).strip())
    os.makedirs(base, exist_ok=True)

    index_path = os.path.join(base, "index.faiss")
    meta_path = os.path.join(base, "meta.json")

    print("\n========== INGEST START ==========")
    print("USER:", user_id)
    print("CHAT:", chat_id)
    print("PATH:", base)
    print("FILE TYPE:", file_type)

    try:
        if file_type == "pdf":
            text = load_pdf(file)
        elif file_type == "docx":
            text = load_docx(file)
        elif file_type == "pptx":
            text = load_pptx(file)
        elif file_type == "csv":
            text = load_csv(file)
        elif file_type in ("image", "png", "jpg", "jpeg"):
            text = load_image(file)
        elif file_type == "json":
            text = load_json(file)
        else:
            print("Unsupported file type:", file_type)
            return 0
    except Exception as e:
        print("LOAD ERROR:", e)
        return 0

    print("TEXT LENGTH:", len(text) if text else 0)

    if not text or not text.strip():
        print("NO TEXT EXTRACTED")
        return 0

    chunks = smart_chunk(text)
    print("CHUNKS:", len(chunks))

    if not chunks:
        print("NO CHUNKS CREATED")
        return 0

    meta = _load_existing_meta(meta_path)

    try:
        embeddings = np.asarray(get_embeddings(chunks), dtype="float32")
    except Exception as e:
        print("EMBEDDING ERROR:", e)
        _append_meta(meta, chunks, roles)
        _save_meta(meta_path, meta)
        print("SAVED TEXT METADATA WITHOUT FAISS INDEX")
        print("========== END ==========\n")
        return len(chunks)

    print("EMBEDDINGS SHAPE:", embeddings.shape)

    if embeddings.ndim != 2 or embeddings.shape[0] == 0:
        print("EMPTY OR INVALID EMBEDDINGS")
        _append_meta(meta, chunks, roles)
        _save_meta(meta_path, meta)
        return len(chunks)

    if os.path.exists(index_path):
        try:
            index = faiss.read_index(index_path)
            if getattr(index, "d", embeddings.shape[1]) != embeddings.shape[1]:
                print("INDEX DIMENSION MISMATCH; REBUILDING INDEX")
                index = faiss.IndexFlatL2(embeddings.shape[1])
                meta = []
        except Exception as e:
            print("INDEX LOAD ERROR:", e)
            index = faiss.IndexFlatL2(embeddings.shape[1])
            meta = []
    else:
        index = faiss.IndexFlatL2(embeddings.shape[1])

    index.add(embeddings)
    _append_meta(meta, chunks, roles)

    faiss.write_index(index, index_path)
    _save_meta(meta_path, meta)

    print("INGEST SUCCESS")
    print("========== END ==========\n")

    return len(chunks)
