"""
memory/brain_store.py — Central Unified Knowledge Brain & Persistent Storage for ALEX 6.0.

Provides robust, transactional, zero-external-dependency SQLite storage for:
  1. Session Memory (active conversation & transient context)
  2. Working Memory (multi-step task scratchpad & intermediate steps)
  3. Long-Term Memory (stable preferences, instructions, owner facts)
  4. Project Memory (isolated architecture, decisions, stack, bugs, tasks)
  5. Task Memory (multi-step task lifecycle & checkpoint recovery)
  6. Knowledge Library (document index with FTS5 lexical/BM25 full-text search)

Owner: Aditya Rajak
Salutation: Sir
Assistant: ALEX
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

BASE_DIR = Path(__file__).resolve().parent.parent
MEMORY_DIR = BASE_DIR / "memory"
DB_PATH = MEMORY_DIR / "alex_brain.db"
CONFIG_DIR = BASE_DIR / "config"

CURRENT_SCHEMA_VERSION = 1

# ── Secret Redaction Regular Expressions ─────────────────────────────────────
SECRET_PATTERNS = [
    re.compile(r"(AIza[0-9A-Za-z-_]{35})", re.IGNORECASE),
    re.compile(r"(sk-[a-zA-Z0-9]{20,})", re.IGNORECASE),
    re.compile(r"(ghp_[a-zA-Z0-9]{20,})", re.IGNORECASE),
    re.compile(r"(bearer\s+[a-zA-Z0-9_\-\.]{20,})", re.IGNORECASE),
    re.compile(r"(?i)(password|passwd|api[_-]?key|secret|token|auth)\s*[:=]\s*['\"]?([^'\"\s\r\n]{6,})['\"]?"),
    re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+ PRIVATE KEY-----"),
]


def redact_secrets(text: str) -> str:
    """Scrub sensitive credentials, passwords, and API keys before persistence."""
    if not isinstance(text, str) or not text:
        return text

    sanitized = text
    # Replace full private key blocks
    sanitized = re.sub(
        r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+ PRIVATE KEY-----",
        "[REDACTED_PRIVATE_KEY]",
        sanitized
    )
    # Replace common API keys
    sanitized = re.sub(r"AIza[0-9A-Za-z-_]{35}", "[REDACTED_API_KEY]", sanitized)
    sanitized = re.sub(r"sk-[a-zA-Z0-9]{20,}", "[REDACTED_API_KEY]", sanitized)
    sanitized = re.sub(r"ghp_[a-zA-Z0-9]{20,}", "[REDACTED_GITHUB_TOKEN]", sanitized)

    # Replace key-value passwords/secrets
    def _repl_kv(match):
        prefix = match.group(1)
        return f"{prefix}: [REDACTED_CREDENTIAL]"

    sanitized = re.sub(
        r"(?i)(password|passwd|api[_-]?key|secret|token|auth)\s*[:=]\s*['\"]?([^'\"\s\r\n]{6,})['\"]?",
        _repl_kv,
        sanitized
    )
    return sanitized


@dataclass
class MemoryRecord:
    id: str
    memory_type: str        # session, working, long_term, project, task, knowledge
    category: str           # preferences, identity, architecture, decisions, notes, etc.
    key: Optional[str]
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    source: str = "conversation"
    confidence: float = 1.0
    project_id: Optional[str] = None
    sensitivity: str = "normal"   # normal, sensitive, restricted
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    review_date: Optional[str] = None
    status: str = "active"        # active, archived, superseded


@dataclass
class DocumentChunk:
    chunk_id: str
    doc_id: str
    chunk_index: int
    title: str
    content: str
    token_estimate: int
    metadata: Dict[str, Any] = field(default_factory=dict)


class BrainStore:
    """Central SQLite database engine managing ALEX's 6-layer memory and knowledge brain."""

    _instance: Optional[BrainStore] = None
    _lock = threading.RLock()

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_database()

    @classmethod
    def get_instance(cls, db_path: Optional[Path] = None) -> BrainStore:
        with cls._lock:
            if cls._instance is None:
                cls._instance = BrainStore(db_path)
            return cls._instance

    def _get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=30.0,
                check_same_thread=False
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            self._local.conn = conn
        return self._local.conn

    def close(self) -> None:
        """Closes the thread-local database connection and releases file handles."""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            try:
                self._local.conn.close()
            except Exception:
                pass
            self._local.conn = None

    # ── Database Initialization & Migrations ──────────────────────────────────

    def _init_database(self) -> None:
        with self._lock:
            try:
                conn = self._get_connection()
                with conn:
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS schema_migrations (
                            version INTEGER PRIMARY KEY,
                            applied_at TEXT NOT NULL,
                            description TEXT NOT NULL
                        );
                    """)

                    # Check current version
                    cur = conn.execute("SELECT MAX(version) FROM schema_migrations;")
                    row = cur.fetchone()
                    current_ver = row[0] if row and row[0] is not None else 0

                    if current_ver < 1:
                        self._apply_migration_v1(conn)
            except Exception:
                self.close()
                raise

    def _apply_migration_v1(self, conn: sqlite3.Connection) -> None:
        """Initial Full 6-Layer Schema with FTS5 search engines."""
        # 1. Memories Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                memory_type TEXT NOT NULL,
                category TEXT NOT NULL,
                key TEXT,
                content TEXT NOT NULL,
                metadata TEXT,
                source TEXT DEFAULT 'conversation',
                confidence REAL DEFAULT 1.0,
                project_id TEXT,
                sensitivity TEXT DEFAULT 'normal',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                review_date TEXT,
                status TEXT DEFAULT 'active'
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_type ON memories(memory_type);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_cat ON memories(category);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_proj ON memories(project_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_key ON memories(key);")

        # FTS5 for Memories
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                id UNINDEXED,
                content,
                key,
                category,
                project_id
            );
        """)

        # 2. Projects Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                path TEXT NOT NULL,
                tech_stack TEXT,
                architecture TEXT,
                requirements TEXT,
                completed_features TEXT,
                known_bugs TEXT,
                pending_tasks TEXT,
                test_status TEXT,
                decisions TEXT,
                status TEXT DEFAULT 'Active',
                last_verified TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)

        # 3. Tasks Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                goal TEXT NOT NULL,
                project_id TEXT,
                context TEXT,
                plan TEXT,
                completed_steps TEXT,
                current_step INTEGER DEFAULT 0,
                total_steps INTEGER DEFAULT 0,
                status TEXT DEFAULT 'QUEUED',
                files_modified TEXT,
                tests_performed TEXT,
                failures TEXT,
                recovery_instructions TEXT,
                can_resume INTEGER DEFAULT 1,
                permissions TEXT DEFAULT 'SAFE',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_proj ON tasks(project_id);")

        # 4. Documents & Knowledge Chunks
        conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                doc_id TEXT PRIMARY KEY,
                file_path TEXT UNIQUE NOT NULL,
                file_name TEXT NOT NULL,
                file_type TEXT NOT NULL,
                file_hash TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                project_id TEXT,
                chunk_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'indexed',
                last_indexed TEXT NOT NULL,
                metadata TEXT
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_docs_path ON documents(file_path);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_docs_proj ON documents(project_id);")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS document_chunks (
                chunk_id TEXT PRIMARY KEY,
                doc_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                title TEXT,
                content TEXT NOT NULL,
                token_estimate INTEGER DEFAULT 0,
                metadata TEXT,
                FOREIGN KEY(doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc ON document_chunks(doc_id);")

        # FTS5 for Document Chunks
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                chunk_id UNINDEXED,
                doc_id UNINDEXED,
                title,
                content,
                file_name,
                project_id
            );
        """)

        # 5. Working Memory (Ephemeral Task Scratchpad)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS working_memory (
                key TEXT PRIMARY KEY,
                task_id TEXT,
                value TEXT NOT NULL,
                expires_at TEXT,
                updated_at TEXT NOT NULL
            );
        """)

        # 6. Conflicts Ledger (Memory quality & contradict resolving)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conflicts (
                conflict_id TEXT PRIMARY KEY,
                memory_id TEXT,
                key TEXT,
                old_value TEXT,
                new_value TEXT,
                reason TEXT,
                resolved INTEGER DEFAULT 0,
                resolution TEXT,
                resolved_at TEXT
            );
        """)

        # Record migration
        conn.execute("""
            INSERT INTO schema_migrations (version, applied_at, description)
            VALUES (1, ?, 'Initial full 6-layer memory, knowledge and FTS5 schema');
        """, (datetime.now().isoformat(),))

        # Perform initial sync from existing legacy JSON files if present
        self._import_legacy_json(conn)

    def _import_legacy_json(self, conn: sqlite3.Connection) -> None:
        """Migrates legacy long_term.json, projects.json, and task_center.json into SQLite seamlessly."""
        # 1. Migrate long_term.json
        legacy_lt = MEMORY_DIR / "long_term.json"
        if legacy_lt.exists():
            try:
                data = json.loads(legacy_lt.read_text(encoding="utf-8"))
                for cat, items in data.items():
                    if cat == "sessions" and isinstance(items, list):
                        for s in items:
                            s_summary = s.get("summary", "")
                            if s_summary:
                                s_id = f"mem_sess_{uuid.uuid4().hex[:8]}"
                                conn.execute("""
                                    INSERT OR IGNORE INTO memories (
                                        id, memory_type, category, key, content, metadata,
                                        source, confidence, project_id, sensitivity, created_at, updated_at
                                    ) VALUES (?, 'session', 'session_summary', 'session', ?, ?, 'session_logger', 1.0, NULL, 'normal', ?, ?)
                                """, (
                                    s_id,
                                    redact_secrets(s_summary),
                                    json.dumps({"language": s.get("language", "Hindi")}),
                                    s.get("date", datetime.now().strftime("%Y-%m-%d")),
                                    s.get("date", datetime.now().strftime("%Y-%m-%d")),
                                ))
                    elif isinstance(items, dict):
                        for k, v in items.items():
                            val = v.get("value", "") if isinstance(v, dict) else str(v)
                            # Fix: Ensure user title is Sir
                            if k == "user_title":
                                val = "Sir"
                            updated = v.get("updated", datetime.now().strftime("%Y-%m-%d")) if isinstance(v, dict) else datetime.now().strftime("%Y-%m-%d")
                            mem_id = f"mem_lt_{uuid.uuid4().hex[:8]}"
                            conn.execute("""
                                INSERT OR IGNORE INTO memories (
                                    id, memory_type, category, key, content, metadata,
                                    source, confidence, project_id, sensitivity, created_at, updated_at
                                ) VALUES (?, 'long_term', ?, ?, ?, '{}', 'legacy_import', 1.0, NULL, 'normal', ?, ?)
                            """, (mem_id, cat, k, redact_secrets(val), updated, updated))
                            conn.execute("""
                                INSERT INTO memories_fts (id, content, key, category, project_id)
                                VALUES (?, ?, ?, ?, NULL);
                            """, (mem_id, redact_secrets(val), k, cat))
            except Exception as e:
                print(f"[BrainStore] Legacy long_term.json import notice: {e}")

        # 2. Migrate projects.json
        legacy_proj = MEMORY_DIR / "projects.json"
        if legacy_proj.exists():
            try:
                p_data = json.loads(legacy_proj.read_text(encoding="utf-8"))
                projs = p_data.get("projects", {})
                for p_name, p_info in projs.items():
                    if isinstance(p_info, dict):
                        proj_id = f"proj_{uuid.uuid4().hex[:8]}"
                        conn.execute("""
                            INSERT OR IGNORE INTO projects (
                                project_id, name, path, tech_stack, architecture, requirements,
                                completed_features, known_bugs, pending_tasks, test_status,
                                decisions, status, last_verified, created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            proj_id,
                            p_name,
                            p_info.get("path", str(BASE_DIR)),
                            p_info.get("tech_stack", "Python"),
                            p_info.get("architecture", "Modular Agentic Architecture"),
                            p_info.get("requirements", "Reliable personal workstation assistant"),
                            json.dumps(p_info.get("completed_features", [])),
                            json.dumps(p_info.get("known_bugs", [])),
                            json.dumps(p_info.get("active_tasks", p_info.get("tasks", []))),
                            p_info.get("test_results", "Verified"),
                            json.dumps(p_info.get("decisions", [])),
                            p_info.get("status", "Active"),
                            p_info.get("last_activity", datetime.now().isoformat()),
                            datetime.now().isoformat(),
                            datetime.now().isoformat(),
                        ))
            except Exception as e:
                print(f"[BrainStore] Legacy projects.json import notice: {e}")

    # ── Memory CRUD Operations ───────────────────────────────────────────────

    def save_memory(
        self,
        content: str,
        category: str = "notes",
        memory_type: str = "long_term",
        key: Optional[str] = None,
        project_id: Optional[str] = None,
        source: str = "conversation",
        confidence: float = 1.0,
        sensitivity: str = "normal",
        metadata: Optional[Dict[str, Any]] = None,
        review_date: Optional[str] = None
    ) -> MemoryRecord:
        """Saves or updates a memory record with secret redaction and FTS indexing."""
        with self._lock:
            conn = self._get_connection()
            now = datetime.now().isoformat()
            clean_content = redact_secrets(content.strip())
            meta_json = json.dumps(metadata or {})

            # Enforce user title rule strictly
            if key == "user_title" and clean_content in ("Aditya Sir", "aditya sir", "Sir"):
                clean_content = "Sir"

            # Check for existing key in the same category and project
            existing = None
            if key:
                cur = conn.execute("""
                    SELECT id, content FROM memories
                    WHERE category = ? AND key = ? AND (project_id IS ? OR project_id = ?) AND status = 'active'
                """, (category, key, project_id, project_id))
                existing = cur.fetchone()

            if existing:
                mem_id = existing["id"]
                old_val = existing["content"]
                # If value is different, record in conflict/audit history
                if old_val != clean_content:
                    conflict_id = f"cnf_{uuid.uuid4().hex[:8]}"
                    conn.execute("""
                        INSERT INTO conflicts (conflict_id, memory_id, key, old_value, new_value, reason, resolved, resolution, resolved_at)
                        VALUES (?, ?, ?, ?, ?, 'Direct preference update from owner', 1, 'Updated to newer owner value', ?)
                    """, (conflict_id, mem_id, key, old_val, clean_content, now))

                with conn:
                    conn.execute("""
                        UPDATE memories
                        SET content = ?, metadata = ?, source = ?, confidence = ?,
                            sensitivity = ?, updated_at = ?, review_date = ?
                        WHERE id = ?
                    """, (clean_content, meta_json, source, confidence, sensitivity, now, review_date, mem_id))

                    # Update FTS
                    conn.execute("DELETE FROM memories_fts WHERE id = ?;", (mem_id,))
                    conn.execute("""
                        INSERT INTO memories_fts (id, content, key, category, project_id)
                        VALUES (?, ?, ?, ?, ?);
                    """, (mem_id, clean_content, key or "", category, project_id or ""))
            else:
                mem_id = f"mem_{uuid.uuid4().hex[:12]}"
                with conn:
                    conn.execute("""
                        INSERT INTO memories (
                            id, memory_type, category, key, content, metadata,
                            source, confidence, project_id, sensitivity,
                            created_at, updated_at, review_date, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
                    """, (
                        mem_id, memory_type, category, key, clean_content,
                        meta_json, source, confidence, project_id,
                        sensitivity, now, now, review_date
                    ))

                    # Insert FTS
                    conn.execute("""
                        INSERT INTO memories_fts (id, content, key, category, project_id)
                        VALUES (?, ?, ?, ?, ?);
                    """, (mem_id, clean_content, key or "", category, project_id or ""))

            return MemoryRecord(
                id=mem_id,
                memory_type=memory_type,
                category=category,
                key=key,
                content=clean_content,
                metadata=metadata or {},
                source=source,
                confidence=confidence,
                project_id=project_id,
                sensitivity=sensitivity,
                created_at=now,
                updated_at=now,
                review_date=review_date,
                status="active"
            )

    def get_memory(self, mem_id: str) -> Optional[MemoryRecord]:
        with self._lock:
            conn = self._get_connection()
            cur = conn.execute("SELECT * FROM memories WHERE id = ? AND status = 'active';", (mem_id,))
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_memory(row)

    def get_memory_by_key(self, category: str, key: str, project_id: Optional[str] = None) -> Optional[MemoryRecord]:
        with self._lock:
            conn = self._get_connection()
            cur = conn.execute("""
                SELECT * FROM memories
                WHERE category = ? AND key = ? AND (project_id IS ? OR project_id = ?) AND status = 'active'
                ORDER BY updated_at DESC LIMIT 1;
            """, (category, key, project_id, project_id))
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_memory(row)

    def delete_memory(self, mem_id: str) -> bool:
        with self._lock:
            conn = self._get_connection()
            with conn:
                conn.execute("UPDATE memories SET status = 'archived' WHERE id = ?;", (mem_id,))
                conn.execute("DELETE FROM memories_fts WHERE id = ?;", (mem_id,))
            return True

    def purge_memory(self, mem_id: str) -> bool:
        """Permanently deletes a memory from the database."""
        with self._lock:
            conn = self._get_connection()
            with conn:
                conn.execute("DELETE FROM memories WHERE id = ?;", (mem_id,))
                conn.execute("DELETE FROM memories_fts WHERE id = ?;", (mem_id,))
            return True

    def list_memories(
        self,
        memory_type: Optional[str] = None,
        category: Optional[str] = None,
        project_id: Optional[str] = None,
        limit: int = 50
    ) -> List[MemoryRecord]:
        with self._lock:
            conn = self._get_connection()
            clauses = ["status = 'active'"]
            params = []

            if memory_type:
                clauses.append("memory_type = ?")
                params.append(memory_type)
            if category:
                clauses.append("category = ?")
                params.append(category)
            if project_id:
                clauses.append("project_id = ?")
                params.append(project_id)

            where_str = " AND ".join(clauses)
            cur = conn.execute(f"SELECT * FROM memories WHERE {where_str} ORDER BY updated_at DESC LIMIT ?;", (*params, limit))
            return [self._row_to_memory(r) for r in cur.fetchall()]

    # ── Search & Retrieval ───────────────────────────────────────────────────

    def search_memories(
        self,
        query: str,
        project_id: Optional[str] = None,
        memory_type: Optional[str] = None,
        limit: int = 8
    ) -> List[Tuple[MemoryRecord, float]]:
        """Hybrid search combining FTS5 BM25 ranking and lexical filtering."""
        with self._lock:
            conn = self._get_connection()
            clean_q = query.strip()
            if not clean_q:
                # Return most recent
                records = self.list_memories(memory_type=memory_type, project_id=project_id, limit=limit)
                return [(r, 1.0) for r in records]

            # Clean query for FTS5 (remove punctuation that breaks FTS syntax)
            fts_query = re.sub(r'[^\w\s]', ' ', clean_q)
            words = [w for w in fts_query.split() if len(w) > 1]
            if not words:
                records = self.list_memories(memory_type=memory_type, project_id=project_id, limit=limit)
                return [(r, 1.0) for r in records]

            fts_match_expr = " OR ".join(f'"{w}"*' for w in words)

            sql = """
                SELECT m.*, bm25(memories_fts) AS rank
                FROM memories_fts f
                JOIN memories m ON m.id = f.id
                WHERE memories_fts MATCH ? AND m.status = 'active'
            """
            params = [fts_match_expr]

            if project_id:
                sql += " AND (m.project_id = ? OR m.project_id IS NULL)"
                params.append(project_id)
            if memory_type:
                sql += " AND m.memory_type = ?"
                params.append(memory_type)

            sql += " ORDER BY rank LIMIT ?;"
            params.append(limit)

            try:
                cur = conn.execute(sql, params)
                rows = cur.fetchall()
                results = []
                for row in rows:
                    rec = self._row_to_memory(row)
                    # bm25 returns negative score where closer to 0 is better, convert to positive score
                    score = abs(float(row["rank"])) if "rank" in row.keys() else 1.0
                    results.append((rec, score))
                if results:
                    return results
            except Exception:
                pass

            # Fallback to LIKE keyword search if FTS syntax fails
            like_clauses = " OR ".join(["content LIKE ? OR key LIKE ?"] * len(words))
            like_params = []
            for w in words:
                like_params.extend([f"%{w}%", f"%{w}%"])

            sql_fallback = f"""
                SELECT * FROM memories
                WHERE ({like_clauses}) AND status = 'active'
            """
            if project_id:
                sql_fallback += " AND (project_id = ? OR project_id IS NULL)"
                like_params.append(project_id)
            sql_fallback += " ORDER BY updated_at DESC LIMIT ?;"
            like_params.append(limit)

            cur = conn.execute(sql_fallback, like_params)
            return [(self._row_to_memory(r), 0.5) for r in cur.fetchall()]

    # ── Working Memory (Multi-step Task Scratchpad) ──────────────────────────

    def set_working_memory(self, key: str, value: Any, task_id: Optional[str] = None, ttl_seconds: int = 3600) -> None:
        with self._lock:
            conn = self._get_connection()
            val_str = json.dumps(value) if not isinstance(value, str) else value
            now = datetime.now()
            expires = datetime.fromtimestamp(now.timestamp() + ttl_seconds).isoformat()
            with conn:
                conn.execute("""
                    INSERT INTO working_memory (key, task_id, value, expires_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        task_id = excluded.task_id,
                        value = excluded.value,
                        expires_at = excluded.expires_at,
                        updated_at = excluded.updated_at;
                """, (key, task_id, val_str, expires, now.isoformat()))

    def get_working_memory(self, key: str) -> Optional[Any]:
        with self._lock:
            conn = self._get_connection()
            now = datetime.now().isoformat()
            cur = conn.execute("SELECT value, expires_at FROM working_memory WHERE key = ?;", (key,))
            row = cur.fetchone()
            if not row:
                return None
            if row["expires_at"] and row["expires_at"] < now:
                # Expired
                with conn:
                    conn.execute("DELETE FROM working_memory WHERE key = ?;", (key,))
                return None
            val = row["value"]
            try:
                return json.loads(val)
            except Exception:
                return val

    def clear_working_memory(self, task_id: Optional[str] = None) -> None:
        with self._lock:
            conn = self._get_connection()
            with conn:
                if task_id:
                    conn.execute("DELETE FROM working_memory WHERE task_id = ?;", (task_id,))
                else:
                    conn.execute("DELETE FROM working_memory;")

    # ── Project Knowledge Profiles ───────────────────────────────────────────

    def save_project_profile(self, name: str, path: str, **kwargs) -> Dict[str, Any]:
        with self._lock:
            conn = self._get_connection()
            now = datetime.now().isoformat()
            cur = conn.execute("SELECT * FROM projects WHERE name = ?;", (name,))
            existing = cur.fetchone()
            proj_id = existing["project_id"] if existing else f"proj_{uuid.uuid4().hex[:8]}"

            tech_stack = kwargs.get("tech_stack") or (existing["tech_stack"] if existing else "Python")
            architecture = kwargs.get("architecture") or (existing["architecture"] if existing else "Modular Agentic Architecture")
            requirements = kwargs.get("requirements") or (existing["requirements"] if existing else "General development")
            completed_features = json.dumps(kwargs.get("completed_features")) if "completed_features" in kwargs else (existing["completed_features"] if existing else "[]")
            known_bugs = json.dumps(kwargs.get("known_bugs")) if "known_bugs" in kwargs else (existing["known_bugs"] if existing else "[]")
            pending_tasks = json.dumps(kwargs.get("pending_tasks")) if "pending_tasks" in kwargs else (existing["pending_tasks"] if existing else "[]")
            test_status = kwargs.get("test_status") or (existing["test_status"] if existing else "Untested")
            decisions = json.dumps(kwargs.get("decisions")) if "decisions" in kwargs else (existing["decisions"] if existing else "[]")
            status = kwargs.get("status") or (existing["status"] if existing else "Active")
            last_verified = kwargs.get("last_verified", now)

            with conn:
                conn.execute("""
                    INSERT INTO projects (
                        project_id, name, path, tech_stack, architecture, requirements,
                        completed_features, known_bugs, pending_tasks, test_status,
                        decisions, status, last_verified, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        path = excluded.path,
                        tech_stack = excluded.tech_stack,
                        architecture = excluded.architecture,
                        requirements = excluded.requirements,
                        completed_features = excluded.completed_features,
                        known_bugs = excluded.known_bugs,
                        pending_tasks = excluded.pending_tasks,
                        test_status = excluded.test_status,
                        decisions = excluded.decisions,
                        status = excluded.status,
                        last_verified = excluded.last_verified,
                        updated_at = excluded.updated_at;
                """, (
                    proj_id, name, path, tech_stack, architecture, requirements,
                    completed_features, known_bugs, pending_tasks, test_status,
                    decisions, status, last_verified, now, now
                ))

            return self.get_project_profile(name) or {}

    def get_project_profile(self, name_or_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            conn = self._get_connection()
            cur = conn.execute("""
                SELECT * FROM projects WHERE name = ? OR project_id = ?;
            """, (name_or_id, name_or_id))
            row = cur.fetchone()
            if not row:
                return None
            res = dict(row)
            for k in ("completed_features", "known_bugs", "pending_tasks", "decisions"):
                if res.get(k):
                    try:
                        res[k] = json.loads(res[k])
                    except Exception:
                        pass
            return res

    def list_project_profiles(self) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._get_connection()
            cur = conn.execute("SELECT * FROM projects ORDER BY updated_at DESC;")
            out = []
            for row in cur.fetchall():
                d = dict(row)
                for k in ("completed_features", "known_bugs", "pending_tasks", "decisions"):
                    if d.get(k):
                        try:
                            d[k] = json.loads(d[k])
                        except Exception:
                            pass
                out.append(d)
            return out

    def delete_project_profile(self, name_or_id: str) -> bool:
        with self._lock:
            conn = self._get_connection()
            with conn:
                conn.execute("DELETE FROM projects WHERE name = ? OR project_id = ?;", (name_or_id, name_or_id))
            return True

    # ── Document Knowledge & Chunks ───────────────────────────────────────────

    def save_document(
        self,
        file_path: str,
        file_name: str,
        file_type: str,
        file_hash: str,
        file_size: int,
        chunks: List[Dict[str, Any]],
        project_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        with self._lock:
            conn = self._get_connection()
            now = datetime.now().isoformat()
            cur = conn.execute("SELECT doc_id FROM documents WHERE file_path = ?;", (file_path,))
            existing = cur.fetchone()
            doc_id = existing["doc_id"] if existing else f"doc_{uuid.uuid4().hex[:10]}"
            meta_json = json.dumps(metadata or {})

            with conn:
                # Upsert document
                conn.execute("""
                    INSERT INTO documents (
                        doc_id, file_path, file_name, file_type, file_hash,
                        file_size, project_id, chunk_count, status, last_indexed, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'indexed', ?, ?)
                    ON CONFLICT(file_path) DO UPDATE SET
                        file_name = excluded.file_name,
                        file_type = excluded.file_type,
                        file_hash = excluded.file_hash,
                        file_size = excluded.file_size,
                        project_id = excluded.project_id,
                        chunk_count = excluded.chunk_count,
                        status = 'indexed',
                        last_indexed = excluded.last_indexed,
                        metadata = excluded.metadata;
                """, (doc_id, file_path, file_name, file_type, file_hash, file_size, project_id, len(chunks), now, meta_json))

                # Clear old chunks and FTS
                conn.execute("DELETE FROM document_chunks WHERE doc_id = ?;", (doc_id,))
                conn.execute("DELETE FROM documents_fts WHERE doc_id = ?;", (doc_id,))

                # Insert new chunks
                for i, c in enumerate(chunks):
                    chunk_id = f"chk_{doc_id}_{i}"
                    title = c.get("title", f"{file_name} Part {i+1}")
                    content = redact_secrets(c.get("content", ""))
                    tok_est = len(content.split())
                    c_meta = json.dumps(c.get("metadata", {}))

                    conn.execute("""
                        INSERT INTO document_chunks (
                            chunk_id, doc_id, chunk_index, title, content, token_estimate, metadata
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (chunk_id, doc_id, i, title, content, tok_est, c_meta))

                    conn.execute("""
                        INSERT INTO documents_fts (
                            chunk_id, doc_id, title, content, file_name, project_id
                        ) VALUES (?, ?, ?, ?, ?, ?)
                    """, (chunk_id, doc_id, title, content, file_name, project_id or ""))

            return doc_id

    def search_documents(
        self,
        query: str,
        project_id: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._get_connection()
            clean_q = re.sub(r'[^\w\s]', ' ', query.strip())
            words = [w for w in clean_q.split() if len(w) > 1]
            if not words:
                return []

            fts_match_expr = " OR ".join(f'"{w}"*' for w in words)
            sql = """
                SELECT f.chunk_id, f.doc_id, f.title, f.content, f.file_name, f.project_id,
                       d.file_path, d.file_type, bm25(documents_fts) AS rank
                FROM documents_fts f
                JOIN documents d ON d.doc_id = f.doc_id
                WHERE documents_fts MATCH ? AND d.status = 'indexed'
            """
            params = [fts_match_expr]

            if project_id:
                sql += " AND (f.project_id = ? OR f.project_id IS NULL)"
                params.append(project_id)

            sql += " ORDER BY rank LIMIT ?;"
            params.append(limit)

            try:
                cur = conn.execute(sql, params)
                return [dict(r) for r in cur.fetchall()]
            except Exception:
                # Fallback to LIKE
                like_clauses = " OR ".join(["content LIKE ? OR title LIKE ?"] * len(words))
                like_params = []
                for w in words:
                    like_params.extend([f"%{w}%", f"%{w}%"])
                cur = conn.execute(f"""
                    SELECT c.*, d.file_path, d.file_name, d.file_type
                    FROM document_chunks c
                    JOIN documents d ON d.doc_id = c.doc_id
                    WHERE ({like_clauses}) AND d.status = 'indexed'
                    LIMIT ?;
                """, (*like_params, limit))
                return [dict(r) for r in cur.fetchall()]

    def delete_document(self, file_path_or_id: str) -> bool:
        with self._lock:
            conn = self._get_connection()
            cur = conn.execute("SELECT doc_id FROM documents WHERE file_path = ? OR doc_id = ?;", (file_path_or_id, file_path_or_id))
            row = cur.fetchone()
            if not row:
                return False
            doc_id = row["doc_id"]
            with conn:
                conn.execute("DELETE FROM documents WHERE doc_id = ?;", (doc_id,))
                conn.execute("DELETE FROM document_chunks WHERE doc_id = ?;", (doc_id,))
                conn.execute("DELETE FROM documents_fts WHERE doc_id = ?;", (doc_id,))
            return True

    def list_documents(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._get_connection()
            if project_id:
                cur = conn.execute("SELECT * FROM documents WHERE project_id = ? ORDER BY last_indexed DESC;", (project_id,))
            else:
                cur = conn.execute("SELECT * FROM documents ORDER BY last_indexed DESC;")
            return [dict(r) for r in cur.fetchall()]

    # ── Task Persistence & Continuity ─────────────────────────────────────────

    def save_task_record(self, task_data: Dict[str, Any]) -> str:
        with self._lock:
            conn = self._get_connection()
            now = datetime.now().isoformat()
            task_id = task_data.get("task_id") or f"task_{uuid.uuid4().hex[:10]}"

            with conn:
                conn.execute("""
                    INSERT INTO tasks (
                        task_id, goal, project_id, context, plan, completed_steps,
                        current_step, total_steps, status, files_modified, tests_performed,
                        failures, recovery_instructions, can_resume, permissions,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(task_id) DO UPDATE SET
                        goal = excluded.goal,
                        project_id = excluded.project_id,
                        context = excluded.context,
                        plan = excluded.plan,
                        completed_steps = excluded.completed_steps,
                        current_step = excluded.current_step,
                        total_steps = excluded.total_steps,
                        status = excluded.status,
                        files_modified = excluded.files_modified,
                        tests_performed = excluded.tests_performed,
                        failures = excluded.failures,
                        recovery_instructions = excluded.recovery_instructions,
                        can_resume = excluded.can_resume,
                        permissions = excluded.permissions,
                        updated_at = excluded.updated_at;
                """, (
                    task_id,
                    task_data.get("goal", "Autonomous Task"),
                    task_data.get("project_id"),
                    task_data.get("context", ""),
                    json.dumps(task_data.get("plan", [])),
                    json.dumps(task_data.get("completed_steps", [])),
                    task_data.get("current_step", 0),
                    task_data.get("total_steps", 0),
                    task_data.get("status", "QUEUED"),
                    json.dumps(task_data.get("files_modified", [])),
                    json.dumps(task_data.get("tests_performed", [])),
                    json.dumps(task_data.get("failures", [])),
                    task_data.get("recovery_instructions", ""),
                    1 if task_data.get("can_resume", True) else 0,
                    task_data.get("permissions", "SAFE"),
                    task_data.get("created_at", now),
                    now
                ))
            return task_id

    def get_task_record(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            conn = self._get_connection()
            cur = conn.execute("SELECT * FROM tasks WHERE task_id = ?;", (task_id,))
            row = cur.fetchone()
            if not row:
                return None
            d = dict(row)
            for k in ("plan", "completed_steps", "files_modified", "tests_performed", "failures"):
                if d.get(k):
                    try:
                        d[k] = json.loads(d[k])
                    except Exception:
                        pass
            return d

    def get_unfinished_tasks(self) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._get_connection()
            cur = conn.execute("""
                SELECT * FROM tasks
                WHERE status IN ('RUNNING', 'PAUSED', 'PLANNING', 'WAITING') AND can_resume = 1
                ORDER BY updated_at DESC;
            """)
            out = []
            for row in cur.fetchall():
                d = dict(row)
                for k in ("plan", "completed_steps", "files_modified", "tests_performed", "failures"):
                    if d.get(k):
                        try:
                            d[k] = json.loads(d[k])
                        except Exception:
                            pass
                out.append(d)
            return out

    # ── Database Backup, Restore, Export & Stats ──────────────────────────────

    def backup_database(self, destination_path: Path) -> bool:
        """Atomic SQLite online backup."""
        with self._lock:
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            source_conn = self._get_connection()
            dest_conn = sqlite3.connect(str(destination_path))
            try:
                with dest_conn:
                    source_conn.backup(dest_conn, pages=100)
                return True
            except Exception as e:
                print(f"[BrainStore] ⚠️ Backup error: {e}")
                return False
            finally:
                dest_conn.close()

    def restore_database(self, backup_path: Path) -> bool:
        """Restores database from verified SQLite backup."""
        with self._lock:
            if not backup_path.exists():
                return False
            # Verify validity of backup
            try:
                test_conn = sqlite3.connect(str(backup_path))
                test_cur = test_conn.execute("PRAGMA integrity_check;")
                status = test_cur.fetchone()[0]
                test_conn.close()
                if status != "ok":
                    return False
            except Exception:
                return False

            # Close current connection
            if hasattr(self._local, "conn") and self._local.conn is not None:
                self._local.conn.close()
                self._local.conn = None

            shutil.copy2(str(backup_path), str(self.db_path))
            self._init_database()
            return True

    def export_memories(self, export_format: str = "json") -> str:
        """Exports all memories in JSON or Markdown format."""
        with self._lock:
            mems = self.list_memories(limit=1000)
            if export_format == "json":
                return json.dumps([asdict(m) for m in mems], indent=2, ensure_ascii=False)
            elif export_format == "markdown":
                lines = ["# ALEX Knowledge Brain Export", f"Generated: {datetime.now().isoformat()}", ""]
                for m in mems:
                    lines.append(f"### [{m.category.upper()}] {m.key or m.id}")
                    lines.append(f"- **Content:** {m.content}")
                    lines.append(f"- **Type:** {m.memory_type} | **Source:** {m.source} | **Updated:** {m.updated_at}")
                    lines.append("")
                return "\n".join(lines)
            return ""

    def get_brain_stats(self) -> Dict[str, Any]:
        with self._lock:
            conn = self._get_connection()
            stats = {}
            for table in ("memories", "projects", "tasks", "documents", "document_chunks", "conflicts"):
                cur = conn.execute(f"SELECT COUNT(*) FROM {table};")
                stats[table] = cur.fetchone()[0]

            # Category breakdown
            cur = conn.execute("SELECT category, COUNT(*) FROM memories WHERE status = 'active' GROUP BY category;")
            stats["categories"] = dict(cur.fetchall())
            return stats

    # ── Internal Helpers ──────────────────────────────────────────────────────

    def _row_to_memory(self, row: sqlite3.Row) -> MemoryRecord:
        meta = {}
        if row["metadata"]:
            try:
                meta = json.loads(row["metadata"])
            except Exception:
                pass
        return MemoryRecord(
            id=row["id"],
            memory_type=row["memory_type"],
            category=row["category"],
            key=row["key"],
            content=row["content"],
            metadata=meta,
            source=row["source"],
            confidence=float(row["confidence"]) if row["confidence"] is not None else 1.0,
            project_id=row["project_id"],
            sensitivity=row["sensitivity"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            review_date=row["review_date"],
            status=row["status"]
        )


# Singleton Instance
brain_store = BrainStore.get_instance()
