import os
import re
import json
import base64
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import pypdf

from rag_engine import RAGEngine, STUDY_MATERIALS_DIR
from ai_service import AIService
from cloud_vector_store import CloudVectorStore, PINECONE_INDEX_HOST
from ingest_materials import detect_subject

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

# Anti-caching middleware: ensures users always receive latest frontend UI and scripts without stale browser caching
@app.middleware("http")
async def add_cache_control_headers(request, call_next):
    response = await call_next(request)
    if request.url.path in ["/", "/admin"] or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Initialize Cloud Vector Store, Local Fallback, and AI Engine
cloud_store = CloudVectorStore(gemini_api_key=GEMINI_KEY, pinecone_api_key=PINECONE_KEY, index_host=PINECONE_HOST)
local_rag = RAGEngine(storage_dir=STUDY_MATERIALS_DIR)
ai = AIService(api_key=GEMINI_KEY)

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

CATALOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cloud_catalog.json")

def load_catalog_data() -> List[Dict[str, Any]]:
    if os.path.exists(CATALOG_FILE):
        try:
            with open(CATALOG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_catalog_data(data: List[Dict[str, Any]]):
    try:
        with open(CATALOG_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving catalog: {e}")


@app.get("/")
async def serve_index():
    """Serves the clean student ChatGPT-style chat app."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Excel AI is online."}


@app.get("/admin")
async def serve_admin():
    """Serves the clean drag-and-drop Study Material Manager for teachers/institute."""
    admin_path = os.path.join(STATIC_DIR, "admin.html")
    if os.path.exists(admin_path):
        return FileResponse(admin_path)
    return {"message": "Admin portal is loading."}


@app.post("/api/chat")
async def chat_endpoint(
    message: Optional[str] = Form(""),
    file: Optional[UploadFile] = File(None)
):
    """Unified endpoint: queries Pinecone Cloud Vector DB and generates exam-standard answers via Gemini."""
    user_text = (message or "").strip()
    image_b64 = ""
    mime_type = "image/jpeg"

    # Safely handle optional file without AttributeError
    if file is not None and getattr(file, "filename", None):
        try:
            content_bytes = await file.read()
            mime_type = file.content_type or "image/jpeg"
            image_b64 = base64.b64encode(content_bytes).decode("utf-8")
        except Exception as e:
            print(f"[File reading error]: {e}")

    if not user_text and not image_b64:
        raise HTTPException(status_code=400, detail="Please provide a message or upload an image/document.")

    # 1. Search Knowledge Base: Priority to Pinecone Cloud Vector DB with 4.5s timeout to prevent lag
    chunks = []
    query_text = user_text if user_text else "Evaluate student answer sheet and assign step marks"
    try:
        chunks = await asyncio.wait_for(cloud_store.query(query_text, top_k=3), timeout=4.5)
    except Exception as e:
        print(f"[Vector DB notice]: {e}. Proceeding directly to AI.")

    # 2. Generate response via Gemini (with multi-model fallback and Multimodal Vision)
    reply_text = await ai.get_response(
        message=user_text,
        image_base64=image_b64 if image_b64 else None,
        mime_type=mime_type,
        context_chunks=chunks
    )

    return {"reply": reply_text}


class MCQGenerateRequest(BaseModel):
    topic: Optional[str] = "Random"
    count: Optional[int] = 10
    level: Optional[str] = "CA_Inter"


@app.post("/api/mcq/generate")
async def generate_mcq_endpoint(req: MCQGenerateRequest):
    """Generates structured interactive MCQs with options, hidden answers, and brief reasoning."""
    data = await ai.generate_interactive_mcqs(
        topic=req.topic or "Random",
        count=req.count or 10,
        level=req.level or "CA_Inter"
    )
    return data


def extract_chunks_from_pdf_stream(pdf_stream, doc_name: str, subject: str) -> (int, List[Dict[str, Any]]):
    reader = pypdf.PdfReader(pdf_stream)
    total_pages = len(reader.pages)
    chunks = []
    for page_idx, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        clean_text = re.sub(r'\s+', ' ', text).strip()
        if len(clean_text) < 40:
            continue

        words = clean_text.split()
        chunk_size = 300
        overlap = 40
        start = 0
        chunk_id = 0
        while start < len(words):
            end = min(start + chunk_size, len(words))
            block = " ".join(words[start:end])
            safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', doc_name)
            safe_id = f"{safe_name}_p{page_idx+1}_c{chunk_id}"
            chunks.append({
                "id": safe_id,
                "subject": subject,
                "doc_name": doc_name,
                "section": f"Page {page_idx+1}",
                "content": block
            })
            start += chunk_size - overlap
            chunk_id += 1
    return total_pages, chunks


@app.post("/api/admin/upload-cloud-pdf")
async def upload_cloud_pdf(
    file: UploadFile = File(...),
    subject: str = Form("General")
):
    """Admin endpoint: ingests an uploaded coaching PDF or ZIP archive of PDFs directly into Pinecone Cloud."""
    filename_lower = file.filename.lower()
    if not (filename_lower.endswith(".pdf") or filename_lower.endswith(".zip")):
        raise HTTPException(status_code=400, detail="Only PDF and ZIP files are supported.")

    content_bytes = await file.read()
    now_ts = int(datetime.now().timestamp())
    catalog = load_catalog_data()

    # Handle ZIP archive containing multiple PDFs
    if filename_lower.endswith(".zip"):
        import zipfile
        import io
        zip_stream = io.BytesIO(content_bytes)
        processed_docs = []
        total_chunks_added = 0

        with zipfile.ZipFile(zip_stream, 'r') as zf:
            pdf_names = [n for n in zf.namelist() if n.lower().endswith(".pdf") and not n.startswith("__MACOSX")]
            if not pdf_names:
                raise HTTPException(status_code=400, detail="No PDF files found inside the uploaded ZIP archive.")

            for pdf_path in pdf_names:
                doc_name = os.path.basename(pdf_path)
                pdf_subject = subject
                if subject == "General":
                    pdf_subject = detect_subject(pdf_path)

                try:
                    p_bytes = zf.read(pdf_path)
                    stream = io.BytesIO(p_bytes)
                    total_pages, chunks = extract_chunks_from_pdf_stream(stream, doc_name, pdf_subject)
                    if chunks:
                        for i in range(0, len(chunks), 20):
                            batch = chunks[i:i+20]
                            await cloud_store.upsert_chunks(batch)

                        catalog.insert(0, {
                            "id": f"mat_{now_ts}_{len(processed_docs)}",
                            "doc_name": doc_name,
                            "subject": pdf_subject,
                            "pages": total_pages,
                            "chunks": len(chunks),
                            "uploaded_at": datetime.now().isoformat()
                        })
                        processed_docs.append(doc_name)
                        total_chunks_added += len(chunks)
                except Exception as err:
                    print(f"Error processing {doc_name} from zip: {err}")

        save_catalog_data(catalog)
        return {
            "success": True,
            "message": f"Successfully extracted and indexed {len(processed_docs)} PDFs ({total_chunks_added} chunks) from ZIP archive into Pinecone Cloud!",
            "pages": len(processed_docs),
            "chunks_count": total_chunks_added
        }

    # Handle Single PDF
    import io
    doc_name = file.filename
    pdf_stream = io.BytesIO(content_bytes)
    total_pages, chunks = extract_chunks_from_pdf_stream(pdf_stream, doc_name, subject)

    if not chunks:
        raise HTTPException(status_code=400, detail="Could not extract readable text from this PDF.")

    batch_size = 20
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i+batch_size]
        await cloud_store.upsert_chunks(batch)

    catalog.insert(0, {
        "id": f"mat_{now_ts}",
        "doc_name": doc_name,
        "subject": subject,
        "pages": total_pages,
        "chunks": len(chunks),
        "uploaded_at": datetime.now().isoformat()
    })
    save_catalog_data(catalog)

    return {
        "success": True,
        "message": f"Successfully indexed '{doc_name}' into Pinecone Cloud!",
        "pages": total_pages,
        "chunks_count": len(chunks)
    }


@app.get("/api/admin/materials")
async def get_admin_materials():
    """Lists all uploaded study materials in the cloud database."""
    catalog = load_catalog_data()
    return {"materials": catalog}


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
