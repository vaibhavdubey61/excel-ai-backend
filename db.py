import os
import sqlite3
from typing import List, Dict, Any, Optional

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/app.db")

def get_db_path() -> str:
    if DATABASE_URL.startswith("sqlite:///"):
        return DATABASE_URL.replace("sqlite:///", "")
    return "data/app.db"

def get_connection() -> sqlite3.Connection:
    db_path = get_db_path()
    abs_dir = os.path.dirname(os.path.abspath(db_path))
    if abs_dir:
        os.makedirs(abs_dir, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes tables and migrates existing JSON catalog if present."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS materials (
                id TEXT PRIMARY KEY,
                doc_name TEXT NOT NULL,
                subject TEXT NOT NULL,
                pages INTEGER DEFAULT 0,
                chunks INTEGER DEFAULT 0,
                uploaded_at TEXT NOT NULL,
                course TEXT DEFAULT '',
                level TEXT DEFAULT '',
                needs_ocr INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                course TEXT DEFAULT '',
                level TEXT DEFAULT '',
                question TEXT NOT NULL,
                answer_preview TEXT DEFAULT '',
                source TEXT NOT NULL,
                top_score REAL DEFAULT 0.0,
                retrieval_ok INTEGER DEFAULT 1,
                model_used TEXT DEFAULT '',
                response_time_ms INTEGER DEFAULT 0
            )
        """)

        # Migration: ensure answer_preview and response_time_ms exist if table pre-existed
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(chat_log)")
        cols = [c[1] for c in cur.fetchall()]
        if "answer_preview" not in cols:
            conn.execute("ALTER TABLE chat_log ADD COLUMN answer_preview TEXT DEFAULT ''")
        if "response_time_ms" not in cols:
            conn.execute("ALTER TABLE chat_log ADD COLUMN response_time_ms INTEGER DEFAULT 0")
        conn.commit()

    # One-time migration from cloud_catalog.json if materials table is empty
    catalog_json = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cloud_catalog.json")
    if os.path.exists(catalog_json):
        try:
            import json
            with open(catalog_json, "r", encoding="utf-8") as f:
                items = json.load(f)
            if items:
                with get_connection() as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT COUNT(*) FROM materials")
                    count = cur.fetchone()[0]
                    if count == 0:
                        for it in items:
                            cur.execute("""
                                INSERT OR IGNORE INTO materials (id, doc_name, subject, pages, chunks, uploaded_at, course, level, needs_ocr)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                it.get("id"),
                                it.get("doc_name", ""),
                                it.get("subject", "General"),
                                it.get("pages", 0),
                                it.get("chunks", 0),
                                it.get("uploaded_at", ""),
                                it.get("course", ""),
                                it.get("level", ""),
                                1 if it.get("needs_ocr") else 0
                            ))
                        conn.commit()
        except Exception as e:
            print(f"[DB Init Warning]: Could not migrate old cloud_catalog.json: {e}")

def get_materials() -> List[Dict[str, Any]]:
    """Retrieves all indexed materials ordered by upload date descending."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM materials ORDER BY uploaded_at DESC")
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

def insert_material(material: Dict[str, Any]):
    """Inserts or updates a study material record."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO materials (id, doc_name, subject, pages, chunks, uploaded_at, course, level, needs_ocr)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            material.get("id"),
            material.get("doc_name", ""),
            material.get("subject", "General"),
            material.get("pages", 0),
            material.get("chunks", 0),
            material.get("uploaded_at", ""),
            material.get("course", ""),
            material.get("level", ""),
            1 if material.get("needs_ocr") else 0
        ))
        conn.commit()

def log_chat_interaction(
    timestamp: str,
    course: str,
    level: str,
    question: str,
    answer_preview: str,
    source: str,
    top_score: Optional[float],
    retrieval_ok: bool,
    model_used: str,
    response_time_ms: int
):
    """Logs question, answer preview, and retrieval metadata for admin insights."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO chat_log (
                timestamp, course, level, question, answer_preview, source, top_score, retrieval_ok, model_used, response_time_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            timestamp,
            course,
            level,
            question[:500],
            answer_preview[:200],
            source,
            float(top_score) if top_score is not None else 0.0,
            1 if retrieval_ok else 0,
            model_used,
            int(response_time_ms)
        ))
        conn.commit()


def get_chat_insights(limit: int = 100) -> Dict[str, Any]:
    """Computes administrative stats and returns recent chat logs."""
    min_score_threshold = float(os.getenv("MIN_SCORE", "0.62"))
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM chat_log")
        total_chats = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM chat_log WHERE source = 'material'")
        material_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM chat_log WHERE source = 'general'")
        general_count = cursor.fetchone()[0]

        cursor.execute("SELECT AVG(response_time_ms) FROM chat_log WHERE response_time_ms > 0")
        avg_resp_ms = cursor.fetchone()[0] or 0.0

        cursor.execute("SELECT COUNT(*) FROM chat_log WHERE retrieval_ok = 1")
        retrieval_ok_count = cursor.fetchone()[0]

        cursor.execute("SELECT course, level, COUNT(*) FROM chat_log GROUP BY course, level")
        by_course_level: Dict[str, Dict[str, int]] = {}
        for c, l, cnt in cursor.fetchall():
            c_key = c or "Unknown"
            l_key = l or "Unknown"
            if c_key not in by_course_level:
                by_course_level[c_key] = {}
            by_course_level[c_key][l_key] = cnt

        cursor.execute("""
            SELECT id, timestamp, course, level, question, answer_preview, source, top_score, retrieval_ok, model_used, response_time_ms
            FROM chat_log
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))
        recent_rows = []
        for r in cursor.fetchall():
            row_dict = dict(r)
            row_dict["is_low_score"] = bool((row_dict.get("top_score") or 0.0) < min_score_threshold)
            recent_rows.append(row_dict)

        material_pct = round((material_count / total_chats * 100), 1) if total_chats > 0 else 0.0
        general_pct = round((general_count / total_chats * 100), 1) if total_chats > 0 else 0.0
        retrieval_success_rate = round((retrieval_ok_count / total_chats * 100), 1) if total_chats > 0 else 0.0

        return {
            "total_chats": total_chats,
            "material_count": material_count,
            "general_count": general_count,
            "material_pct": material_pct,
            "general_pct": general_pct,
            "avg_response_time_ms": round(float(avg_resp_ms), 1),
            "retrieval_success_rate": retrieval_success_rate,
            "by_course_level": by_course_level,
            "recent_chats": recent_rows,
            "min_score_threshold": min_score_threshold
        }


def get_all_chat_logs() -> List[Dict[str, Any]]:
    """Retrieves all chat logs for CSV export."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, timestamp, course, level, question, answer_preview, source, top_score, retrieval_ok, model_used, response_time_ms
            FROM chat_log
            ORDER BY id DESC
        """)
        return [dict(r) for r in cursor.fetchall()]
