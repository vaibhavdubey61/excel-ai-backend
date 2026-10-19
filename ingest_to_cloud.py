import asyncio
import os
from rag_engine import SAMPLE_KNOWLEDGE_BASE
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

async def main():
    print("Connecting to Pinecone Cloud & Google Embedding Engine...")
    store = CloudVectorStore(gemini_api_key=GEMINI_API_KEY, pinecone_api_key=PINECONE_API_KEY)
    
    chunks_to_upload = []
    for idx, sample in enumerate(SAMPLE_KNOWLEDGE_BASE):
        chunks_to_upload.append({
            "id": f"core_sample_{idx}_{sample['subject']}",
            "subject": sample["subject"],
            "doc_name": sample["doc_name"],
            "section": sample.get("section", ""),
            "content": sample["content"]
        })
    
    print(f"Uploading {len(chunks_to_upload)} knowledge chunks to Pinecone Cloud...")
    res = await store.upsert_chunks(chunks_to_upload)
    print("Upsert Response from Pinecone Cloud:", res)
    
    print("\nTesting Query against Cloud Vector Database...")
    matches = await store.query("Section 115BAC tax slabs", top_k=2)
    print(f"Query returned {len(matches)} matches from Cloud Vector DB:")
    for m in matches:
        print(f" - [{m['subject']}] Score: {m['score']:.3f} | {m['section']}")

if __name__ == "__main__":
    asyncio.run(main())
