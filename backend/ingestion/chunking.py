import re


SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _word_len(text):
    return len(text.split())


def _slice_with_overlap(words, size, overlap):
    chunks = []
    step = max(size - overlap, 1)
    for i in range(0, len(words), step):
        part = words[i:i + size]
        if part:
            chunks.append(" ".join(part))
        if i + size >= len(words):
            break
    return chunks


def _split_large_sentence(sentence, size, overlap):
    words = sentence.split()
    if len(words) <= size:
        return [sentence]
    return _slice_with_overlap(words, size, overlap)


def smart_chunk(text, size=400, overlap=50):
    text = str(text or "").strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks = []
    buffer_sentences = []
    buffer_words = 0

    for paragraph in paragraphs:
        sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(paragraph) if s.strip()]
        if not sentences:
            sentences = [paragraph]

        for sentence in sentences:
            sentence_parts = _split_large_sentence(sentence, size, overlap)
            for part in sentence_parts:
                part_words = _word_len(part)

                if buffer_words + part_words <= size:
                    buffer_sentences.append(part)
                    buffer_words += part_words
                    continue

                if buffer_sentences:
                    chunks.append(" ".join(buffer_sentences))
                    tail_words = " ".join(buffer_sentences).split()[-overlap:]
                    buffer_sentences = [" ".join(tail_words)] if tail_words else []
                    buffer_words = len(tail_words)

                if part_words > size:
                    split_parts = _split_large_sentence(part, size, overlap)
                    for split_part in split_parts:
                        if _word_len(split_part) <= size:
                            buffer_sentences.append(split_part)
                            buffer_words += _word_len(split_part)
                        else:
                            chunks.append(split_part)
                else:
                    buffer_sentences.append(part)
                    buffer_words += part_words

    if buffer_sentences:
        chunks.append(" ".join(buffer_sentences))

    # Deduplicate empty/noise chunks
    final_chunks = []
    seen = set()
    for chunk in chunks:
        normalized = " ".join(chunk.split())
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        final_chunks.append(normalized)

    return final_chunks
