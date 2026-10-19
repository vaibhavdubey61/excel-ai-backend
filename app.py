import os
import base64
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from rag_engine import RAGEngine, STUDY_MATERIALS_DIR
from ai_service import AIService
from cloud_vector_store import CloudVectorStore, PINECONE_INDEX_HOST

# Load keys from environment or .env
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
PINECONE_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_HOST = os.getenv("PINECONE_INDEX_HOST", PINECONE_INDEX_HOST)

env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(env_path):
    try:
        with open(env_path, "r") as f:
            for line in f:
                if line.startswith("GEMINI_API_KEY="):
                    GEMINI_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("PINECONE_API_KEY="):
                    PINECONE_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("PINECONE_INDEX_HOST="):
                    PINECONE_HOST = line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass

app = FastAPI(title="Excel AI Coach", version="2.0.0")

# Initialize Cloud Vector Store, Local RAG Fallback, and AI Engine
cloud_store = CloudVectorStore(gemini_api_key=GEMINI_KEY, pinecone_api_key=PINECONE_KEY, index_host=PINECONE_HOST)
local_rag = RAGEngine(storage_dir=STUDY_MATERIALS_DIR)
ai = AIService(api_key=GEMINI_KEY)

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def serve_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Excel AI is online."}


@app.post("/api/chat")
async def chat_endpoint(
    message: Optional[str] = Form(""),
    file: Optional[UploadFile] = File(None)
):
    """Unified endpoint: queries Pinecone Cloud Vector DB and generates exam-standard answers via Gemini."""
    user_text = (message or "").strip()
    image_b64 = ""
    mime_type = "image/jpeg"

    if file and file.filename:
        content_bytes = await file.read()
        mime_type = file.content_type or "image/jpeg"
        image_b64 = base64.b64encode(content_bytes).decode("utf-8")

    if not user_text and not image_b64:
        raise HTTPException(status_code=400, detail="Please provide a message or upload an image/document.")

    # 1. Search Knowledge Base: Priority to Pinecone Cloud Vector DB
    chunks = []
    query_text = user_text if user_text else "Evaluate student answer sheet and assign step marks"
    try:
        chunks = await cloud_store.query(query_text, top_k=3)
    except Exception as e:
        print(f"[Cloud Vector DB warning]: {e}. Falling back to local index.")
        chunks = local_rag.search(query=query_text, top_k=3)

    # 2. Generate response via Gemini (with Multimodal Vision if handwritten image is attached)
    reply_text = await ai.get_response(
        message=user_text,
        image_base64=image_b64 if image_b64 else None,
        mime_type=mime_type,
        context_chunks=chunks
    )

    return {"reply": reply_text}


@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "cloud_vector_db": "Pinecone Serverless (AWS)",
        "ai_model": "Google Gemini 1.5 Flash (Live)"
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    print(f"Starting Excel AI on http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
