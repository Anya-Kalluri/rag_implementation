from fastapi import FastAPI
from backend.auth.routes import router as auth_router
from backend.rag.routes import router as rag_router

app = FastAPI()

app.include_router(auth_router)
app.include_router(rag_router)