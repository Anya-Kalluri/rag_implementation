import os
import re
import time
from urllib.parse import urlparse

from backend.db import connect, init_db
from backend.utils.chat_registry import auto_rename_chat
from backend.utils.file_metadata import get_files


WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9]{2,}|\d{4}")
ACRONYMS = {"ai", "api", "csv", "json", "jwt", "llm", "ml", "ocr", "pdf", "rag", "sql", "url"}
STOP_WORDS = {
    "about",
    "above",
    "after",
    "again",
    "also",
    "and",
    "answer",
    "any",
    "are",
    "because",
    "based",
    "before",
    "being",
    "between",
    "can",
    "chat",
    "could",
    "does",
    "document",
    "documents",
    "each",
    "file",
    "files",
    "for",
    "from",
    "give",
    "has",
    "have",
    "how",
    "its",
    "into",
    "just",
    "like",
    "may",
    "more",
    "need",
    "not",
    "only",
    "or",
    "please",
    "query",
    "question",
    "requirements",
    "should",
    "show",
    "summarise",
    "summarize",
    "summary",
    "tell",
    "than",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "these",
    "this",
    "those",
    "uploaded",
    "using",
    "what",
    "when",
    "where",
    "which",
    "with",
    "would",
    "your",
}
TITLE_FILLER_WORDS = {
    "about",
    "and",
    "for",
    "from",
    "into",
    "that",
    "the",
    "this",
    "what",
    "with",
}
FILE_TYPE_LABELS = {
    "csv": ["csv", "dataset"],
    "xls": ["excel", "dataset"],
    "xlsx": ["excel", "dataset"],
    "json": ["json", "data"],
    "pdf": ["pdf", "document"],
    "docx": ["word", "document"],
    "pptx": ["presentation"],
    "md": ["markdown", "document"],
    "txt": ["text", "document"],
    "html": ["web", "document"],
    "htm": ["web", "document"],
}
NOISY_VALUE_WORDS = {
    "female",
    "male",
    "miss",
    "missus",
    "mrs",
    "mr",
    "master",
}


def _readable_text(value):
    text = str(value or "")
    if text.startswith(("http://", "https://")):
        parsed = urlparse(text)
        text = f"{parsed.netloc} {parsed.path}"
    elif not re.search(r"\s", text) and re.search(r"\.[A-Za-z0-9]{2,5}$", text):
        text = os.path.splitext(os.path.basename(text))[0]

    return re.sub(r"[_\-./?=&%]+", " ", text)


def _keywords_from_text(text):
    keywords = []
    for word in WORD_RE.findall(_readable_text(text)):
        key = word.lower()
        if key in STOP_WORDS or key in NOISY_VALUE_WORDS:
            continue
        if any(key == existing or key in existing or existing in key for existing in keywords):
            continue
        keywords.append(key)
    return keywords


def _format_title(keywords):
    return " ".join(word.upper() if word in ACRONYMS or word.isupper() else word.title() for word in keywords)


def _file_extension(value):
    path = urlparse(str(value or "")).path if str(value or "").startswith(("http://", "https://")) else str(value or "")
    extension = os.path.splitext(path)[1].lstrip(".").lower()
    return extension


def _title_from_file_name(value):
    keywords = _keywords_from_text(value)
    if not keywords:
        return None

    extension = _file_extension(value)
    for label in FILE_TYPE_LABELS.get(extension, ["document"]):
        if len(keywords) >= 3:
            break
        if label not in keywords:
            keywords.append(label)

    while len(keywords) < 3:
        fallback = "collection" if "document" in keywords or "dataset" in keywords else "document"
        if fallback not in keywords:
            keywords.append(fallback)
        else:
            break

    return _format_title(keywords[:3]) if len(keywords) >= 3 else None


def _best_file_title(files):
    for item in files:
        for value in (item.get("file"), item.get("source_file")):
            title = _title_from_file_name(value)
            if title:
                return title
    return None


def _chunk_snippets(user, chat_id, limit=5):
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT text
            FROM chunks
            WHERE user_id = ? AND chat_id = ?
            ORDER BY position ASC
            LIMIT ?
            """,
            (user, chat_id, limit),
        ).fetchall()

    return [row["text"] for row in rows]


def suggest_chat_title(user, chat_id, latest_query=""):
    files = get_files(user=user, chat_id=chat_id)
    file_title = _best_file_title(files)
    if file_title:
        return file_title

    keywords = []
    for snippet in _chunk_snippets(user, chat_id, limit=2):
        for word in _keywords_from_text(snippet[:500]):
            if word in NOISY_VALUE_WORDS:
                continue
            keywords.append(word)
            if len(keywords) >= 3:
                break
        if len(keywords) >= 3:
            break

    clean_keywords = []
    for word in keywords:
        if any(word == existing or word in existing or existing in word for existing in clean_keywords):
            continue
        clean_keywords.append(word)
        if len(clean_keywords) == 3:
            break

    if len(clean_keywords) < 3:
        return None

    return _format_title(clean_keywords)


def auto_update_chat_title(user, chat_id, latest_query=""):
    title = suggest_chat_title(user, chat_id, latest_query=latest_query)
    if not title:
        return None

    return auto_rename_chat(user, chat_id, title)


def title_has_filler_word(title):
    words = {word.lower() for word in WORD_RE.findall(str(title or ""))}
    return bool(words & TITLE_FILLER_WORDS)


def repair_unprofessional_chat_title(user, chat_id, current_title):
    replacement = _best_file_title(get_files(user=user, chat_id=chat_id))
    if not replacement or replacement == current_title:
        return None

    current_keywords = set(_keywords_from_text(current_title))
    replacement_keywords = set(_keywords_from_text(replacement))
    should_repair = (
        title_has_filler_word(current_title)
        or bool(current_keywords & NOISY_VALUE_WORDS)
        or not (current_keywords & replacement_keywords)
    )
    if not should_repair:
        return None

    init_db()
    with connect() as conn:
        conn.execute(
            """
            UPDATE chats
            SET title = ?, auto_title = 0, updated_at = ?
            WHERE user = ? AND chat_id = ?
            """,
            (replacement, time.time(), user, chat_id),
        )

    return replacement
