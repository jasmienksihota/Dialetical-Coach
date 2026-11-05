"""SQLite storage: schema, connections and optional FTS5 index."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,                 -- 'sha256[:12]' => stable for identical bytes
    sha256 TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    author TEXT,
    date TEXT,
    edition TEXT,                        -- edition / translation, if known
    original_filename TEXT NOT NULL,     -- sanitized
    stored_name TEXT NOT NULL,           -- '<sha256><ext>' inside data/originals
    file_type TEXT NOT NULL,             -- pdf | txt | md
    kind TEXT NOT NULL DEFAULT 'primary',-- primary | secondary_notes
    approved INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,                -- ok | warning | empty
    warnings TEXT NOT NULL DEFAULT '[]', -- JSON list
    page_count INTEGER,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    char_count INTEGER NOT NULL DEFAULT 0,
    printed_page_offset INTEGER,         -- printed = physical + offset; NULL = unknown
    created_at TEXT NOT NULL,
    approved_at TEXT
);
CREATE TABLE IF NOT EXISTS document_tags (
    doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    PRIMARY KEY (doc_id, tag)
);
CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,                 -- '<doc_id>-<ordinal:04d>'
    doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    text TEXT NOT NULL,
    before_text TEXT NOT NULL DEFAULT '',
    after_text TEXT NOT NULL DEFAULT '',
    page_start INTEGER,                  -- physical PDF page (1-based)
    page_end INTEGER,
    section TEXT,                        -- Markdown heading trail
    line_start INTEGER,                  -- txt / md only (1-based)
    line_end INTEGER
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id, ordinal);
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    mode TEXT NOT NULL,                  -- chat | exercise
    provider TEXT NOT NULL,              -- demo | live
    scope TEXT NOT NULL,                 -- JSON {doc_ids, tags, include_secondary}
    summary TEXT NOT NULL DEFAULT '',
    exercise TEXT,                       -- JSON exercise state (exercise mode)
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,                  -- user | assistant
    text TEXT NOT NULL DEFAULT '',
    blocks TEXT,                         -- JSON list of validated display blocks
    evidence TEXT,                       -- JSON snapshots of passages supplied this turn
    report TEXT,                         -- JSON citation validation report
    provider_label TEXT,
    purpose TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, id);
CREATE TABLE IF NOT EXISTS flags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    block_index INTEGER,
    chunk_id TEXT,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
"""

FTS_DDL = (
    "CREATE VIRTUAL TABLE chunks_fts USING fts5("
    "text, chunk_id UNINDEXED, tokenize='porter unicode61')"
)


class Database:
    def __init__(self, path: Path, force_no_fts: bool = False):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fts = False
        with self.tx() as conn:
            conn.executescript(SCHEMA)
            if not force_no_fts:
                self.fts = self._ensure_fts(conn)

    @contextmanager
    def tx(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _ensure_fts(conn) -> bool:
        try:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE name='chunks_fts'"
            ).fetchone()
            if not exists:
                conn.execute(FTS_DDL)
                conn.execute(
                    "INSERT INTO chunks_fts(text, chunk_id) SELECT text, id FROM chunks"
                )
            return True
        except sqlite3.OperationalError:
            return False

    @property
    def retrieval_mode(self) -> str:
        return "sqlite-fts5" if self.fts else "lexical-fallback (no FTS5)"
