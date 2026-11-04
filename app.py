from contextlib import asynccontextmanager
import os
import re
import json
import base64
import asyncio
import time
from collections import defaultdict
from datetime import datetime
import uuid
import csv
import io
from typing import Optional, List, Dict, Any, Tuple
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel
import pypdf
import psutil

from rag_engine import RAGEngine, STUDY_MATERIALS_DIR
from ai_service import AIService, clean_student_reply
from cloud_vector_store import CloudVectorStore, PINECONE_INDEX_HOST
from ingest_materials import detect_subject
from reranker import get_reranker, CrossEncoderReranker
from rate_limiter import rate_limiter, get_rate_limiter, InMemoryFallbackLimiter
import db
import syllabus
import video_service
import structlog
import logging
from guardrails import check_input_guardrails, SAFE_CANNED_RESPONSE

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger("excel_ai.app")

# Global in-memory registry for background ingestion jobs
JOBS: Dict[str, Dict[str, Any]] = {}

# Load keys and config from environment or .env
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
PINECONE_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_HOST = os.getenv("PINECONE_INDEX_HOST", PINECONE_INDEX_HOST)
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/app.db")
MIN_SCORE = float(os.getenv("MIN_SCORE", "0.62"))

env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(env_path):
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("GEMINI_API_KEY="):
                    GEMINI_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("PINECONE_API_KEY="):
                    PINECONE_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("PINECONE_INDEX_HOST="):
                    PINECONE_HOST = line.split("=", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("ADMIN_PASSWORD="):
                    ADMIN_PASSWORD = line.split("=", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("DATABASE_URL="):
                    DATABASE_URL = line.split("=", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("MIN_SCORE="):
                    MIN_SCORE = float(line.split("=", 1)[1].strip().strip('"').strip("'"))
    except Exception:
        pass

# Initialize database
db.init_db()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager: initializes distributed Redis rate limiter (fail-open) and handles graceful shutdown."""
    try:
        await rate_limiter.init()
    except Exception as e:
        logger.error("Rate limiter initialization failed", error=str(e))
    yield
    try:
        await rate_limiter.close()
    except Exception as e:
        logger.info("Rate limiter close notice", error=str(e))

app = FastAPI(title="Excel AI Coach", version="2.0.0", lifespan=lifespan)

@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    req_id = request.headers.get("x-request-id") or request.headers.get("x-correlation-id") or str(uuid.uuid4())
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=req_id)
    response = await call_next(request)
    response.headers["X-Request-ID"] = req_id
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Anti-caching middleware: ensures users always receive latest frontend UI and scripts without stale browser caching
@app.middleware("http")
async def add_cache_control_headers(request, call_next):
    response = await call_next(request)
    if request.url.path in ["/", "/admin"] or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Backward-compatible references for rate limiting
InMemoryRateLimiter = InMemoryFallbackLimiter
chat_limiter = rate_limiter.fallback_limiter

def verify_admin(request: Request):
    """Enforces simple admin authentication via X-Admin-Key header."""
    key = request.headers.get("X-Admin-Key")
    if not key or key != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid Admin Key")

# Initialize Cloud Vector Store, Local Fallback, Reranker, and AI Engine
cloud_store = CloudVectorStore(gemini_api_key=GEMINI_KEY, pinecone_api_key=PINECONE_KEY, index_host=PINECONE_HOST)
local_rag = RAGEngine(storage_dir=STUDY_MATERIALS_DIR)
reranker = get_reranker()
ai = AIService(api_key=GEMINI_KEY)

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def serve_index():
    """Serves the clean student ChatGPT-style chat app."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Excel AI is online."}


@app.get("/admin")
async def serve_admin(request: Request):
    """Serves the clean drag-and-drop Study Material Manager for teachers/institute."""
    admin_key = request.headers.get("X-Admin-Key")
    if admin_key and admin_key != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid Admin Key")
    admin_path = os.path.join(STATIC_DIR, "admin.html")
    if os.path.exists(admin_path):
        return FileResponse(admin_path)
    return {"message": "Admin portal is loading."}


@app.get("/ops")
def serve_ops():
    ops_path = os.path.join(STATIC_DIR, "ops.html")
    if os.path.exists(ops_path):
        return FileResponse(ops_path)
    return {"message": "Ops dashboard is loading."}

@app.post("/api/chat")
async def chat_endpoint(
    request: Request,
    message: Optional[str] = Form(""),
    file: Optional[UploadFile] = File(None),
    course: Optional[str] = Form("CA"),
    level: Optional[str] = Form("Inter"),
    history: Optional[str] = Form("[]"),
    session_id: Optional[str] = Form(None),
    stream: Optional[str] = Form(None)
):
    """Unified endpoint: queries Pinecone Cloud Vector DB with Cross-Encoder reranking, supporting real-time SSE streaming."""
    # Distributed Redis Rate Limiting (30 requests/minute per client IP or API key, fail-open)
    await rate_limiter.check(request, limit=30, window_seconds=60)

    # Validate course and level against syllabus
    c_norm = syllabus.normalize_course(course or "CA")
    l_norm = syllabus.normalize_level(c_norm, level or "Inter")
    if not syllabus.is_valid_course_level(c_norm, l_norm):
        raise HTTPException(status_code=400, detail=f"Invalid course/level: {course} {level}")

    # Parse conversation history (last 6 turns)
    parsed_history: List[Dict[str, str]] = []
    if history:
        try:
            parsed_history = json.loads(history)
            if not isinstance(parsed_history, list):
                parsed_history = []
        except Exception:
            parsed_history = []
    parsed_history = parsed_history[-6:]

    user_text = (message or "").strip()
    image_b64 = ""
    mime_type = "image/jpeg"

    # Fast input guardrails check against prompt injection (<10ms)
    is_safe, matched_pattern = check_input_guardrails(user_text)
    if not is_safe:
        logger.warning(
            "Prompt injection attempt blocked by guardrails",
            matched_pattern=matched_pattern,
            user_text=user_text[:120],
        )
        return {"reply": SAFE_CANNED_RESPONSE}

    # Safely handle optional file without AttributeError
    if file is not None and getattr(file, "filename", None):
        try:
            content_bytes = await file.read()
            mime_type = file.content_type or "image/jpeg"
            image_b64 = base64.b64encode(content_bytes).decode("utf-8")
        except Exception as e:
            logger.error("File reading error", error=str(e))

    if not user_text and not image_b64:
        raise HTTPException(status_code=400, detail="Please provide a message or upload an image/document.")

    # 0. Check for YouTube / Teaching Lecture Video link
    client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "unknown")
    effective_session = session_id or client_ip
    youtube_id = video_service.extract_youtube_video_id(user_text)

    is_summary_request = any(p in user_text.lower() for p in ["summarize this", "summarize the video", "video summary", "lecture summary", "explain this video", "summarize"])
    if not youtube_id and is_summary_request:
        for msg in reversed(parsed_history):
            h_yt = video_service.extract_youtube_video_id(msg.get("text", ""))
            if h_yt:
                youtube_id = h_yt
                break

    if youtube_id:
        meta = video_service.fetch_youtube_metadata(youtube_id)
        v_title = meta.get("title") or "CA Exam Prep Teaching Lecture"
        v_author = meta.get("author_name") or "Excel Educational Institute"

        transcript, err = video_service.fetch_youtube_transcript_text(youtube_id)
        if transcript:
            summary_prompt = video_service.format_video_summary_prompt(
                transcript, course=c_norm, level=l_norm, student_note=user_text, video_title=v_title
            )
            context_notes = transcript
        else:
            summary_prompt = video_service.format_video_metadata_summary_prompt(
                youtube_id, title=v_title, author=v_author, course=c_norm, level=l_norm, student_note=user_text
            )
            context_notes = f"Lecture: {v_title} by {v_author}"

        try:
            res = await ai.get_response(
                message=summary_prompt,
                course=c_norm,
                level=l_norm,
                history=[]
            )
            summary_reply = video_service.clean_video_summary(clean_student_reply(res.get("reply", "")))
            if effective_session:
                video_service.store_video_session(
                    effective_session, youtube_id, context_notes, summary_reply, title=v_title, author=v_author
                )
            return {"reply": summary_reply}
        except Exception as e:
            logger.error("Video summary error", error=str(e))
            raise HTTPException(status_code=503, detail="The AI is busy summarizing the video. Please try again in a moment.")

    # If this session has an active shared video, attach teaching context for doubt solving
    active_video = video_service.get_video_session(effective_session)
    if not active_video:
        for msg in reversed(parsed_history):
            h_yt = video_service.extract_youtube_video_id(msg.get("text", ""))
            if h_yt:
                h_meta = video_service.fetch_youtube_metadata(h_yt)
                h_title = h_meta.get("title") or "CA Exam Prep Teaching Lecture"
                active_video = {
                    "video_id": h_yt,
                    "title": h_title,
                    "author": h_meta.get("author_name") or "Excel Educational Institute",
                    "transcript": f"Lecture: {h_title}",
                    "summary": ""
                }
                break

    if active_video and "transcript" in active_video:
        v_label = active_video.get('title') or active_video.get('video_id', '')
        lecture_ctx = (
            f"[CONTEXT FROM SHARED TEACHING VIDEO '{v_label}' ({active_video.get('video_id', '')})]:\n"
            f"The student previously shared this lecture in chat and is now asking doubts or concepts from it.\n"
            f"Faculty Spoken Notes / Lecture Content:\n{active_video.get('transcript', '')[:4000]}\n"
            f"Answer the student's doubt directly using what the faculty taught in this video, aligning strictly with ICAI standards.\n\n"
        )
        user_text = f"{lecture_ctx}Student's Doubt: {user_text}"

    # 1. Retrieval query building
    search_query = user_text
    if image_b64 and len(user_text.split()) < 4:
        extracted_question = await ai.extract_question_from_image(image_b64, mime_type=mime_type)
        if extracted_question:
            search_query = f"{user_text} {extracted_question}".strip()
    elif parsed_history and len(user_text.split()) < 10:
        last_user_turn = ""
        for item in reversed(parsed_history):
            if item.get("role") in ["user", "student"]:
                last_user_turn = item.get("text") or item.get("content") or ""
                break
        if last_user_turn:
            search_query = f"{last_user_turn} {user_text}".strip()

    # Determine whether client requested SSE streaming
    user_agent = request.headers.get("user-agent", "").lower()
    accept_hdr = request.headers.get("accept", "").lower()
    is_curl = "curl" in user_agent
    accepts_sse = "text/event-stream" in accept_hdr
    explicit_stream = (stream or "").strip().lower() in ("true", "1", "yes") if stream is not None else None
    explicit_no_stream = (stream or "").strip().lower() in ("false", "0", "no") if stream is not None else False
    is_test_client = user_agent == "testclient"

    is_streaming = (
        (explicit_stream is True)
        or accepts_sse
        or is_curl
        or (explicit_stream is None and not explicit_no_stream and not is_test_client and "application/json" not in accept_hdr)
    )

    if is_streaming:
        async def chat_sse_stream():
            start_t = time.time()
            # Event 1: Immediate notification to the student
            yield f"data: {json.dumps({'event': 'status', 'message': 'Searching knowledge base...'})}\n\n"

            # RAG Pipeline: Retrieve top-5 from Pinecone (cosine similarity) with TF-IDF fallback.
            # NOTE: Local cross-encoder reranker was removed to prevent OOM on 512MB containers.
            # The lightweight pass-through reranker in reranker.py applies MIN_SCORE + top-k sorting.
            # To restore high-precision reranking, integrate Jina/Cohere Rerank API in reranker.py.
            ns = syllabus.namespace(c_norm, l_norm)
            candidate_chunks: List[Dict[str, Any]] = []
            stream_chunks: List[Dict[str, Any]] = []
            retrieval_ok = True

            if search_query:
                try:
                    raw_chunks = await asyncio.wait_for(
                        cloud_store.query(search_query, namespace=ns, top_k=5),
                        timeout=6.0
                    )
                    candidate_chunks = list(raw_chunks)
                except Exception as e:
                    logger.warning("Vector DB notice, checking local knowledge fallback", namespace=ns, error=str(e))
                    retrieval_ok = False

                if not candidate_chunks:
                    try:
                        local_results = local_rag.search(search_query, top_k=5)
                        for lr in local_results:
                            if lr.get("relevance_score", 0.0) >= 0.12:
                                candidate_chunks.append({
                                    "doc_name": lr.get("doc_name", ""),
                                    "section": lr.get("section", ""),
                                    "content": lr.get("content", ""),
                                    "score": lr.get("relevance_score", 0.0),
                                    "subject": lr.get("subject", "")
                                })
                        if candidate_chunks:
                            logger.info("Local RAG fallback found candidate excerpts", count=len(candidate_chunks))
                    except Exception as l_err:
                        logger.warning("Local RAG notice", error=str(l_err))

                if candidate_chunks:
                    # Pass-through reranker: sorts by score, applies MIN_SCORE filter, returns top-k.
                    try:
                        stream_chunks = await reranker.rerank(
                            query=search_query,
                            chunks=candidate_chunks,
                            top_k=4,
                            min_score=MIN_SCORE
                        )
                    except Exception as r_err:
                        logger.warning("Reranker warning", error=str(r_err))
                        stream_chunks = [c for c in candidate_chunks if c.get("score", 0.0) >= MIN_SCORE][:4]

            if stream_chunks:
                yield f"data: {json.dumps({'event': 'status', 'message': f'Found {len(stream_chunks)} relevant excerpts. Formulating answer...'})}\n\n"

            # 3. Stream tokens from LLM
            collected_tokens = []
            try:
                async for token in ai.stream_response(
                    message=user_text,
                    image_base64=image_b64 if image_b64 else None,
                    mime_type=mime_type,
                    context_chunks=stream_chunks,
                    course=c_norm,
                    level=l_norm,
                    history=parsed_history
                ):
                    collected_tokens.append(token)
                    yield f"data: {json.dumps({'token': token})}\n\n"
            except Exception as stream_err:
                logger.error("Streaming AI error", error=str(stream_err))
                yield f"data: {json.dumps({'error': 'The AI is busy right now. Please try again in a moment.'})}\n\n"
                return

            full_reply = "".join(collected_tokens)
            cleaned = clean_student_reply(full_reply)
            top_score = max([c.get("score", 0.0) for c in stream_chunks], default=0.0)

            # 4. Final completion event
            yield f"data: {json.dumps({'event': 'done', 'reply': cleaned})}\n\n"

            # 5. Background log interaction
            try:
                resp_time = round(time.time() - start_t, 3)
                db.log_chat_interaction(
                    timestamp=datetime.now().isoformat(),
                    course=c_norm,
                    level=l_norm,
                    question=user_text or search_query,
                    answer_preview=cleaned[:200],
                    source="material" if stream_chunks else "general",
                    top_score=top_score,
                    retrieval_ok=retrieval_ok,
                    model_used=ai.last_model_used,
                    response_time_ms=int(resp_time * 1000)
                )
            except Exception as log_err:
                logger.warning("Chat log warning", error=str(log_err))

        return StreamingResponse(
            chat_sse_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

    # Non-streaming path (for TestClient, evaluation scripts, and admin workflows)
    ns = syllabus.namespace(c_norm, l_norm)
    candidate_chunks: List[Dict[str, Any]] = []
    chunks: List[Dict[str, Any]] = []
    retrieval_ok = True
    start_t = time.time()

    if search_query:
        try:
            raw_chunks = await asyncio.wait_for(
                cloud_store.query(search_query, namespace=ns, top_k=5),
                timeout=6.0
            )
            candidate_chunks = list(raw_chunks)
        except Exception as e:
            logger.warning("Vector DB notice, checking local knowledge fallback", namespace=ns, error=str(e))
            retrieval_ok = False

        if not candidate_chunks:
            try:
                local_results = local_rag.search(search_query, top_k=5)
                for lr in local_results:
                    if lr.get("relevance_score", 0.0) >= 0.12:
                        candidate_chunks.append({
                            "doc_name": lr.get("doc_name", ""),
                            "section": lr.get("section", ""),
                            "content": lr.get("content", ""),
                            "score": lr.get("relevance_score", 0.0),
                            "subject": lr.get("subject", "")
                        })
                if candidate_chunks:
                    logger.info("Local RAG fallback found candidate excerpts", count=len(candidate_chunks))
            except Exception as l_err:
                logger.warning("Local RAG notice", error=str(l_err))

        if candidate_chunks:
            # Pass-through reranker: sorts by score, applies MIN_SCORE filter, returns top-k.
            try:
                chunks = await reranker.rerank(
                    query=search_query,
                    chunks=candidate_chunks,
                    top_k=4,
                    min_score=MIN_SCORE
                )
            except Exception as r_err:
                logger.warning("Score-sort reranking warning", error=str(r_err))
                chunks = [c for c in candidate_chunks if c.get("score", 0.0) >= MIN_SCORE][:4]

    try:
        res = await ai.get_response(
            message=user_text,
            image_base64=image_b64 if image_b64 else None,
            mime_type=mime_type,
            context_chunks=chunks,
            course=c_norm,
            level=l_norm,
            history=parsed_history
        )
    except Exception as e:
        logger.error("AI chat error", error=str(e))
        raise HTTPException(
            status_code=503,
            detail="The AI is busy right now. Please try again in a moment."
        )

    resp_time = round(time.time() - start_t, 3)

    try:
        resp_time_ms = int(resp_time * 1000)
        answer_preview = res.get("reply", "")[:200]
        db.log_chat_interaction(
            timestamp=datetime.now().isoformat(),
            course=c_norm,
            level=l_norm,
            question=user_text or search_query,
            answer_preview=answer_preview,
            source=res.get("source", "general"),
            top_score=res.get("top_score", 0.0),
            retrieval_ok=retrieval_ok,
            model_used=res.get("model_used", ""),
            response_time_ms=resp_time_ms
        )
    except Exception as log_err:
        logger.warning("Chat log warning", error=str(log_err))

    return {"reply": clean_student_reply(res["reply"])}


class MCQGenerateRequest(BaseModel):
    course: Optional[str] = "CA"
    level: Optional[str] = "Inter"
    subject: Optional[str] = None
    topic: Optional[str] = "Random"
    count: Optional[int] = 10



class VideoSummarizeRequest(BaseModel):
    video_url: str
    course: Optional[str] = "CA"
    level: Optional[str] = "Inter"
    session_id: Optional[str] = ""
    note: Optional[str] = ""


@app.post("/api/video/summarize")
async def summarize_video_endpoint(req: VideoSummarizeRequest):
    """Generates an academic summary of a shared teaching video without timestamps."""
    youtube_id = video_service.extract_youtube_video_id(req.video_url)
    if not youtube_id:
        raise HTTPException(status_code=400, detail="Invalid YouTube video URL. Please provide a valid link.")

    transcript, err = video_service.fetch_youtube_transcript_text(youtube_id)
    if not transcript:
        raise HTTPException(status_code=422, detail=f"Could not retrieve captions from this video: {err}")

    summary_prompt = video_service.format_video_summary_prompt(
        transcript, course=req.course or "CA", level=req.level or "Inter", student_note=req.note
    )
    res = await ai.get_response(
        message=summary_prompt,
        course=req.course or "CA",
        level=req.level or "Inter",
        history=[]
    )
    clean_summary = video_service.clean_video_summary(clean_student_reply(res.get("reply", "")))
    if req.session_id:
        video_service.store_video_session(req.session_id, youtube_id, transcript, clean_summary)

    return {
        "success": True,
        "video_id": youtube_id,
        "summary": clean_summary
    }

@app.post("/api/mcq/generate")
async def generate_mcq_endpoint(req: MCQGenerateRequest):
    """
    Generates structured interactive MCQs with options, hidden answers, and brief reasoning.
    Validates course and level against SYLLABUS.
    Pulls top-k relevant chunks from Pinecone in student's namespace with optional subject filter.
    Falls back to level-aware general knowledge if no chunks found.
    """
    raw_course = (req.course or "CA").strip()
    raw_level = (req.level or "Inter").strip()

    # Handle legacy level values like "CA_Inter" or "CA-Foundation"
    if "_" in raw_level and (not req.course or req.course == "CA"):
        parts = raw_level.split("_", 1)
        raw_course, raw_level = parts[0], parts[1]
    elif "-" in raw_level and (not req.course or req.course == "CA"):
        parts = raw_level.split("-", 1)
        raw_course, raw_level = parts[0], parts[1]

    norm_course = syllabus.normalize_course(raw_course)
    norm_level = syllabus.normalize_level(norm_course, raw_level)

    if not syllabus.is_valid_course_level(norm_course, norm_level):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid course/level: '{raw_course} {raw_level}'. Valid options include CA (Foundation, Inter, Final), CS (Executive, Professional), CMA (Foundation, Inter, Final)."
        )

    ns = syllabus.namespace(norm_course, norm_level)
    count = max(1, min(int(req.count or 10), 20))
    subject = req.subject.strip() if req.subject and req.subject.strip().lower() not in ["", "all", "all subjects", "general"] else None
    topic = req.topic.strip() if req.topic and req.topic.strip().lower() not in ["", "random", "all", "mixed"] else "Random"

    chunks = []
    if cloud_store.is_ready():
        try:
            if topic != "Random" and subject:
                query_text = f"{subject}: {topic}"
            elif topic != "Random":
                query_text = topic
            elif subject:
                query_text = f"{subject} exam concepts provisions and problems"
            else:
                query_text = f"{norm_course} {norm_level} exam syllabus key concepts"

            raw_chunks = await asyncio.wait_for(
                cloud_store.query(
                    query_text=query_text,
                    namespace=ns,
                    top_k=8,
                    subject=subject
                ),
                timeout=8.0
            )
            chunks = [c for c in raw_chunks if c.get("score", 0.0) >= MIN_SCORE and c.get("content")]
            chunks = chunks[:5]
        except Exception as query_err:
            logger.warning("MCQ Pinecone query warning", error=str(query_err))
            chunks = []

    try:
        data = await ai.generate_interactive_mcqs(
            course=norm_course,
            level=norm_level,
            subject=subject,
            topic=topic,
            count=count,
            chunks=chunks
        )
        return data
    except Exception as e:
        logger.error("AI MCQ error", error=str(e))
        raise HTTPException(
            status_code=503,
            detail="The AI is busy right now. Please try again in a moment."
        )



@app.post("/api/evaluate")
async def evaluate_endpoint(
    request: Request,
    question: str = Form(...),
    student_answer: Optional[str] = Form(""),
    course: Optional[str] = Form("CA"),
    level: Optional[str] = Form("Inter"),
    subject: Optional[str] = Form(""),
    total_marks: Optional[int] = Form(10),
    file: Optional[UploadFile] = File(None)
):
    """
    Evaluates student subjective exam answer papers against authentic ICAI BoS rubrics.
    Supports multimodal inputs: photos of handwritten answers, PDF answer copies, or typed text.
    Grounded in level-segregated Pinecone study materials.
    """
    client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "unknown")
    if not chat_limiter.is_allowed(client_ip):
        raise HTTPException(status_code=429, detail="Too many evaluation requests. Please pause a moment.")

    c_norm = syllabus.normalize_course(course or "CA")
    l_norm = syllabus.normalize_level(c_norm, level or "Inter")

    images = []
    if file is not None and getattr(file, "filename", None):
        try:
            file_bytes = await file.read()
            mime = file.content_type or "image/jpeg"
            b64_str = base64.b64encode(file_bytes).decode("utf-8")
            images.append({"data": b64_str, "mime_type": mime})
        except Exception as file_err:
            logger.error("Evaluation file read error", error=str(file_err))

    # Grounding: retrieve relevant study material from Pinecone
    ns = syllabus.namespace(c_norm, l_norm)
    chunks = []
    if cloud_store.is_ready():
        try:
            raw_chunks = await asyncio.wait_for(
                cloud_store.query(
                    query_text=f"{subject} {question}".strip(),
                    namespace=ns,
                    top_k=5,
                    subject=subject or None
                ),
                timeout=6.0
            )
            chunks = [c for c in raw_chunks if c.get("score", 0.0) >= MIN_SCORE]
        except Exception as query_err:
            logger.warning("Evaluation retrieval notice", error=str(query_err))

    try:
        result = await ai.evaluate_subjective_answer(
            question=question,
            student_answer=student_answer or "",
            course=c_norm,
            level=l_norm,
            subject=subject or "",
            total_marks=total_marks or 10,
            images=images if images else None,
            reference_chunks=chunks if chunks else None
        )
        return result
    except Exception as e:
        logger.error("Evaluation engine error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Evaluation could not be completed: {str(e)}")


@app.get("/api/syllabus")
async def get_syllabus():
    """Returns the full syllabus hierarchy (course -> level -> subjects)."""
    return {"syllabus": syllabus.SYLLABUS}


def extract_chunks_from_pdf_stream(
    pdf_stream,
    doc_name: str,
    subject: str,
    course: str = "",
    level: str = ""
) -> Tuple[int, List[Dict[str, Any]], bool]:
    """
    Extracts text chunks from PDF stream.
    Prefixes each chunk with '[{subject} | {doc_name} | Page N]' to retain structural context.
    Detects scanned image pages that yield no text and marks needs_ocr.
    """
    reader = pypdf.PdfReader(pdf_stream)
    total_pages = len(reader.pages)
    chunks = []
    has_scanned_page = False

    for page_idx, page in enumerate(reader.pages):
        page_num = page_idx + 1
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        clean_text = re.sub(r'\s+', ' ', text).strip()
        if len(clean_text) < 40:
            has_scanned_page = True
            continue

        words = clean_text.split()
        chunk_size = 300
        overlap = 40
        start = 0
        chunk_id = 0
        prefix = f"[{subject} | {doc_name} | Page {page_num}]"

        while start < len(words):
            end = min(start + chunk_size, len(words))
            block = " ".join(words[start:end])
            full_chunk_text = f"{prefix}\n{block}"
            safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', doc_name)
            safe_id = f"{safe_name}_p{page_num}_c{chunk_id}"
            chunks.append({
                "id": safe_id,
                "subject": subject,
                "doc_name": doc_name,
                "section": f"Page {page_num}",
                "course": course,
                "level": level,
                "topic": subject,
                "content": full_chunk_text
            })
            start += chunk_size - overlap
            chunk_id += 1

    return total_pages, chunks, has_scanned_page


async def process_ingestion_job(
    job_id: str,
    content_bytes: bytes,
    filename: str,
    course: str,
    level: str,
    subject: str
):
    """Background task worker: ingests PDFs into course/level Pinecone namespace without request timeouts."""
    job = JOBS.get(job_id)
    if not job:
        return

    ns = syllabus.namespace(course, level)
    now_ts = int(time.time())

    try:
        job["status"] = "processing"
        job["progress"] = 15
        job["message"] = f"Extracting syllabus text from {filename}..."

        filename_lower = filename.lower()
        if filename_lower.endswith(".zip"):
            import zipfile
            import io
            zip_stream = io.BytesIO(content_bytes)
            processed_docs = []
            total_chunks_added = 0
            has_ocr_needed = False

            with zipfile.ZipFile(zip_stream, 'r') as zf:
                pdf_names = [n for n in zf.namelist() if n.lower().endswith(".pdf") and not n.startswith("__MACOSX")]
                if not pdf_names:
                    job["status"] = "failed"
                    job["error"] = "No PDF files found inside the uploaded ZIP archive."
                    job["message"] = "No PDF files found inside the uploaded ZIP archive."
                    return

                total_pdfs = len(pdf_names)
                for idx, pdf_path in enumerate(pdf_names):
                    doc_name = os.path.basename(pdf_path)
                    pdf_subject = subject
                    if subject == "General" or not subject:
                        pdf_subject = detect_subject(pdf_path)

                    try:
                        p_bytes = zf.read(pdf_path)
                        stream = io.BytesIO(p_bytes)
                        total_pages, chunks, needs_ocr = extract_chunks_from_pdf_stream(
                            stream, doc_name, pdf_subject, course=course, level=level
                        )
                        if needs_ocr:
                            has_ocr_needed = True

                        if chunks:
                            await cloud_store.upsert_chunks(chunks, namespace=ns)
                            db.insert_material({
                                "id": f"mat_{now_ts}_{len(processed_docs)}",
                                "doc_name": doc_name,
                                "subject": pdf_subject,
                                "pages": total_pages,
                                "chunks": len(chunks),
                                "uploaded_at": datetime.now().isoformat(),
                                "course": course,
                                "level": level,
                                "needs_ocr": 1 if needs_ocr else 0
                            })
                            processed_docs.append(doc_name)
                            total_chunks_added += len(chunks)
                    except Exception as err:
                        logger.error("Error processing document from zip", doc_name=doc_name, error=str(err))

                    pct = int(15 + ((idx + 1) / total_pdfs) * 80)
                    job["progress"] = min(pct, 95)
                    job["message"] = f"Processed {idx + 1}/{total_pdfs} PDFs ({total_chunks_added} chunks into '{ns}')..."

            job["status"] = "completed"
            job["progress"] = 100
            job["chunks_count"] = total_chunks_added
            job["pages_count"] = len(processed_docs)
            job["needs_ocr"] = has_ocr_needed
            job["message"] = f"Successfully extracted and indexed {len(processed_docs)} PDFs ({total_chunks_added} chunks) into namespace '{ns}'!"

        else:
            # Single PDF
            import io
            doc_name = filename
            pdf_stream = io.BytesIO(content_bytes)
            total_pages, chunks, needs_ocr = extract_chunks_from_pdf_stream(
                pdf_stream, doc_name, subject, course=course, level=level
            )

            job["progress"] = 40
            job["message"] = f"Generated {len(chunks)} chunks across {total_pages} pages. Upserting to '{ns}'..."

            if not chunks:
                job["status"] = "failed"
                job["error"] = "Could not extract readable text from this PDF (scanned image PDF requires OCR)."
                job["message"] = "Could not extract readable text from this PDF (scanned image PDF requires OCR)."
                db.insert_material({
                    "id": f"mat_{now_ts}",
                    "doc_name": doc_name,
                    "subject": subject,
                    "pages": total_pages,
                    "chunks": 0,
                    "uploaded_at": datetime.now().isoformat(),
                    "course": course,
                    "level": level,
                    "needs_ocr": 1
                })
                return

            await cloud_store.upsert_chunks(chunks, namespace=ns)

            db.insert_material({
                "id": f"mat_{now_ts}",
                "doc_name": doc_name,
                "subject": subject,
                "pages": total_pages,
                "chunks": len(chunks),
                "uploaded_at": datetime.now().isoformat(),
                "course": course,
                "level": level,
                "needs_ocr": 1 if needs_ocr else 0
            })

            job["status"] = "completed"
            job["progress"] = 100
            job["chunks_count"] = len(chunks)
            job["pages_count"] = total_pages
            job["needs_ocr"] = needs_ocr
            job["message"] = f"Successfully indexed '{doc_name}' ({len(chunks)} chunks) into namespace '{ns}'!"

    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)
        job["message"] = f"Ingestion error: {e}"
        logger.error("Ingestion error", error=str(e))
    finally:
        job["updated_at"] = datetime.now().isoformat()


@app.post("/api/admin/upload-cloud-pdf")
async def upload_cloud_pdf(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    course: str = Form(...),
    level: str = Form(...),
    subject: str = Form("General")
):
    """Admin endpoint: schedules background ingestion into course/level Pinecone namespace."""
    verify_admin(request)

    # Validate course and level against syllabus
    if not syllabus.is_valid_course_level(course, level):
        raise HTTPException(status_code=400, detail=f"Invalid course/level: {course} {level}")

    filename_lower = file.filename.lower()
    if not (filename_lower.endswith(".pdf") or filename_lower.endswith(".zip")):
        raise HTTPException(status_code=400, detail="Only PDF and ZIP files are supported.")

    content_bytes = await file.read()
    job_id = f"job_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    ns = syllabus.namespace(course, level)

    JOBS[job_id] = {
        "id": job_id,
        "status": "queued",
        "progress": 5,
        "message": f"Queued '{file.filename}' for ingestion into namespace '{ns}'...",
        "course": course,
        "level": level,
        "subject": subject,
        "filename": file.filename,
        "chunks_count": 0,
        "pages_count": 0,
        "needs_ocr": False,
        "error": None,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }

    background_tasks.add_task(
        process_ingestion_job,
        job_id=job_id,
        content_bytes=content_bytes,
        filename=file.filename,
        course=course,
        level=level,
        subject=subject
    )

    return {
        "success": True,
        "job_id": job_id,
        "status": "queued",
        "namespace": ns,
        "message": f"Upload received. Processing '{file.filename}' in background for namespace '{ns}'."
    }


@app.get("/api/admin/jobs/{job_id}")
async def get_job_status(request: Request, job_id: str):
    """Admin endpoint: inspects progress and status of a background ingestion job."""
    verify_admin(request)
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/admin/materials")
async def get_admin_materials(request: Request):
    """Lists all uploaded study materials in the cloud database."""
    verify_admin(request)
    materials = db.get_materials()
    return {"materials": materials}


@app.get("/api/admin/insights")
async def get_admin_insights(request: Request):
    """Admin endpoint: computes aggregate metrics and returns recent chat logs."""
    verify_admin(request)
    insights = db.get_chat_insights()
    insights["min_score_threshold"] = MIN_SCORE
    return insights


@app.get("/api/admin/chat-logs/export")
async def export_chat_logs(request: Request):
    """Admin endpoint: exports full chat logs as a downloadable CSV."""
    verify_admin(request)
    logs = db.get_all_chat_logs()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "timestamp", "course", "level", "question",
        "answer_preview", "source", "top_score",
        "model_used", "response_time_ms"
    ])
    for row in logs:
        writer.writerow([
            row.get("timestamp"),
            row.get("course"),
            row.get("level"),
            row.get("question"),
            row.get("answer_preview"),
            row.get("source"),
            row.get("top_score"),
            row.get("model_used"),
            row.get("response_time_ms")
        ])

    csv_data = output.getvalue()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=excel_ai_chat_logs.csv"}
    )


@app.get("/api/health")
async def health_check():
    """Returns service health status and current process memory usage via psutil."""
    proc = psutil.Process(os.getpid())
    mem = proc.memory_info()
    return {
        "status": "ok",
        "cloud_vector_db": "Pinecone Serverless (AWS)",
        "ai_model": "Google Gemini 1.5 Flash (Live)",
        "reranker": reranker.model_name,
        "memory": {
            "rss_mb": round(mem.rss / 1024 / 1024, 2),
            "vms_mb": round(mem.vms / 1024 / 1024, 2),
        },
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    logger.info("Starting Excel AI", port=port, url=f"http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
