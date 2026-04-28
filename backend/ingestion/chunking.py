def smart_chunk(text, size=400, overlap=50):
    words = text.split()
    chunks = []

    for i in range(0, len(words), size - overlap):
        chunk = " ".join(words[i:i+size])
        chunks.append(chunk)

    return chunks