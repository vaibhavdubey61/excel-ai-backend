import os
from typing import List, Dict, Any, Optional
import httpx
import asyncio

PINECONE_INDEX_HOST = "https://excel-ai-materials-dlalmyk.svc.aped-4627-b74a.pinecone.io"

class QuotaExhaustedError(Exception):
    """Raised when daily embedding quota is exhausted across all available API keys."""
    pass

class CloudVectorStore:
    def __init__(
        self,
        gemini_api_key: str,
        pinecone_api_key: str,
        index_host: str = PINECONE_INDEX_HOST,
        secondary_gemini_key: Optional[str] = None,
        key_pool: Optional[List[str]] = None
    ):
        if key_pool is not None:
            raw_pool = list(key_pool)
        else:
            raw_pool = [
                gemini_api_key,
                secondary_gemini_key or os.getenv("GEMINI_API_KEY_SECONDARY", ""),
                os.getenv("GEMINI_API_KEY_TERTIARY", "")
            ]
            # Also parse .env if present
            env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
            if os.path.exists(env_file):
                try:
                    with open(env_file, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line.startswith("#") and "=" in line:
                                k, v = line.split("=", 1)
                                if "GEMINI_API_KEY" in k.strip():
                                    val = v.strip().strip('"').strip("'")
                                    if val:
                                        raw_pool.append(val)
                except Exception:
                    pass

        # Deduplicate while preserving order
        seen = set()
        deduped = []
        for k in raw_pool:
            k_clean = k.strip() if k else ""
            if k_clean and len(k_clean) > 15 and k_clean not in seen:
                seen.add(k_clean)
                deduped.append(k_clean)

        self.keys = deduped
        self.key_index = 0
        self.active_key = self.keys[0] if self.keys else gemini_api_key
        self.pinecone_api_key = pinecone_api_key
        self.index_host = index_host.rstrip('/')

    def is_ready(self) -> bool:
        """Returns True if required API keys and index host are configured."""
        return bool(self.active_key and self.pinecone_api_key and self.index_host)

    def switch_to_next_key(self) -> bool:
        """Rotates to next available key in pool if current key exhausted or invalid."""
        if self.key_index + 1 < len(self.keys):
            self.key_index += 1
            self.active_key = self.keys[self.key_index]
            print(f"[CloudVectorStore]: Switched to Key #{self.key_index + 1} ({self.active_key[:14]}...)...")
            return True
        return False

    switch_to_secondary_key = switch_to_next_key

    async def get_embedding(self, text: str, task_type: str = "RETRIEVAL_QUERY") -> List[float]:
        """Generates a 768-dim vector embedding with automatic multi-key failover."""
        for attempt in range(5):
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={self.active_key}"
            payload = {
                "model": "models/gemini-embedding-001",
                "content": {
                    "parts": [{"text": text[:6000]}]
                },
                "taskType": task_type,
                "outputDimensionality": 768
            }
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    return resp.json()["embedding"]["values"]
                elif resp.status_code == 401:
                    print(f"[CloudVectorStore]: Key {self.active_key[:12]}... returned 401. Switching key...")
                    if self.switch_to_next_key():
                        continue
                    raise Exception("All configured Gemini API keys returned 401 Invalid.")
                elif resp.status_code == 429:
                    is_daily = "per day limit exceeded" in resp.text.lower() or "requestsperday" in resp.text.lower()
                    if is_daily:
                        if self.switch_to_next_key():
                            continue
                        raise QuotaExhaustedError("Daily embedding quota reached across all API keys.")
                    # Short-term minute limit
                    print(f"[get_embedding 429]: Pausing 15s for minute window...")
                    await asyncio.sleep(15)
                else:
                    raise Exception(f"Embedding error {resp.status_code}: {resp.text[:120]}")
        raise Exception("Failed to obtain embedding after retries.")

    # Alias for querying convenience
    embed_query = get_embedding

    async def embed_batch(self, texts: List[str], task_type: str = "RETRIEVAL_DOCUMENT") -> List[List[float]]:
        """Generates embeddings for a batch of texts using batchEmbedContents with 429 failover."""
        if not texts:
            return []

        all_embeddings: List[List[float]] = []
        batch_size = 25  # Safely below free tier 30,000 TPM limit

        for i in range(0, len(texts), batch_size):
            chunk_texts = texts[i:i + batch_size]
            batch_succeeded = False

            for attempt in range(8):
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:batchEmbedContents?key={self.active_key}"
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

                try:
                    async with httpx.AsyncClient(timeout=45.0) as client:
                        resp = await client.post(url, json={"requests": requests})
                        if resp.status_code == 200:
                            data = resp.json()
                            embs = [item["values"] for item in data.get("embeddings", [])]
                            if len(embs) == len(chunk_texts):
                                all_embeddings.extend(embs)
                                batch_succeeded = True
                                break
                        elif resp.status_code == 401:
                            print(f"[embed_batch]: Key {self.active_key[:12]}... returned 401. Switching key...")
                            if self.switch_to_next_key():
                                continue
                            raise Exception("All configured Gemini API keys returned 401 Invalid.")
                        elif resp.status_code == 429:
                            is_daily = "per day limit exceeded" in resp.text.lower() or "requestsperday" in resp.text.lower()
                            if is_daily:
                                if self.switch_to_next_key():
                                    print(f"[embed_batch]: Key daily quota reached. Retrying with Key #{self.key_index + 1}...")
                                    continue
                                else:
                                    raise QuotaExhaustedError("Daily embedding quota reached across all API keys.")

                            # Per-minute rate limit: parse retry delay or sleep 20s
                            wait_sec = 20
                            try:
                                for d in resp.json().get("details", []):
                                    if "retryDelay" in d:
                                        wait_sec = int(float(d["retryDelay"].rstrip("s"))) + 2
                            except Exception:
                                pass
                            print(f"[Rate limit 429 minute pause]: Pausing {wait_sec}s for minute window...")
                            await asyncio.sleep(wait_sec)
                        else:
                            print(f"[Embedding HTTP {resp.status_code}]: {resp.text[:80]}")
                            break
                except QuotaExhaustedError:
                    raise
                except Exception as e:
                    print(f"[batchEmbedContents notice]: {e}")
                    await asyncio.sleep(2)

            if not batch_succeeded:
                # Fallback to sequential get_embedding
                for t in chunk_texts:
                    emb = await self.get_embedding(t, task_type=task_type)
                    all_embeddings.append(emb)
                    await asyncio.sleep(0.20)

            # Polite 1.2s pause between batches to protect against 100 RPM limit
            await asyncio.sleep(1.2)

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

        async with httpx.AsyncClient(timeout=5.0) as client:
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
