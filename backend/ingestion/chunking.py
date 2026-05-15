"""Text chunking helpers used before embedding and retrieval."""

from langchain_text_splitters import RecursiveCharacterTextSplitter


def _dedupe_chunks(chunks):
    """Normalize chunks and drop duplicates or empty strings."""
    final_chunks = []
    seen = set()
    for chunk in chunks:
        normalized = " ".join(str(chunk or "").split())
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        final_chunks.append(normalized)
    return final_chunks


def smart_chunk(text, size=1600, overlap=200):
    """Split text into overlapping chunks while preserving natural boundaries."""
    text = str(text or "").strip()
    if not text:
        return []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=size,
        chunk_overlap=overlap,
        # Prefer paragraphs and sentences before falling back to words/chars.
        separators=["\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " ", ""],
    )
    return _dedupe_chunks(splitter.split_text(text))
