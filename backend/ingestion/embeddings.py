"""SentenceTransformer embedding model wrapper."""

from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"
model = None


def get_model():
    """Load the local embedding model once and reuse it across requests."""
    global model

    if model is None:
        # local_files_only avoids surprise downloads in offline/local deployments.
        model = SentenceTransformer(MODEL_NAME, local_files_only=True)

    return model


def get_embeddings(texts):
    """Convert a list of text chunks into dense vector embeddings."""
    return get_model().encode(texts)
