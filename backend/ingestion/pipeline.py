import os
import uuid
import time

import faiss
import numpy as np

from backend.db import connect, decode, encode, init_db
from backend.vector_index import delete_index, read_index, write_index

from .chunking import smart_chunk
from .embeddings import get_embeddings
from .loaders import *


SUPPORTED_FILE_TYPES = {
    "pdf": load_pdf,
    "docx": load_docx,
    "pptx": load_pptx,
    "csv": load_csv,
    "json": load_json,
    "txt": load_text,
    "md": load_text,
    "html": load_html,
    "htm": load_html,
    "xlsx": load_excel,
    "xls": load_excel,
    "xml": load_xml,
    "image": load_image,
    "png": load_image,
    "jpg": load_image,
    "jpeg": load_image,
    "tif": load_image,
    "tiff": load_image,
    "bmp": load_image,
    "webp": load_image,
}


def _load_existing_chunks(user_id, chat_id):
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, text, roles_json
            FROM chunks
            WHERE user_id = ? AND chat_id = ?
            ORDER BY position ASC
            """,
            (str(user_id).strip(), str(chat_id).strip()),
        ).fetchall()

    return [
        {
            "id": row["id"],
            "text": row["text"],
            "roles": decode(row["roles_json"], []),
        }
        for row in rows
    ]


def _append_chunks(user_id, chat_id, chunks, roles):
    init_db()
    existing_count = len(_load_existing_chunks(user_id, chat_id))
    now = time.time()

    with connect() as conn:
        for offset, chunk in enumerate(chunks):
            conn.execute(
                """
                INSERT INTO chunks (id, user_id, chat_id, text, roles_json, position, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    str(user_id).strip(),
                    str(chat_id).strip(),
                    chunk,
                    encode(roles),
                    existing_count + offset,
                    now,
                ),
            )


def _replace_chunks(user_id, chat_id):
    init_db()
    with connect() as conn:
        conn.execute(
            "DELETE FROM chunks WHERE user_id = ? AND chat_id = ?",
            (str(user_id).strip(), str(chat_id).strip()),
        )


def _index_text(text, user_id, chat_id, roles):
    print("TEXT LENGTH:", len(text) if text else 0)

    if not text or not text.strip():
        print("NO TEXT EXTRACTED")
        return 0

    chunks = smart_chunk(text)
    print("CHUNKS:", len(chunks))

    if not chunks:
        print("NO CHUNKS CREATED")
        return 0

    try:
        embeddings = np.asarray(get_embeddings(chunks), dtype="float32")
    except Exception as e:
        print("EMBEDDING ERROR:", e)
        _append_chunks(user_id, chat_id, chunks, roles)
        print("SAVED TEXT METADATA WITHOUT FAISS INDEX")
        print("========== END ==========\n")
        return len(chunks)

    print("EMBEDDINGS SHAPE:", embeddings.shape)

    if embeddings.ndim != 2 or embeddings.shape[0] == 0:
        print("EMPTY OR INVALID EMBEDDINGS")
        _append_chunks(user_id, chat_id, chunks, roles)
        return len(chunks)

    try:
        index = read_index(user_id, chat_id)
        if index is not None and getattr(index, "d", embeddings.shape[1]) != embeddings.shape[1]:
            print("INDEX DIMENSION MISMATCH; REBUILDING INDEX")
            index = faiss.IndexFlatL2(embeddings.shape[1])
            _replace_chunks(user_id, chat_id)
            delete_index(user_id, chat_id)
    except Exception as e:
        print("INDEX LOAD ERROR:", e)
        index = faiss.IndexFlatL2(embeddings.shape[1])
        _replace_chunks(user_id, chat_id)
        delete_index(user_id, chat_id)

    if index is None:
        index = faiss.IndexFlatL2(embeddings.shape[1])

    index.add(embeddings)
    _append_chunks(user_id, chat_id, chunks, roles)
    write_index(user_id, chat_id, index)

    print("INGEST SUCCESS")
    print("========== END ==========\n")
    return len(chunks)


def process_file(file, file_type, user_id, chat_id, roles):
    print("\n========== INGEST START ==========")
    print("USER:", user_id)
    print("CHAT:", chat_id)
    print("FILE TYPE:", file_type)

    try:
        loader = SUPPORTED_FILE_TYPES.get(file_type.lower().strip())
        if not loader:
            print("Unsupported file type:", file_type)
            raise ValueError(f"Unsupported file type: {file_type}")
        text = loader(file)
    except Exception as e:
        print("LOAD ERROR:", e)
        raise ValueError(f"Could not extract text from {file_type}: {e}") from e

    return _index_text(text, user_id, chat_id, roles)


def process_text(text, user_id, chat_id, roles, source_type="text"):
    print("\n========== INGEST START ==========")
    print("USER:", user_id)
    print("CHAT:", chat_id)
    print("FILE TYPE:", source_type)
    return _index_text(text, user_id, chat_id, roles)
