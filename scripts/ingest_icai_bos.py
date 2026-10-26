"""
ICAI BoS (Board of Studies) Comprehensive Knowledge Harvester.
Crawls official BoS portal for CA Foundation, Inter, and Final (English & Hindi),
downloads chapter PDFs into organized directories, and indexes them into
level-segregated Pinecone Cloud namespaces (ca-foundation, ca-inter, ca-final).
"""
import os
import re
import sys
import json
import asyncio
import argparse
from datetime import datetime
from urllib.parse import urljoin
from typing import List, Dict, Any, Optional

import httpx
import pypdf

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

# Preset Official ICAI BoS URLs
BOS_PRESETS = {
    "1": {
        "id": "ca-foundation-en",
        "title": "CA Foundation (English) - May 2026",
        "course": "CA",
        "level": "Foundation",
        "language": "English",
        "url": "https://boslive.icai.org/study_material_new_paper_details.php?c=foundation&language=English&year=Applicable%20for%20May%202026%20Exam%20Onwards"
    },
    "2": {
        "id": "ca-foundation-hi",
        "title": "CA Foundation (Hindi) - 2026",
        "course": "CA",
        "level": "Foundation",
        "language": "Hindi",
        "url": "https://boslive.icai.org/study_material_new_paper_details.php?c=foundation&language=Hindi&year=Applicable%20for%202026%20Exam%20Onwards"
    },
    "3": {
        "id": "ca-inter-en",
        "title": "CA Intermediate (English) - May 2026",
        "course": "CA",
        "level": "Inter",
        "language": "English",
        "url": "https://boslive.icai.org/study_material_new_paper_details.php?c=intermediate&language=English&year=Applicable%20for%20May%202026%20Examination%20Onwards"
    },
    "4": {
        "id": "ca-inter-hi",
        "title": "CA Intermediate (Hindi) - May 2026",
        "course": "CA",
        "level": "Inter",
        "language": "Hindi",
        "url": "https://boslive.icai.org/study_material_new_paper_details.php?c=intermediate&language=Hindi&year=Applicable%20for%20May%202026%20Exam%20Onwards"
    },
    "5": {
        "id": "ca-final-en",
        "title": "CA Final (English) - May 2026",
        "course": "CA",
        "level": "Final",
        "language": "English",
        "url": "https://boslive.icai.org/study_material_new_paper_details.php?c=final&language=English&year=Applicable%20for%20May%202026%20Exam%20Onwards"
    },
    "6": {
        "id": "ca-final-hi",
        "title": "CA Final (Hindi) - May 2026",
        "course": "CA",
        "level": "Final",
        "language": "Hindi",
        "url": "https://boslive.icai.org/study_material_new_paper_details.php?c=final&language=Hindi&year=Applicable%20for%20May%202026%20Exam"
    }
}



def load_catalog() -> List[Dict[str, Any]]:
    if os.path.exists(CATALOG_FILE):
        try:
            with open(CATALOG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_catalog(catalog: List[Dict[str, Any]]):
    try:
        with open(CATALOG_FILE, "w", encoding="utf-8") as f:
            json.dump(catalog, f, indent=2)
    except Exception as e:
        print(f"[Warning saving catalog]: {e}")

def update_progress_markdown(catalog: List[Dict[str, Any]]):
    md_path = os.path.join(ROOT_DIR, "INGESTION_PROGRESS.md")
    total_docs = len(catalog)
    total_pages = sum(c.get("pages", 0) for c in catalog)
    total_chunks = sum(c.get("chunks", 0) for c in catalog)
    
    # Level breakdown
    by_lvl = {}
    for c in catalog:
        lvl = c.get("level", "Foundation")
        by_lvl[lvl] = by_lvl.get(lvl, 0) + 1

    lines = [
        "# 📚 Excel AI - Study Materials Ingestion Progress",
        f"**Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "### 📊 Overall Cloud Vector DB Summary",
        f"- **Total Indexed Documents:** {total_docs}",
        f"- **Total Pages Processed:** {total_pages}",
        f"- **Total Vectors in Pinecone Cloud:** {total_chunks}",
        f"- **Cloud Index:** `excel-ai-materials`",
        f"- **Level Breakdown:** Foundation: {by_lvl.get('Foundation', 0)} | Inter: {by_lvl.get('Inter', 0)} | Final: {by_lvl.get('Final', 0)}",
        "",
        "### 📖 Indexed Materials Catalog",
        "| # | Document Name | Level | Subject | Pages | Pinecone Chunks | Status |",
        "|---|---|---|---|---|---|---|"
    ]
    for i, doc in enumerate(catalog, 1):
        lines.append(f"| {i} | {doc.get('doc_name')} | {doc.get('level', 'Foundation')} | `{doc.get('subject')}` | {doc.get('pages')} | {doc.get('chunks')} | ✅ Indexed |")
    
    try:
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except Exception as err:
        print(f"[Warning writing markdown]: {err}")

def push_git_progress():
    try:
        import subprocess
        subprocess.run(["git", "add", "INGESTION_PROGRESS.md", "cloud_catalog.json"], cwd=ROOT_DIR, check=True)
        subprocess.run(["git", "commit", "-m", "docs: update study materials ingestion progress"], cwd=ROOT_DIR, check=True)
        # Attempt push (will succeed if credentials available)
        p = subprocess.run(["git", "push"], cwd=ROOT_DIR, capture_output=True, text=True)
        if p.returncode == 0:
            print("[Git]: Progress committed and pushed to GitHub successfully!")
        else:
            print("[Git]: Progress committed locally (push deferred).")
    except Exception as e:
        print(f"[Git Notice]: {e}")

def crawl_bos_page(root_url: str) -> List[Dict[str, str]]:
    """Crawls a BoS syllabus root page down to individual chapter PDF URLs."""
    base_url = "https://boslive.icai.org/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    print(f"[*] Crawling BoS Root: {root_url}")
    with httpx.Client(headers=headers, follow_redirects=True, timeout=30.0) as client:
        r = client.get(root_url)
        if r.status_code != 200:
            raise Exception(f"Failed to fetch BoS page (HTTP {r.status_code})")

        # Discover paper links
        links = re.findall(r'<a\s+[^>]*href=["\'](sm_module\.php\?module=\d+)["\'][^>]*>(.*?)</a>', r.text, re.IGNORECASE)
        if not links:
            # Fallback regex
            links = re.findall(r'<a\s+[^>]*href=["\'](.*?)["\'][^>]*>(.*?)</a>', r.text, re.IGNORECASE)
            links = [(h, t) for h, t in links if "sm_module.php" in h]

        paper_modules = []
        for href, text in links:
            clean_text = re.sub(r'<[^>]+>', ' ', text).strip()
            paper_modules.append((clean_text, urljoin(base_url, href)))

        print(f"[*] Discovered {len(paper_modules)} Papers on page.")
        all_chapters = []

        for paper_title, p_url in paper_modules:
            print(f"    -> Scanning Paper: {paper_title[:45]}...")
            try:
                pr = client.get(p_url)
                m_links = re.findall(r'<a\s+[^>]*href=["\'](.*?)["\'][^>]*>(.*?)</a>', pr.text, re.IGNORECASE)
                
                seen_m = set()
                modules = []
                for mh, mt in m_links:
                    mt_clean = re.sub(r'<[^>]+>', ' ', mt).strip()
                    if "sm_chapter_details.php" in mh:
                        full_murl = urljoin(base_url, mh)
                        if full_murl not in seen_m:
                            seen_m.add(full_murl)
                            modules.append((mt_clean or "Module", full_murl))

                # If no sm_chapter_details found, check if direct PDFs are on module page
                if not modules:
                    for ch_href, ch_text in m_links:
                        clean_ch = re.sub(r'<[^>]+>', ' ', ch_text).strip()
                        if ("cdn.icai.org" in ch_href or ch_href.lower().endswith(".pdf")) and not ch_href.endswith("Schedule_of_BoS_for_your_sucess.pdf"):
                            all_chapters.append({
                                "paper": paper_title,
                                "module": "Main",
                                "chapter": clean_ch or os.path.basename(ch_href),
                                "pdf_url": urljoin(base_url, ch_href)
                            })

                for mname, murl in modules:
                    cr = client.get(murl)
                    c_links = re.findall(r'<a\s+[^>]*href=["\'](.*?)["\'][^>]*>(.*?)</a>', cr.text, re.IGNORECASE)
                    for ch_href, ch_text in c_links:
                        clean_ch = re.sub(r'<[^>]+>', ' ', ch_text).strip()
                        if ("cdn.icai.org" in ch_href or ch_href.lower().endswith(".pdf")) and not ch_href.endswith("Schedule_of_BoS_for_your_sucess.pdf"):
                            all_chapters.append({
                                "paper": paper_title,
                                "module": mname,
                                "chapter": clean_ch or os.path.basename(ch_href),
                                "pdf_url": urljoin(base_url, ch_href)
                            })
            except Exception as e:
                print(f"       [Warning scanning paper]: {e}")

    return all_chapters


async def ingest_chapter(chapter_info: Dict[str, str], course: str, level: str, language: str, download_dir: str) -> Dict[str, Any]:
    """Downloads a chapter PDF, extracts text, embeds, and uploads to Pinecone namespace."""
    pdf_url = chapter_info["pdf_url"]
    doc_name = os.path.basename(pdf_url)
    chapter_title = chapter_info["chapter"]
    paper_title = chapter_info["paper"]
    
    # Infer subject name
    subject = detect_subject(f"{paper_title}/{chapter_title}/{doc_name}", course=course, level=level)
    save_folder = os.path.join(download_dir, f"{course}_{level}_{language}", subject)
    os.makedirs(save_folder, exist_ok=True)
    local_pdf_path = os.path.join(save_folder, doc_name)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
    }

    # 1. Download if not present
    if not os.path.exists(local_pdf_path):
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=45.0) as client:
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
            "course": course,
            "level": level,
            "language": language,
            "pages": total_pages,
            "chunks": 0,
            "status": "skipped (no readable text)",
            "local_path": local_pdf_path
        }

    # 3. Upsert to Pinecone with exact level namespace (ca-foundation, ca-inter, ca-final)
    ns = syllabus.namespace(course, level)
    batch_size = 20
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i+batch_size]
        for c in batch:
            c["course"] = course
            c["level"] = level
            c["language"] = language
            c["chapter"] = chapter_title
        await cloud_store.upsert_chunks(batch, namespace=ns)
        await asyncio.sleep(0.15)

    res = {
        "id": f"mat_bos_{int(datetime.now().timestamp())}_{abs(hash(doc_name))%10000}",
        "doc_name": doc_name,
        "chapter": chapter_title,
        "subject": subject,
        "course": course,
        "level": level,
        "language": language,
        "pages": total_pages,
        "chunks": len(chunks),
        "uploaded_at": datetime.now().isoformat(),
        "status": "success",
        "local_path": local_pdf_path
    }

    # Save to SQLite database
    try:
        db.insert_material(res) if hasattr(db, "insert_material") else None
    except Exception as e:
        print(f"[DB Notice]: {e}")

    return res


async def run_preset(preset: Dict[str, Any], download_only: bool = False):
    course = preset["course"]
    level = preset["level"]
    language = preset["language"]
    url = preset["url"]
    title = preset["title"]
    ns = syllabus.namespace(course, level)

    print("\n" + "=" * 75)
    print(f"   🎓 EXCEL AI COACH - HARVESTING: {title}")
    print("=" * 75)
    print(f"Target Namespace: '{ns}' | Language: {language}")
    print(f"BoS URL:          {url}\n")

    chapters = crawl_bos_page(url)
    print(f"\n[+] Total Official Chapter PDFs Found: {len(chapters)}")
    if not chapters:
        print(f"[-] No chapter PDFs found for {title}.")
        return

    download_dir = os.path.join(ROOT_DIR, "study_materials")
    os.makedirs(download_dir, exist_ok=True)

    catalog = load_catalog()
    success_count = 0
    total_chunks = 0
    total_pages = 0

    for idx, ch in enumerate(chapters, 1):
        doc_filename = os.path.basename(ch['pdf_url'])
        print(f"\n[{idx}/{len(chapters)}] Ingesting: {ch['chapter']} ({doc_filename})")
        print(f"      Paper: {ch['paper']}")

        # Deduplication check against cloud_catalog
        if any(c.get("doc_name") == doc_filename and c.get("status") == "success" for c in catalog):
            print(f"      -> '{doc_filename}' is already indexed in Pinecone namespace '{ns}'. Skipping...")
            continue
        
        try:
            res = await ingest_chapter(ch, course=course, level=level, language=language, download_dir=download_dir)
            if res.get("status") == "success":
                success_count += 1
                chunks_added = res.get("chunks", 0)
                pages = res.get("pages", 0)
                total_chunks += chunks_added
                total_pages += pages
                print(f"      -> SUCCESS: {pages} pages ({chunks_added} vectors) in Pinecone namespace '{ns}' [OK]")
                
                # Update catalog and INGESTION_PROGRESS.md immediately
                catalog.insert(0, res)
                save_catalog(catalog)
                update_progress_markdown(catalog)
            else:
                print(f"      -> {res.get('status')}")
        except Exception as err:
            print(f"      -> Error: {err}")

    print("\n" + "=" * 75)
    print(f" COMPLETED {title.upper()}!")
    print(f" - Indexed: {success_count} / {len(chapters)} Chapters")
    print(f" - Total Exam Pages: {total_pages}")
    print(f" - Total Vectors:    {total_chunks} in Pinecone namespace '{ns}'")
    print("=" * 75)
    push_git_progress()


async def main():
    parser = argparse.ArgumentParser(description="Automate ICAI BoS PDF downloading and Pinecone cloud indexing.")
    parser.add_argument("--preset", choices=list(BOS_PRESETS.keys()) + ["all"], help="Preset number (1-6) or 'all'")
    parser.add_argument("--url", help="Custom ICAI BoS webpage URL")
    parser.add_argument("--course", default="CA", help="Course (CA, CS, CMA)")
    parser.add_argument("--level", default="Foundation", help="Level (Foundation, Inter, Final)")
    parser.add_argument("--language", default="English", help="Language (English, Hindi)")
    parser.add_argument("--download-only", action="store_true", help="Only download PDFs without embedding")
    args = parser.parse_args()

    if args.preset == "all":
        for k in sorted(BOS_PRESETS.keys()):
            await run_preset(BOS_PRESETS[k], download_only=args.download_only)
    elif args.preset and args.preset in BOS_PRESETS:
        await run_preset(BOS_PRESETS[args.preset], download_only=args.download_only)
    elif args.url:
        custom_preset = {
            "title": f"{args.course} {args.level} ({args.language})",
            "course": args.course,
            "level": args.level,
            "language": args.language,
            "url": args.url
        }
        await run_preset(custom_preset, download_only=args.download_only)
    else:
        print("=" * 75)
        print("   🎓 EXCEL AI COACH - OFFICIAL ICAI BoS KNOWLEDGE HARVESTER")
        print("=" * 75)
        print("Select syllabus to crawl and ingest into Pinecone Cloud:")
        for k, v in sorted(BOS_PRESETS.items()):
            print(f" [{k}] {v['title']}")
        print(" [7] Harvest ALL (Foundation + Intermediate + Final, English & Hindi)")
        print(" [8] Enter custom BoS URL")
        print("=" * 75)
        choice = input("\nEnter choice [1-8, default is 1]: ").strip() or "1"

        if choice == "7":
            for k in sorted(BOS_PRESETS.keys()):
                await run_preset(BOS_PRESETS[k], download_only=args.download_only)
        elif choice == "8":
            u = input("Paste ICAI BoS URL: ").strip()
            c = input("Course (CA/CS/CMA) [default: CA]: ").strip() or "CA"
            l = input("Level (Foundation/Inter/Final) [default: Foundation]: ").strip() or "Foundation"
            lang = input("Language (English/Hindi) [default: English]: ").strip() or "English"
            custom_preset = {
                "title": f"{c} {l} ({lang})",
                "course": c,
                "level": l,
                "language": lang,
                "url": u
            }
            await run_preset(custom_preset, download_only=args.download_only)
        elif choice in BOS_PRESETS:
            await run_preset(BOS_PRESETS[choice], download_only=args.download_only)
        else:
            print("Invalid choice. Exiting.")

if __name__ == "__main__":
    asyncio.run(main())
