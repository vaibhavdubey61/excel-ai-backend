import os
import base64
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from rag_engine import RAGEngine, STUDY_MATERIALS_DIR
from ai_service import AIService

# Read API Key from environment or .env file
API_KEY = os.getenv("GEMINI_API_KEY", "")
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if not API_KEY and os.path.exists(env_path):
    try:
        with open(env_path, "r") as f:
            for line in f:
                if line.startswith("GEMINI_API_KEY="):
                    API_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    except Exception:
        pass

app = FastAPI(title="Excel AI Coach", version="2.0.0")

# Initialize RAG Engine and AI Service silently in the background
rag = RAGEngine(storage_dir=STUDY_MATERIALS_DIR)
ai = AIService(api_key=API_KEY)

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
    """Unified endpoint: handles doubts, questions, handwritten answer photos, and files."""
    user_text = (message or "").strip()
    image_b64 = ""
    mime_type = "image/jpeg"

    if file and file.filename:
        content_bytes = await file.read()
        mime_type = file.content_type or "image/jpeg"
        image_b64 = base64.b64encode(content_bytes).decode("utf-8")

    if not user_text and not image_b64:
        raise HTTPException(status_code=400, detail="Please provide a message or upload an image/document.")

    # 1. Retrieve study material context silently
    query_for_search = user_text if user_text else "Examine and evaluate student answer sheet"
    chunks = rag.search(query=query_for_search, top_k=3)

    # 2. Generate authoritative response without any source citations
    reply_text = await ai.get_response(
        message=user_text,
        image_base64=image_b64 if image_b64 else None,
        mime_type=mime_type,
        context_chunks=chunks
    )

    return {"reply": reply_text}


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}


# Admin endpoint to silently refresh PDFs when new materials are added to study_materials folder
@app.post("/api/admin/refresh-materials")
async def refresh_materials():
    rag.load_all_materials()
    return {"status": "refreshed", "chunks": len(rag.chunks)}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    print(f"Starting Excel AI on http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
