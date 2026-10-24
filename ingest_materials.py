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
    """Infers subject name from directory hierarchy or filename for Foundation, Inter & Final."""
    p = file_path.lower().replace(chr(92), "/")
    
    # 1. Economics
    if "economics" in p or "eco" in p:
        return "CA_Foundation_Business_Economics"
    
    # 2. Maths / Quantitative Aptitude
    if "quantitative" in p or "aptitude" in p or "maths" in p or "math" in p:
        return "CA_Foundation_Quantitative_Aptitude"
    
    # 3. Business Laws
    if "business law" in p or "businesslaws" in p or "bus.law" in p:
        return "CA_Foundation_Business_Laws"
    
    # 4. Tax / GST (Inter)
    if "tax" in p or "gst" in p:
        return "CA_Inter_Taxation"
    
    # 5. Audit (Inter)
    if "audit" in p:
        return "CA_Inter_Auditing"
    
    # 6. Costing (Inter)
    if "cost" in p or "cma" in p:
        return "CA_Inter_Costing"
    
    # 7. Corporate Law (Inter)
    if "corporate law" in p or "corp" in p or "company law" in p:
        return "CA_Inter_Corporate_Law"
    
    # 8. Accounts (Foundation vs Inter)
    if "account" in p or "acc" in p:
        if "inter" in p or "advanced" in p:
            return "CA_Inter_Advanced_Accounts"
        return "CA_Foundation_Accounting"

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

async def ingest_source(target_path: str):
    if not os.path.exists(target_path):
        print(f"[Error]: File or folder not found: {target_path}")
        return

    print("=" * 65)
    print("   EXCEL AI - BATCH STUDY MATERIALS INGESTER")
    print("=" * 65)
    print(f"Source: {target_path}")

    docs_to_process = []
    zf_ref = None

    if os.path.isdir(target_path):
        for root, dirs, files in os.walk(target_path):
            for f in files:
                if f.lower().endswith(".pdf") and not f.startswith("~$") and not f.startswith("."):
                    full_p = os.path.join(root, f)
                    def make_reader(p=full_p):
                        with open(p, "rb") as fh:
                            return fh.read()
                    docs_to_process.append((f, full_p, make_reader))
    elif zipfile.is_zipfile(target_path):
        zf_ref = zipfile.ZipFile(target_path, 'r')
        for n in zf_ref.namelist():
            if n.lower().endswith(".pdf") and not n.startswith("__MACOSX") and not os.path.basename(n).startswith("~$") and not os.path.basename(n).startswith("."):
                doc_name = os.path.basename(n)
                def make_reader(entry_name=n):
                    return zf_ref.read(entry_name)
                docs_to_process.append((doc_name, n, make_reader))
    elif target_path.lower().endswith(".pdf"):
        full_p = os.path.abspath(target_path)
        doc_name = os.path.basename(full_p)
        docs_to_process.append((doc_name, full_p, lambda: open(full_p, "rb").read()))

    if not docs_to_process:
        print("[Warning]: No PDF files found to ingest.")
        return

    print(f"Found {len(docs_to_process)} PDF documents to ingest.\n")
    
    catalog = []
    if os.path.exists(CATALOG_FILE):
        try:
            with open(CATALOG_FILE, "r") as f:
                catalog = json.load(f)
        except Exception:
            catalog = []
            
    total_chunks = 0
    success_count = 0
    
    for idx, (doc_name, ref_path, reader_fn) in enumerate(docs_to_process, 1):
        subject = detect_subject(ref_path)
        print(f"[{idx}/{len(docs_to_process)}] Ingesting '{doc_name}' -> Subject: {subject}...")
        
        try:
            pdf_bytes = reader_fn()
            res = await process_pdf(doc_name, pdf_bytes, subject)
            
            if res.get("status") == "success":
                success_count += 1
                chunks_added = res.get("chunks", 0)
                total_chunks += chunks_added
                print(f"       -> Indexed {res.get('pages')} pages, {chunks_added} chunks into Pinecone Cloud [OK]")
                catalog.insert(0, res)
            else:
                print(f"       -> Skipped (could not extract text / image-only scan)")
        except Exception as e:
            print(f"       -> Error indexing '{doc_name}': {e}")
            
    if zf_ref:
        zf_ref.close()

    # Save updated catalog
    try:
        with open(CATALOG_FILE, "w") as f:
            json.dump(catalog, f, indent=2)
    except Exception as e:
        print(f"[Error saving catalog]: {e}")
        
    print("\n" + "=" * 65)
    print(f" COMPLETED BATCH INGESTION!")
    print(f" - Successfully indexed: {success_count} / {len(docs_to_process)} PDFs")
    print(f" - Total exam chunks stored in Pinecone Cloud: {total_chunks}")
    print(f" - Vector Database: Active and live for student queries")
    print("=" * 65)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        target = sys.argv[1].strip('"').strip("'")
    elif os.path.exists("study_materials"):
        target = "study_materials"
    else:
        print("\n=======================================================")
        print("   EXCEL AI STUDY MATERIALS BATCH UPLOADER")
        print("=======================================================")
        target = input("\nEnter path to ZIP or folder (e.g. study_materials): ").strip().strip('"').strip("'")

    if target:
        asyncio.run(ingest_source(target))
    else:
        print("No target provided. Exiting.")
