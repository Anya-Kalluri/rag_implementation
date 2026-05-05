from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"
model = None


def get_model():
    global model

    if model is None:
        model = SentenceTransformer(MODEL_NAME, local_files_only=True)

    return model


def get_embeddings(texts):
    return get_model().encode(texts)
