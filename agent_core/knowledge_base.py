"""Knowledge Base - Manajemen memori jangka panjang menggunakan SQLite."""

import json
import logging
import os
import sqlite3
import time
from typing import Optional

logger = logging.getLogger(__name__)


class KnowledgeBase:
    def __init__(self, db_path: str = "data/knowledge_base.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._init_db()

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS knowledge (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversation_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    message_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tool_usage_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_name TEXT NOT NULL,
                    action TEXT,
                    input_summary TEXT,
                    output_summary TEXT,
                    success INTEGER DEFAULT 1,
                    duration_ms INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_category ON knowledge(category)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_key ON knowledge(key)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_session ON conversation_summaries(session_id)")
            conn.commit()
        logger.info(f"Knowledge base diinisialisasi: {self.db_path}")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def store(self, category: str, key: str, value: str, metadata: Optional[dict] = None) -> int:
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM knowledge WHERE category = ? AND key = ?",
                (category, key)
            ).fetchone()

            if existing:
                conn.execute(
                    "UPDATE knowledge SET value = ?, metadata = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (value, meta_json, existing["id"])
                )
                conn.commit()
                logger.debug(f"Knowledge diperbarui: [{category}] {key}")
                return existing["id"]
            else:
                cursor = conn.execute(
                    "INSERT INTO knowledge (category, key, value, metadata) VALUES (?, ?, ?, ?)",
                    (category, key, value, meta_json)
                )
                conn.commit()
                logger.debug(f"Knowledge disimpan: [{category}] {key}")
                return cursor.lastrowid

    def retrieve(self, category: str, key: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM knowledge WHERE category = ? AND key = ?",
                (category, key)
            ).fetchone()
            if row:
                return self._row_to_dict(row)
        return None

    def search(self, query: str, category: Optional[str] = None, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            if category:
                rows = conn.execute(
                    "SELECT * FROM knowledge WHERE category = ? AND (key LIKE ? OR value LIKE ?) ORDER BY updated_at DESC LIMIT ?",
                    (category, f"%{query}%", f"%{query}%", limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM knowledge WHERE key LIKE ? OR value LIKE ? ORDER BY updated_at DESC LIMIT ?",
                    (f"%{query}%", f"%{query}%", limit)
                ).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def list_by_category(self, category: str, limit: int = 50) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM knowledge WHERE category = ? ORDER BY updated_at DESC LIMIT ?",
                (category, limit)
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def delete(self, category: str, key: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM knowledge WHERE category = ? AND key = ?",
                (category, key)
            )
            conn.commit()
            return cursor.rowcount > 0

    def save_conversation_summary(self, session_id: str, summary: str, message_count: int = 0):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO conversation_summaries (session_id, summary, message_count) VALUES (?, ?, ?)",
                (session_id, summary, message_count)
            )
            conn.commit()
        logger.debug(f"Ringkasan percakapan disimpan untuk sesi: {session_id}")

    def get_conversation_summaries(self, session_id: Optional[str] = None, limit: int = 10) -> list[dict]:
        with self._connect() as conn:
            if session_id:
                rows = conn.execute(
                    "SELECT * FROM conversation_summaries WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
                    (session_id, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM conversation_summaries ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            return [dict(r) for r in rows]

    def log_tool_usage(self, tool_name: str, action: str, input_summary: str,
                       output_summary: str, success: bool, duration_ms: int = 0):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO tool_usage_log (tool_name, action, input_summary, output_summary, success, duration_ms) VALUES (?, ?, ?, ?, ?, ?)",
                (tool_name, action, input_summary[:500], output_summary[:500], int(success), duration_ms)
            )
            conn.commit()

    def get_tool_usage_stats(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT tool_name, COUNT(*) as total_calls,
                       SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success_count,
                       AVG(duration_ms) as avg_duration_ms
                FROM tool_usage_log
                GROUP BY tool_name
                ORDER BY total_calls DESC
            """).fetchall()
            return [dict(r) for r in rows]

    def get_stats(self) -> dict:
        with self._connect() as conn:
            knowledge_count = conn.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0]
            categories = conn.execute("SELECT DISTINCT category FROM knowledge").fetchall()
            summary_count = conn.execute("SELECT COUNT(*) FROM conversation_summaries").fetchone()[0]
            tool_log_count = conn.execute("SELECT COUNT(*) FROM tool_usage_log").fetchone()[0]
        return {
            "knowledge_entries": knowledge_count,
            "categories": [r[0] for r in categories],
            "conversation_summaries": summary_count,
            "tool_usage_logs": tool_log_count,
        }

    def _row_to_dict(self, row) -> dict:
        d = dict(row)
        if "metadata" in d and isinstance(d["metadata"], str):
            try:
                d["metadata"] = json.loads(d["metadata"])
            except json.JSONDecodeError:
                pass
        return d
