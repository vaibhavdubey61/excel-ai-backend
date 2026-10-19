import os
from typing import List, Dict, Any, Optional
import httpx

PINECONE_INDEX_HOST = "https://excel-ai-materials-dlalmyk.svc.aped-4627-b74a.pinecone.io"

class CloudVectorStore:
    def __init__(self, gemini_api_key: str, pinecone_api_key: str, index_host: str = PINECONE_INDEX_HOST):
        self.gemini_api_key = gemini_api_key
        self.pinecone_api_key = pinecone_api_key
        self.index_host = index_host.rstrip('/')

    async def get_embedding(self, text: str) -> List[float]:
        """Generates a 768-dim vector embedding using Google Gemini embedding model."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={self.gemini_api_key}"
        payload = {
            "model": "models/gemini-embedding-001",
            "content": {
                "parts": [{"text": text[:2000]}]  # truncate safe length
            },
            "outputDimensionality": 768
        }
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                raise Exception(f"Embedding error {resp.status_code}: {resp.text}")
            return resp.json()["embedding"]["values"]

    async def upsert_chunks(self, chunks: List[Dict[str, Any]]):
        """Uploads document chunks and embeddings directly to Pinecone Cloud."""
        vectors = []
        for c in chunks:
            vec_id = c["id"]
            text_content = c["content"]
            metadata = {
                "subject": c.get("subject", "General"),
                "doc_name": c.get("doc_name", "Study_Material"),
                "section": c.get("section", ""),
                "text": text_content[:1000]  # Store excerpt in metadata for instant retrieval
            }
            # Generate embedding
            embedding = await self.get_embedding(text_content)
            vectors.append({
                "id": vec_id,
                "values": embedding,
                "metadata": metadata
            })

        # Upsert in batches of 50 to Pinecone
        url = f"{self.index_host}/vectors/upsert"
        headers = {
            "Api-Key": self.pinecone_api_key,
            "Content-Type": "application/json"
        }
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(url, headers=headers, json={"vectors": vectors})
            if resp.status_code != 200:
                raise Exception(f"Pinecone upsert failed: {resp.text}")
            return resp.json()

    async def query(self, query_text: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Queries Pinecone Cloud in 20-30ms to find the most relevant study material chunks."""
        query_vec = await self.get_embedding(query_text)
        url = f"{self.index_host}/query"
        headers = {
            "Api-Key": self.pinecone_api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "vector": query_vec,
            "topK": top_k,
            "includeMetadata": True
        }
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                raise Exception(f"Pinecone query failed: {resp.text}")
            results = resp.json().get("matches", [])
            chunks = []
            for r in results:
                meta = r.get("metadata", {})
                chunks.append({
                    "subject": meta.get("subject", ""),
                    "doc_name": meta.get("doc_name", ""),
                    "section": meta.get("section", ""),
                    "content": meta.get("text", ""),
                    "score": r.get("score", 0)
                })
            return chunks
