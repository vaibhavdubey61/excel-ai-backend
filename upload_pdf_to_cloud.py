import os
import sys
import argparse
import asyncio
import re
import pypdf
from cloud_vector_store import CloudVectorStore

def load_env():
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    k, v = line.strip().split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
load_env()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")

def extract_chunks_from_pdf(pdf_path: str, subject: str = "General") -> list:
    """Reads a PDF and creates chunked items."""
    chunks = []
    doc_name = os.path.basename(pdf_path)
    reader = pypdf.PdfReader(pdf_path)
    total_pages = len(reader.pages)
    print(f"Reading '{doc_name}' ({total_pages} pages)...")

    for page_idx, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        clean_text = re.sub(r'\s+', ' ', text).strip()
        if len(clean_text) < 40:
            continue

        # Split into ~300-word blocks
        words = clean_text.split()
        chunk_size = 300
        overlap = 40
        start = 0
        chunk_id = 0
        while start < len(words):
            end = min(start + chunk_size, len(words))
            block = " ".join(words[start:end])
            safe_id = f"{doc_name}_p{page_idx+1}_c{chunk_id}".replace(" ", "_").replace(".", "_")
            chunks.append({
                "id": safe_id,
                "subject": subject,
                "doc_name": doc_name,
                "section": f"Page {page_idx+1}",
                "content": block
            })
            start += chunk_size - overlap
            chunk_id += 1

    return chunks

async def main():
    parser = argparse.ArgumentParser(description="Upload coaching study material PDFs into Pinecone Cloud.")
    parser.add_argument("pdf_path", help="Path to PDF file or folder containing PDFs")
    parser.add_argument("--subject", default="CA_Inter_Taxation", help="Subject name (e.g. CA_Inter_Corporate_Law)")
    args = parser.parse_args()

    store = CloudVectorStore(gemini_api_key=GEMINI_API_KEY, pinecone_api_key=PINECONE_API_KEY)

    pdf_files = []
    if os.path.isfile(args.pdf_path):
        pdf_files.append(args.pdf_path)
    elif os.path.isdir(args.pdf_path):
        for f in os.listdir(args.pdf_path):
            if f.lower().endswith(".pdf"):
                pdf_files.append(os.path.join(args.pdf_path, f))

    if not pdf_files:
        print("No PDF files found at the given path.")
        return

    all_chunks = []
    for p in pdf_files:
        all_chunks.extend(extract_chunks_from_pdf(p, subject=args.subject))

    print(f"Total chunks extracted: {len(all_chunks)}. Uploading to Pinecone Cloud in batches...")
    
    batch_size = 20
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i:i+batch_size]
        print(f"Uploading batch {i//batch_size + 1} / {(len(all_chunks) + batch_size - 1)//batch_size}...")
        await store.upsert_chunks(batch)

    print("\n✓ All study materials successfully indexed in Pinecone Cloud!")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python upload_pdf_to_cloud.py <path_to_pdf_or_folder> --subject <subject_name>")
    else:
        asyncio.run(main())
