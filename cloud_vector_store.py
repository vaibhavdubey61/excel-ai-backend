import os
from typing import List, Dict, Any, Optional
import httpx

PINECONE_INDEX_HOST = "https://excel-ai-materials-dlalmyk.svc.aped-4627-b74a.pinecone.io"

class CloudVectorStore:
    def __init__(self, gemini_api_key: str, pinecone_api_key: str, index_host: str = PINECONE_INDEX_HOST):
        self.gemini_api_key = gemini_api_key
        self.pinecone_api_key = pinecone_api_key
        self.index_host = index_host.rstrip('/')

    def is_ready(self) -> bool:
        """Returns True if required API keys and index host are configured."""
        return bool(self.gemini_api_key and self.pinecone_api_key and self.index_host)

    async def get_embedding(self, text: str, task_type: str = "RETRIEVAL_QUERY") -> List[float]:
        """Generates a 768-dim vector embedding using Google Gemini embedding model with specific taskType."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={self.gemini_api_key}"
        payload = {
            "model": "models/gemini-embedding-001",
            "content": {
                "parts": [{"text": text[:6000]}]
            },
            "taskType": task_type,
            "outputDimensionality": 768
        }
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                raise Exception(f"Embedding error {resp.status_code}: {resp.text}")
            return resp.json()["embedding"]["values"]

    # Alias for querying convenience
    embed_query = get_embedding

    async def embed_batch(self, texts: List[str], task_type: str = "RETRIEVAL_DOCUMENT") -> List[List[float]]:
        """Generates embeddings for a batch of texts using batchEmbedContents (up to 100 per API request)."""
        if not texts:
            return []

        all_embeddings: List[List[float]] = []
        batch_size = 100

        for i in range(0, len(texts), batch_size):
            chunk_texts = texts[i:i + batch_size]
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:batchEmbedContents?key={self.gemini_api_key}"
            requests = [
                {
                    "model": "models/gemini-embedding-001",
                    "content": {
                        "parts": [{"text": t[:6000]}]
                    },
                    "taskType": task_type,
                    "outputDimensionality": 768
                }
                for t in chunk_texts
            ]

            batch_succeeded = False
            try:
                async with httpx.AsyncClient(timeout=45.0) as client:
                    resp = await client.post(url, json={"requests": requests})
                    if resp.status_code == 200:
                        data = resp.json()
                        embs = [item["values"] for item in data.get("embeddings", [])]
                        if len(embs) == len(chunk_texts):
                            all_embeddings.extend(embs)
                            batch_succeeded = True
            except Exception as e:
                print(f"[batchEmbedContents notice: falling back to individual calls]: {e}")

            if not batch_succeeded:
                # Fallback to sequential get_embedding if batch request fails
                for t in chunk_texts:
                    emb = await self.get_embedding(t, task_type=task_type)
                    all_embeddings.append(emb)

        return all_embeddings

    async def upsert_chunks(self, chunks: List[Dict[str, Any]], namespace: str = "") -> Dict[str, Any]:
        """Uploads document chunks and embeddings directly to Pinecone Cloud within a namespace."""
        if not chunks:
            return {"upsertedCount": 0}

        texts = [c.get("content", "") for c in chunks]
        embeddings = await self.embed_batch(texts, task_type="RETRIEVAL_DOCUMENT")

        vectors = []
        for c, embedding in zip(chunks, embeddings):
            metadata = {
                "course": c.get("course", ""),
                "level": c.get("level", ""),
                "subject": c.get("subject", "General"),
                "doc_name": c.get("doc_name", "Study_Material"),
                "section": c.get("section", ""),
                "topic": c.get("topic", ""),
                "text": c.get("content", "")
            }
            vectors.append({
                "id": c["id"],
                "values": embedding,
                "metadata": metadata
            })

        # Upsert in batches of 50 to Pinecone
        url = f"{self.index_host}/vectors/upsert"
        headers = {
            "Api-Key": self.pinecone_api_key,
            "Content-Type": "application/json"
        }

        last_resp = {"upsertedCount": len(vectors)}
        for i in range(0, len(vectors), 50):
            batch_vectors = vectors[i:i + 50]
            payload: Dict[str, Any] = {"vectors": batch_vectors}
            if namespace:
                payload["namespace"] = namespace

            async with httpx.AsyncClient(timeout=45.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code != 200:
                    raise Exception(f"Pinecone upsert failed {resp.status_code}: {resp.text}")
                last_resp = resp.json()

        return last_resp

    async def query(
        self,
        query_text: str,
        namespace: str = "",
        top_k: int = 8,
        subject: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Queries Pinecone Cloud with optional namespace and subject filter."""
        query_vec = await self.get_embedding(query_text, task_type="RETRIEVAL_QUERY")
        url = f"{self.index_host}/query"
        headers = {
            "Api-Key": self.pinecone_api_key,
            "Content-Type": "application/json"
        }
        payload: Dict[str, Any] = {
            "vector": query_vec,
            "topK": top_k,
            "includeMetadata": True
        }
        if namespace:
            payload["namespace"] = namespace
        if subject:
            payload["filter"] = {"subject": {"$eq": subject}}

        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                raise Exception(f"Pinecone query failed {resp.status_code}: {resp.text}")
            results = resp.json().get("matches", [])
            chunks = []
            for r in results:
                meta = r.get("metadata", {})
                chunks.append({
                    "course": meta.get("course", ""),
                    "level": meta.get("level", ""),
                    "subject": meta.get("subject", ""),
                    "doc_name": meta.get("doc_name", ""),
                    "section": meta.get("section", ""),
                    "topic": meta.get("topic", ""),
                    "content": meta.get("text", ""),
                    "score": r.get("score", 0.0)
                })
            return chunks
