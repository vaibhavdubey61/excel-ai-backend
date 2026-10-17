import os
import shutil
import base64
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from rag_engine import RAGEngine, STUDY_MATERIALS_DIR
from ai_service import AIService

app = FastAPI(title="Excel AI - Commerce Exam Coach", version="1.0.0")

# Initialize RAG Engine and AI Service
rag = RAGEngine(storage_dir=STUDY_MATERIALS_DIR)
ai = AIService(api_key=os.getenv("GEMINI_API_KEY", ""))

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class ChatRequest(BaseModel):
    query: str
    subject: Optional[str] = "All"

class MCQRequest(BaseModel):
    subject: str
    topic: str
    count: Optional[int] = 5

class APIKeyRequest(BaseModel):
    api_key: str


@app.get("/")
async def serve_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Excel AI Coach API is active. UI file index.html is being prepared."}


@app.get("/api/stats")
async def get_system_stats():
    rag_stats = rag.get_stats()
    return {
        "status": "healthy",
        "has_api_key": ai.has_api_key(),
        "total_chunks": rag_stats["total_chunks"],
        "total_pdfs": rag_stats["total_pdfs"],
        "subjects": rag_stats["subjects"]
    }


@app.get("/api/subjects")
async def get_subjects():
    subjects = rag.get_subject_folders()
    return {"subjects": subjects}


@app.post("/api/set-api-key")
async def set_api_key(req: APIKeyRequest):
    key = req.api_key.strip()
    ai.set_api_key(key)
    return {
        "success": True,
        "message": "Gemini API Key updated successfully!",
        "has_api_key": ai.has_api_key()
    }


@app.post("/api/chat")
async def handle_doubt(req: ChatRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    
    # 1. Retrieve knowledge chunks via RAG
    chunks = rag.search(query=req.query, subject=req.subject, top_k=4)
    
    # 2. Generate answer via AI Service
    result = await ai.generate_doubt_answer(query=req.query, context_chunks=chunks, subject=req.subject or "")
    return result


@app.post("/api/evaluate")
async def evaluate_answer(
    question: str = Form(...),
    student_answer_text: Optional[str] = Form(""),
    file: Optional[UploadFile] = File(None)
):
    image_b64 = ""
    mime_type = "image/jpeg"

    if file and file.filename:
        content_bytes = await file.read()
        mime_type = file.content_type or "image/jpeg"
        image_b64 = base64.b64encode(content_bytes).decode("utf-8")

    if not student_answer_text and not image_b64:
        raise HTTPException(status_code=400, detail="Please submit either written text or upload an answer sheet photo.")

    result = await ai.evaluate_answer(
        question=question,
        student_answer_text=student_answer_text or "",
        image_base64=image_b64,
        mime_type=mime_type
    )
    return result


@app.post("/api/generate-mcq")
async def generate_mcqs(req: MCQRequest):
    result = await ai.generate_mcqs(subject=req.subject, topic=req.topic, count=req.count or 5)
    return result


@app.post("/api/upload-pdf")
async def upload_pdf(subject: str = Form(...), file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    subject_dir = os.path.join(STUDY_MATERIALS_DIR, subject)
    os.makedirs(subject_dir, exist_ok=True)

    dest_path = os.path.join(subject_dir, file.filename)
    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Reload and reindex knowledge base
    rag.load_all_materials()

    return {
        "success": True,
        "message": f"File '{file.filename}' uploaded and indexed into '{subject}' successfully!",
        "stats": rag.get_stats()
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    print(f"Starting Excel AI Prototype on http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
