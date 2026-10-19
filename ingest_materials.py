import os
import sys
import re
import json
import zipfile
import io
import asyncio
from datetime import datetime
from typing import List, Dict, Any

import pypdf
from cloud_vector_store import CloudVectorStore, PINECONE_INDEX_HOST

# Load keys
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
PINECONE_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_HOST = os.getenv("PINECONE_INDEX_HOST", PINECONE_INDEX_HOST)

if os.path.exists(env_path):
    try:
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    val = v.strip().strip('"').strip("'")
                    if k.strip() == "GEMINI_API_KEY" and not GEMINI_KEY:
                        GEMINI_KEY = val
                    elif k.strip() == "PINECONE_API_KEY" and not PINECONE_KEY:
                        PINECONE_KEY = val
                    elif k.strip() == "PINECONE_INDEX_HOST" and PINECONE_HOST == PINECONE_INDEX_HOST:
                        PINECONE_HOST = val
    except Exception as e:
        print(f"[Warning reading .env]: {e}")

cloud_store = CloudVectorStore(gemini_api_key=GEMINI_KEY, pinecone_api_key=PINECONE_KEY, index_host=PINECONE_HOST)
CATALOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cloud_catalog.json")

def detect_subject(file_path: str) -> str:
    """Infers subject name from directory hierarchy or filename."""
    path_lower = file_path.lower().replace("\\", "/")
    
    # Check parent directory names
    parts = [p.strip() for p in path_lower.split("/") if p.strip()]
    for part in parts[:-1]:
        if "tax" in part or "gst" in part:
            return "CA_Inter_Taxation"
        if "law" in part or "corp" in part:
            return "CA_Inter_Corporate_Law"
        if "cost" in part or "cma" in part:
            return "CA_Inter_Costing"
        if "audit" in part:
            return "CA_Inter_Auditing"
        if "acc" in part:
            return "CA_Inter_Advanced_Accounts"
            
    # Check filename
    filename = os.path.basename(path_lower)
    if "tax" in filename or "gst" in filename:
        return "CA_Inter_Taxation"
    if "law" in filename or "company" in filename:
        return "CA_Inter_Corporate_Law"
    if "cost" in filename:
        return "CA_Inter_Costing"
    if "audit" in filename:
        return "CA_Inter_Auditing"
    if "acc" in filename:
        return "CA_Inter_Advanced_Accounts"
        
    return "General_Study_Material"

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
        chunk_size = 280
        overlap = 35
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

async def process_pdf(doc_name: str, pdf_bytes: bytes, subject: str) -> Dict[str, Any]:
    stream = io.BytesIO(pdf_bytes)
    total_pages, chunks = extract_chunks_from_pdf_stream(stream, doc_name, subject)
    
    if not chunks:
        return {"doc_name": doc_name, "pages": total_pages, "chunks": 0, "status": "skipped (no text)"}
        
    # Batch upsert to Pinecone Cloud
    batch_size = 20
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i+batch_size]
        await cloud_store.upsert_chunks(batch)
        await asyncio.sleep(0.2) # graceful pace for API
        
    return {
        "id": f"mat_{int(datetime.now().timestamp())}",
        "doc_name": doc_name,
        "subject": subject,
        "pages": total_pages,
        "chunks": len(chunks),
        "uploaded_at": datetime.now().isoformat(),
        "status": "success"
    }

async def ingest_zip_archive(zip_path: str):
    if not os.path.exists(zip_path):
        print(f"[Error]: File not found: {zip_path}")
        return

    print("=" * 65)
    print("   EXCEL AI - BATCH STUDY MATERIALS INGESTER")
    print("=" * 65)
    print(f"Reading archive: {zip_path}")
    
    with zipfile.ZipFile(zip_path, 'r') as zf:
        namelist = [n for n in zf.namelist() if n.lower().endswith(".pdf") and not n.startswith("__MACOSX")]
        
        if not namelist:
            print("[Warning]: No PDF files found inside the ZIP archive.")
            return
            
        print(f"Found {len(namelist)} PDF documents inside archive.\n")
        
        catalog = []
        if os.path.exists(CATALOG_FILE):
            try:
                with open(CATALOG_FILE, "r") as f:
                    catalog = json.load(f)
            except Exception:
                catalog = []
                
        total_chunks = 0
        success_count = 0
        
        for idx, pdf_name in enumerate(namelist, 1):
            doc_basename = os.path.basename(pdf_name)
            subject = detect_subject(pdf_name)
            print(f"[{idx}/{len(namelist)}] Ingesting '{doc_basename}' -> Subject: {subject}...")
            
            try:
                pdf_bytes = zf.read(pdf_name)
                res = await process_pdf(doc_basename, pdf_bytes, subject)
                
                if res.get("status") == "success":
                    success_count += 1
                    chunks_added = res.get("chunks", 0)
                    total_chunks += chunks_added
                    print(f"       -> Indexed {res.get('pages')} pages, {chunks_added} chunks into Pinecone Cloud [OK]")
                    catalog.insert(0, res)
                else:
                    print(f"       -> Skipped (could not extract text / image-only scan)")
            except Exception as e:
                print(f"       -> Error indexing '{doc_basename}': {e}")
                
        # Save updated catalog
        try:
            with open(CATALOG_FILE, "w") as f:
                json.dump(catalog, f, indent=2)
        except Exception as e:
            print(f"[Error saving catalog]: {e}")
            
    print("\n" + "=" * 65)
    print(f" COMPLETED BATCH INGESTION!")
    print(f" - Successfully indexed: {success_count} / {len(namelist)} PDFs")
    print(f" - Total exam chunks stored in Pinecone Cloud: {total_chunks}")
    print(f" - Vector Database: Active and live for student queries")
    print("=" * 65)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        target_zip = sys.argv[1].strip('"').strip("'")
    else:
        print("\n=======================================================")
        print("   EXCEL AI STUDY MATERIALS BATCH UPLOADER")
        print("=======================================================")
        target_zip = input("\nEnter the path to your .zip file (or drag & drop here): ").strip().strip('"').strip("'")

    if target_zip:
        asyncio.run(ingest_zip_archive(target_zip))
    else:
        print("No zip file provided. Exiting.")
