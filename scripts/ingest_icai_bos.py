"""
ICAI BoS (Board of Studies) Automated Web Crawler & Knowledge Base Ingester.
Crawls official BoS portal webpages, extracts chapter PDF links from resource.cdn.icai.org,
downloads them locally, and directly indexes them into Pinecone Cloud with level-aware namespaces.
"""
import os
import re
import sys
import json
import asyncio
import argparse
from datetime import datetime
from urllib.parse import urljoin
from typing import List, Dict, Any

import httpx
import pypdf

# Adjust path to import project modules
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from cloud_vector_store import CloudVectorStore, PINECONE_INDEX_HOST
from ingest_materials import detect_subject, extract_chunks_from_pdf_stream
import db
import syllabus

# Load environment keys
env_path = os.path.join(ROOT_DIR, ".env")
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
PINECONE_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_HOST = os.getenv("PINECONE_INDEX_HOST", PINECONE_INDEX_HOST)

if os.path.exists(env_path):
    try:
        with open(env_path, "r", encoding="utf-8") as f:
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
CATALOG_FILE = os.path.join(ROOT_DIR, "cloud_catalog.json")


def crawl_bos_page(root_url: str) -> List[Dict[str, str]]:
    """Crawls a BoS syllabus root page down to individual chapter PDF URLs."""
    base_url = "https://boslive.icai.org/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    print(f"[*] Crawling BoS Root: {root_url}")
    with httpx.Client(headers=headers, follow_redirects=True, timeout=25.0) as client:
        r = client.get(root_url)
        if r.status_code != 200:
            raise Exception(f"Failed to fetch BoS page (HTTP {r.status_code})")

        links = re.findall(r'<a\s+[^>]*href=["\'](.*?)["\'][^>]*>(.*?)</a>', r.text, re.DOTALL | re.IGNORECASE)
        
        paper_modules = []
        for href, text in links:
            clean_text = re.sub(r'<[^>]+>', ' ', text).strip()
            if "sm_module.php" in href:
                paper_modules.append((clean_text, urljoin(base_url, href)))

        print(f"[*] Discovered {len(paper_modules)} Papers on page.")
        all_chapters = []

        for paper_title, p_url in paper_modules:
            print(f"    -> Scanning Paper: {paper_title[:45]}...")
            pr = client.get(p_url)
            m_links = re.findall(r'<a\s+[^>]*href=["\'](.*?)["\'][^>]*>(.*?)</a>', pr.text, re.DOTALL | re.IGNORECASE)
            
            seen_m = set()
            modules = []
            for mh, mt in m_links:
                mt_clean = re.sub(r'<[^>]+>', ' ', mt).strip()
                if "sm_chapter_details.php" in mh:
                    full_murl = urljoin(base_url, mh)
                    if full_murl not in seen_m:
                        seen_m.add(full_murl)
                        modules.append((mt_clean or "Module", full_murl))

            for mname, murl in modules:
                cr = client.get(murl)
                c_links = re.findall(r'<a\s+[^>]*href=["\'](.*?)["\'][^>]*>(.*?)</a>', cr.text, re.DOTALL | re.IGNORECASE)
                for ch_href, ch_text in c_links:
                    clean_ch = re.sub(r'<[^>]+>', ' ', ch_text).strip()
                    if ("cdn.icai.org" in ch_href or ch_href.lower().endswith(".pdf")) and not ch_href.endswith("Schedule_of_BoS_for_your_sucess.pdf"):
                        full_pdf_url = urljoin(base_url, ch_href)
                        all_chapters.append({
                            "paper": paper_title,
                            "module": mname,
                            "chapter": clean_ch or os.path.basename(full_pdf_url),
                            "pdf_url": full_pdf_url
                        })

    return all_chapters


async def ingest_chapter(chapter_info: Dict[str, str], course: str, level: str, download_dir: str) -> Dict[str, Any]:
    """Downloads a chapter PDF, extracts text, embeds, and uploads to Pinecone."""
    pdf_url = chapter_info["pdf_url"]
    doc_name = os.path.basename(pdf_url)
    chapter_title = chapter_info["chapter"]
    paper_title = chapter_info["paper"]
    
    # Infer subject name
    subject = detect_subject(f"{paper_title}/{chapter_title}/{doc_name}")
    save_folder = os.path.join(download_dir, subject)
    os.makedirs(save_folder, exist_ok=True)
    local_pdf_path = os.path.join(save_folder, doc_name)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
    }

    # 1. Download if not present
    if not os.path.exists(local_pdf_path):
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=40.0) as client:
            resp = await client.get(pdf_url)
            if resp.status_code == 200:
                with open(local_pdf_path, "wb") as f:
                    f.write(resp.content)
            else:
                raise Exception(f"HTTP {resp.status_code} downloading {pdf_url}")

    with open(local_pdf_path, "rb") as f:
        pdf_bytes = f.read()

    # 2. Extract chunks
    import io
    stream = io.BytesIO(pdf_bytes)
    total_pages, chunks = extract_chunks_from_pdf_stream(stream, doc_name, subject)

    if not chunks:
        return {
            "doc_name": doc_name,
            "chapter": chapter_title,
            "subject": subject,
            "pages": total_pages,
            "chunks": 0,
            "status": "skipped (no readable text)",
            "local_path": local_pdf_path
        }

    # 3. Upsert to Pinecone with exact level namespace
    ns = syllabus.namespace(course, level)
    batch_size = 20
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i+batch_size]
        await cloud_store.upsert_chunks(batch, namespace=ns)
        await asyncio.sleep(0.15)

    res = {
        "id": f"mat_bos_{int(datetime.now().timestamp())}_{abs(hash(doc_name))%10000}",
        "doc_name": doc_name,
        "chapter": chapter_title,
        "subject": subject,
        "course": course,
        "level": level,
        "pages": total_pages,
        "chunks": len(chunks),
        "uploaded_at": datetime.now().isoformat(),
        "status": "success",
        "local_path": local_pdf_path
    }

    # Save to SQLite database
    try:
        db.save_material(res)
    except Exception as e:
        print(f"[DB Notice]: {e}")

    return res


async def run_pipeline(url: str, course: str = "CA", level: str = "Foundation", download_only: bool = False):
    print("=" * 70)
    print("   🎓 EXCEL AI COACH - OFFICIAL ICAI BoS KNOWLEDGE HARVESTER")
    print("=" * 70)
    print(f"Target Syllabus: {course} {level}")
    print(f"BoS URL:         {url}\n")

    chapters = crawl_bos_page(url)
    print(f"\n[+] Total Official Chapter PDFs Found: {len(chapters)}")
    if not chapters:
        print("[-] No chapter PDFs found. Please verify the URL.")
        return

    download_dir = os.path.join(ROOT_DIR, "study_materials")
    os.makedirs(download_dir, exist_ok=True)

    success_count = 0
    total_chunks = 0
    total_pages = 0

    for idx, ch in enumerate(chapters, 1):
        print(f"\n[{idx}/{len(chapters)}] Processing: {ch['chapter']} ({os.path.basename(ch['pdf_url'])})")
        print(f"      Paper: {ch['paper']}")
        
        try:
            res = await ingest_chapter(ch, course=course, level=level, download_dir=download_dir)
            if res.get("status") == "success":
                success_count += 1
                chunks_added = res.get("chunks", 0)
                pages = res.get("pages", 0)
                total_chunks += chunks_added
                total_pages += pages
                print(f"      -> SUCCESS: Indexed {pages} pages ({chunks_added} vectors) into Pinecone namespace '{syllabus.namespace(course, level)}' [OK]")
            else:
                print(f"      -> {res.get('status')}")
        except Exception as err:
            print(f"      -> Error: {err}")

    print("\n" + "=" * 70)
    print(" 🎉 ICAI BoS HARVESTING COMPLETED!")
    print(f" - Successfully Processed: {success_count} / {len(chapters)} Chapters")
    print(f" - Total Exam Pages Added: {total_pages}")
    print(f" - Total Vector Embeddings: {total_chunks}")
    print(f" - Knowledge Stored In:     Pinecone Cloud ('{syllabus.namespace(course, level)}')")
    print(f" - Local PDFs Saved In:     c:\\Users\\HC\\Documents\\Excel\\study_materials\\")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Automate ICAI BoS PDF downloading and Pinecone cloud indexing.")
    parser.add_argument("--url", default="https://boslive.icai.org/study_material_new_paper_details.php?c=foundation&language=English&year=Applicable%20for%20May%202026%20Exam%20Onwards", help="ICAI BoS webpage URL")
    parser.add_argument("--course", default="CA", help="Course (CA, CS, CMA)")
    parser.add_argument("--level", default="Foundation", help="Level (Foundation, Inter, Final)")
    parser.add_argument("--download-only", action="store_true", help="Only download PDFs to study_materials without embedding")
    args = parser.parse_args()

    asyncio.run(run_pipeline(url=args.url, course=args.course, level=args.level, download_only=args.download_only))
