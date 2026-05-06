import os
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")

SECRET_KEY = os.getenv("SECRET_KEY") or "fallback_secret"
ALGORITHM = os.getenv("ALGORITHM") or "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60))
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
LLM_PROVIDER = (os.getenv("LLM_PROVIDER") or "groq").strip().lower()
LLM_API_KEY = os.getenv("LLM_API_KEY") or GROQ_API_KEY
LLM_BASE_URL = os.getenv("LLM_BASE_URL")
DEFAULT_LLM_MODELS = {
    "groq": "llama-3.1-8b-instant",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-latest",
    "google": "gemini-1.5-flash",
    "gemini": "gemini-1.5-flash",
}
RAG_LLM_MODEL_EXPLICIT = bool(os.getenv("RAG_LLM_MODEL"))
RAG_LLM_MODEL = os.getenv("RAG_LLM_MODEL") or DEFAULT_LLM_MODELS.get(
    LLM_PROVIDER,
    "llama-3.1-8b-instant",
)
TESSERACT_CMD = os.getenv("TESSERACT_CMD")
REDIS_URL = os.getenv("REDIS_URL") or "redis://localhost:6379/0"
CHAT_SUMMARY_THRESHOLD = int(os.getenv("CHAT_SUMMARY_THRESHOLD", 5))
IMAGE_OCR_MODEL = os.getenv("IMAGE_OCR_MODEL") or "llama-3.2-11b-vision-preview"
GUEST_QUERY_LIMIT = int(os.getenv("GUEST_QUERY_LIMIT", 5))
