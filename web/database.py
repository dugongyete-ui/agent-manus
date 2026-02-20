import os
import psycopg2
import psycopg2.extras
import time
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_connection():
    return psycopg2.connect(DATABASE_URL)


def init_database():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT 'New Chat',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
            content TEXT NOT NULL,
            metadata JSONB DEFAULT '{}',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tool_executions (
            id SERIAL PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            message_id INTEGER REFERENCES messages(id) ON DELETE SET NULL,
            tool_name TEXT NOT NULL,
            params JSONB DEFAULT '{}',
            result TEXT DEFAULT '',
            status TEXT DEFAULT 'running',
            duration_ms INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS webdev_projects (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            framework TEXT NOT NULL,
            directory TEXT NOT NULL,
            manager TEXT DEFAULT 'npm',
            dev_command TEXT,
            build_command TEXT,
            files JSONB DEFAULT '[]',
            dependencies JSONB DEFAULT '[]',
            metadata JSONB DEFAULT '{}',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_workspaces (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL DEFAULT 'default',
            name TEXT NOT NULL DEFAULT 'Default Workspace',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS uploaded_files (
            id SERIAL PRIMARY KEY,
            session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
            workspace_id TEXT REFERENCES user_workspaces(id) ON DELETE CASCADE,
            filename TEXT NOT NULL,
            original_name TEXT NOT NULL,
            file_type TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            metadata JSONB DEFAULT '{}',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS workspace_id TEXT REFERENCES user_workspaces(id)")
    cur.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS user_id TEXT DEFAULT 'default'")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_webdev_name ON webdev_projects(name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tool_exec_session ON tool_executions(session_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_uploaded_files_session ON uploaded_files(session_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_uploaded_files_workspace ON uploaded_files(workspace_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_workspaces_user ON user_workspaces(user_id)")
    conn.commit()
    cur.close()
    conn.close()
    logger.info("Database initialized")


def create_session(session_id: str, title: str = "New Chat") -> dict:
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "INSERT INTO sessions (id, title) VALUES (%s, %s) RETURNING *",
        (session_id, title)
    )
    row = cur.fetchone()
    session = dict(row) if row else {}
    conn.commit()
    cur.close()
    conn.close()
    return session


def get_sessions(limit: int = 50) -> list:
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT s.*, COUNT(m.id) as message_count FROM sessions s LEFT JOIN messages m ON s.id = m.session_id GROUP BY s.id ORDER BY s.updated_at DESC LIMIT %s",
        (limit,)
    )
    sessions = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return sessions


def get_session(session_id: str) -> dict | None:
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM sessions WHERE id = %s", (session_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else None


def delete_session(session_id: str) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM sessions WHERE id = %s", (session_id,))
    deleted = cur.rowcount > 0
    conn.commit()
    cur.close()
    conn.close()
    return deleted


def update_session_title(session_id: str, title: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE sessions SET title = %s, updated_at = NOW() WHERE id = %s", (title, session_id))
    conn.commit()
    cur.close()
    conn.close()


def add_message(session_id: str, role: str, content: str, metadata: dict | None = None) -> dict:
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "INSERT INTO messages (session_id, role, content, metadata) VALUES (%s, %s, %s, %s) RETURNING *",
        (session_id, role, content, json.dumps(metadata or {}))
    )
    row = cur.fetchone()
    msg = dict(row) if row else {}
    cur.execute("UPDATE sessions SET updated_at = NOW() WHERE id = %s", (session_id,))
    conn.commit()
    cur.close()
    conn.close()
    return msg


def get_messages(session_id: str, limit: int = 200) -> list:
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT * FROM messages WHERE session_id = %s ORDER BY created_at ASC LIMIT %s",
        (session_id, limit)
    )
    messages = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return messages


def build_context_string(session_id: str) -> str:
    messages = get_messages(session_id)
    if not messages:
        return ""
    parts = []
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if role == "user":
            parts.append(f"User: {content}")
        elif role == "assistant":
            parts.append(f"Assistant: {content}")
        elif role == "system":
            parts.append(f"[System]: {content}")
    return "\n".join(parts)


def log_tool_execution(session_id: str, tool_name: str, params: dict, result: str, status: str, duration_ms: int, message_id: int | None = None) -> dict:
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "INSERT INTO tool_executions (session_id, message_id, tool_name, params, result, status, duration_ms) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING *",
        (session_id, message_id, tool_name, json.dumps(params), result[:5000], status, duration_ms)
    )
    fetched = cur.fetchone()
    row = dict(fetched) if fetched else {}
    conn.commit()
    cur.close()
    conn.close()
    return row


def save_webdev_project(name: str, framework: str, directory: str, manager: str = "npm",
                        dev_command: Optional[str] = None, build_command: Optional[str] = None,
                        files: Optional[list] = None, dependencies: Optional[list] = None) -> dict:
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """INSERT INTO webdev_projects (name, framework, directory, manager, dev_command, build_command, files, dependencies)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
        (name, framework, directory, manager, dev_command, build_command,
         json.dumps(files or []), json.dumps(dependencies or []))
    )
    row = cur.fetchone()
    project = dict(row) if row else {}
    conn.commit()
    cur.close()
    conn.close()
    return project


def get_webdev_projects() -> list:
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM webdev_projects ORDER BY created_at DESC")
    projects = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return projects


def get_webdev_project(project_id: int) -> dict | None:
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM webdev_projects WHERE id = %s", (project_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else None


def get_webdev_project_by_name(name: str) -> dict | None:
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM webdev_projects WHERE name = %s ORDER BY created_at DESC LIMIT 1", (name,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else None


def delete_webdev_project(project_id: int) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM webdev_projects WHERE id = %s", (project_id,))
    deleted = cur.rowcount > 0
    conn.commit()
    cur.close()
    conn.close()
    return deleted


def get_tool_executions(session_id: str) -> list:
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT * FROM tool_executions WHERE session_id = %s ORDER BY created_at DESC LIMIT 50",
        (session_id,)
    )
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def create_workspace(workspace_id: str, user_id: str = "default", name: str = "Default Workspace") -> dict:
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "INSERT INTO user_workspaces (id, user_id, name) VALUES (%s, %s, %s) RETURNING *",
        (workspace_id, user_id, name)
    )
    row = cur.fetchone()
    workspace = dict(row) if row else {}
    conn.commit()
    cur.close()
    conn.close()
    return workspace


def get_workspaces(user_id: str = "default") -> list:
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT * FROM user_workspaces WHERE user_id = %s ORDER BY updated_at DESC",
        (user_id,)
    )
    workspaces = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return workspaces


def get_workspace(workspace_id: str) -> dict | None:
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM user_workspaces WHERE id = %s", (workspace_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else None


def delete_workspace(workspace_id: str) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM user_workspaces WHERE id = %s", (workspace_id,))
    deleted = cur.rowcount > 0
    conn.commit()
    cur.close()
    conn.close()
    return deleted


def save_uploaded_file(session_id: Optional[str], workspace_id: Optional[str], filename: str,
                       original_name: str, file_type: str, file_size: int,
                       file_path: str, metadata: Optional[dict] = None) -> dict:
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """INSERT INTO uploaded_files (session_id, workspace_id, filename, original_name, file_type, file_size, file_path, metadata)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
        (session_id, workspace_id, filename, original_name, file_type, file_size, file_path, json.dumps(metadata or {}))
    )
    row = cur.fetchone()
    file_record = dict(row) if row else {}
    conn.commit()
    cur.close()
    conn.close()
    return file_record


def get_uploaded_files(session_id: Optional[str] = None, workspace_id: Optional[str] = None) -> list:
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    conditions = []
    params = []
    if session_id:
        conditions.append("session_id = %s")
        params.append(session_id)
    if workspace_id:
        conditions.append("workspace_id = %s")
        params.append(workspace_id)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    cur.execute(f"SELECT * FROM uploaded_files{where} ORDER BY created_at DESC", params)
    files = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return files


def get_uploaded_file(file_id: int) -> dict | None:
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM uploaded_files WHERE id = %s", (file_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else None


def delete_uploaded_file(file_id: int) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM uploaded_files WHERE id = %s", (file_id,))
    deleted = cur.rowcount > 0
    conn.commit()
    cur.close()
    conn.close()
    return deleted
