"""SQLite storage layer for codecks-cli snapshot data.

Replaces JSON-file persistence (.pm_cache.json, .pm_claims.json) with indexed
SQLite for faster queries, FTS search, and persistence across restarts.
"""

import json
import sqlite3
import threading
from datetime import UTC, datetime


class CardStore:
    """SQLite-backed card store with FTS5 search and thread-safe access.

    Usage::

        store = CardStore()                 # .pm_store.db in project root
        store = CardStore(":memory:")       # in-memory for tests
        store.upsert_cards([{...}, ...])
        results = store.query_cards(status="started", deck="gameplay")
        hits = store.search_cards("inventory system")
        store.close()
    """

    def __init__(self, db_path: str | None = None) -> None:
        if db_path is None:
            from codecks_cli.config import STORE_DB_PATH

            db_path = STORE_DB_PATH
        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        """Create tables, indexes, FTS virtual table, and triggers."""
        with self._lock:
            cur = self._conn.cursor()
            cur.executescript(
                """
                CREATE TABLE IF NOT EXISTS cards (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    status TEXT,
                    priority TEXT,
                    effort INTEGER,
                    deck_name TEXT,
                    owner_name TEXT,
                    content TEXT,
                    is_doc INTEGER DEFAULT 0,
                    created_at TEXT,
                    updated_at TEXT,
                    tags TEXT,
                    fetched_at TEXT
                );
                CREATE TABLE IF NOT EXISTS decks (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    project_id TEXT,
                    project_name TEXT
                );
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS claims (
                    card_id TEXT PRIMARY KEY,
                    agent_name TEXT,
                    claimed_at TEXT,
                    reason TEXT
                );
                CREATE TABLE IF NOT EXISTS query_cache (
                    query_hash TEXT PRIMARY KEY,
                    result_json TEXT,
                    created_at TEXT,
                    ttl_seconds INTEGER
                );

                CREATE INDEX IF NOT EXISTS idx_cards_status ON cards(status);
                CREATE INDEX IF NOT EXISTS idx_cards_deck ON cards(deck_name COLLATE NOCASE);
                CREATE INDEX IF NOT EXISTS idx_cards_owner ON cards(owner_name COLLATE NOCASE);
                CREATE INDEX IF NOT EXISTS idx_cards_priority ON cards(priority);
                CREATE INDEX IF NOT EXISTS idx_cards_updated ON cards(updated_at);
                """
            )
            # FTS5 virtual table (separate statement — executescript can't mix
            # DDL types reliably with virtual tables on older Python/SQLite).
            try:
                cur.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS cards_fts "
                    "USING fts5(title, content, content=cards, content_rowid=rowid)"
                )
            except sqlite3.OperationalError:
                pass  # FTS5 not available — degrade gracefully

            # Triggers to keep FTS in sync with cards table
            cur.executescript(
                """
                CREATE TRIGGER IF NOT EXISTS cards_ai AFTER INSERT ON cards BEGIN
                    INSERT INTO cards_fts(rowid, title, content)
                    VALUES (new.rowid, new.title, new.content);
                END;
                CREATE TRIGGER IF NOT EXISTS cards_ad AFTER DELETE ON cards BEGIN
                    INSERT INTO cards_fts(cards_fts, rowid, title, content)
                    VALUES ('delete', old.rowid, old.title, old.content);
                END;
                CREATE TRIGGER IF NOT EXISTS cards_au AFTER UPDATE ON cards BEGIN
                    INSERT INTO cards_fts(cards_fts, rowid, title, content)
                    VALUES ('delete', old.rowid, old.title, old.content);
                    INSERT INTO cards_fts(rowid, title, content)
                    VALUES (new.rowid, new.title, new.content);
                END;
                """
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # Cards
    # ------------------------------------------------------------------

    def upsert_cards(self, cards: list[dict]) -> None:
        """Bulk upsert cards using INSERT OR REPLACE."""
        if not cards:
            return
        now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = []
        for c in cards:
            tags_val = c.get("tags")
            if isinstance(tags_val, list):
                tags_str = json.dumps(tags_val)
            elif isinstance(tags_val, str):
                tags_str = tags_val
            else:
                tags_str = "[]"
            rows.append(
                (
                    c.get("id", ""),
                    c.get("title", ""),
                    c.get("status", ""),
                    c.get("priority"),
                    c.get("effort"),
                    c.get("deck") or c.get("deck_name") or "",
                    c.get("owner") or c.get("owner_name") or "",
                    c.get("content", ""),
                    1 if c.get("is_doc") or c.get("isDoc") else 0,
                    c.get("created_at") or c.get("createdAt") or "",
                    c.get("updated_at") or c.get("lastUpdatedAt") or c.get("last_updated_at") or "",
                    tags_str,
                    now_iso,
                )
            )
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO cards "
                "(id, title, status, priority, effort, deck_name, owner_name, "
                "content, is_doc, created_at, updated_at, tags, fetched_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            self._conn.commit()

    def upsert_decks(self, decks: list[dict]) -> None:
        """Bulk upsert decks using INSERT OR REPLACE."""
        if not decks:
            return
        rows = []
        for d in decks:
            rows.append(
                (
                    d.get("id", ""),
                    d.get("title") or d.get("name") or "",
                    d.get("project_id") or d.get("projectId") or "",
                    d.get("project_name") or d.get("project") or "",
                )
            )
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO decks (id, title, project_id, project_name) "
                "VALUES (?, ?, ?, ?)",
                rows,
            )
            self._conn.commit()

    def get_card(self, card_id: str) -> dict | None:
        """Single card lookup by ID."""
        with self._lock:
            row = self._conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_card(row)

    def query_cards(
        self,
        *,
        status: str | None = None,
        deck: str | None = None,
        owner: str | None = None,
        priority: str | None = None,
        search: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[dict]:
        """Filtered card query using SQL WHERE clauses."""
        clauses: list[str] = []
        params: list[object] = []

        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if deck is not None:
            clauses.append("deck_name COLLATE NOCASE = ?")
            params.append(deck)
        if owner is not None:
            clauses.append("owner_name COLLATE NOCASE = ?")
            params.append(owner)
        if priority is not None:
            clauses.append("priority = ?")
            params.append(priority)
        if search is not None:
            clauses.append("(title LIKE ? OR content LIKE ?)")
            pattern = f"%{search}%"
            params.extend([pattern, pattern])

        where = " AND ".join(clauses) if clauses else "1=1"
        sql = f"SELECT * FROM cards WHERE {where} LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_card(r) for r in rows]

    def search_cards(self, text: str, limit: int = 50) -> list[dict]:
        """FTS5 full-text search over title and content."""
        with self._lock:
            try:
                rows = self._conn.execute(
                    "SELECT c.* FROM cards c "
                    "JOIN cards_fts f ON c.rowid = f.rowid "
                    "WHERE cards_fts MATCH ? "
                    "LIMIT ?",
                    (text, limit),
                ).fetchall()
            except sqlite3.OperationalError:
                # FTS5 not available or query syntax error — fall back to LIKE
                pattern = f"%{text}%"
                rows = self._conn.execute(
                    "SELECT * FROM cards WHERE title LIKE ? OR content LIKE ? LIMIT ?",
                    (pattern, pattern, limit),
                ).fetchall()
        return [self._row_to_card(r) for r in rows]

    def all_cards(self) -> list[dict]:
        """Return all cards."""
        with self._lock:
            rows = self._conn.execute("SELECT * FROM cards").fetchall()
        return [self._row_to_card(r) for r in rows]

    def card_count(self) -> int:
        """Return total number of stored cards."""
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM cards").fetchone()
        return row[0] if row else 0

    # ------------------------------------------------------------------
    # Meta
    # ------------------------------------------------------------------

    def set_meta(self, key: str, value: str) -> None:
        """Upsert a key-value pair into the meta table."""
        now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO meta (key, value, updated_at) VALUES (?, ?, ?)",
                (key, value, now_iso),
            )
            self._conn.commit()

    def get_meta(self, key: str) -> str | None:
        """Retrieve a value from the meta table. Returns None if not found."""
        with self._lock:
            row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    # ------------------------------------------------------------------
    # Claims
    # ------------------------------------------------------------------

    def upsert_claim(self, card_id: str, agent_name: str, reason: str = "") -> None:
        """Upsert a card claim for an agent."""
        now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO claims (card_id, agent_name, claimed_at, reason) "
                "VALUES (?, ?, ?, ?)",
                (card_id, agent_name, now_iso, reason),
            )
            self._conn.commit()

    def remove_claim(self, card_id: str) -> bool:
        """Remove a card claim. Returns True if a row was deleted."""
        with self._lock:
            cur = self._conn.execute("DELETE FROM claims WHERE card_id = ?", (card_id,))
            self._conn.commit()
        return cur.rowcount > 0

    def get_claim(self, card_id: str) -> dict | None:
        """Get the claim for a card. Returns None if not claimed."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM claims WHERE card_id = ?", (card_id,)
            ).fetchone()
        if row is None:
            return None
        return {
            "card_id": row["card_id"],
            "agent_name": row["agent_name"],
            "claimed_at": row["claimed_at"],
            "reason": row["reason"],
        }

    def all_claims(self) -> dict[str, dict]:
        """Return all claims keyed by card_id."""
        with self._lock:
            rows = self._conn.execute("SELECT * FROM claims").fetchall()
        return {
            row["card_id"]: {
                "agent_name": row["agent_name"],
                "claimed_at": row["claimed_at"],
                "reason": row["reason"],
            }
            for row in rows
        }

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def clear_cards(self) -> None:
        """Delete all cards and FTS data."""
        with self._lock:
            self._conn.execute("DELETE FROM cards")
            try:
                self._conn.execute("INSERT INTO cards_fts(cards_fts) VALUES ('delete-all')")
            except sqlite3.OperationalError:
                pass  # FTS5 not available
            self._conn.commit()

    def clear_all(self) -> None:
        """Delete everything from all tables."""
        with self._lock:
            for table in ("cards", "decks", "meta", "claims", "query_cache"):
                self._conn.execute(f"DELETE FROM {table}")  # noqa: S608
            try:
                self._conn.execute("INSERT INTO cards_fts(cards_fts) VALUES ('delete-all')")
            except sqlite3.OperationalError:
                pass  # FTS5 not available
            self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_card(row: sqlite3.Row) -> dict:
        """Convert a sqlite3.Row to a card dict with proper types."""
        tags_raw = row["tags"]
        try:
            tags = json.loads(tags_raw) if tags_raw else []
        except (json.JSONDecodeError, TypeError):
            tags = []

        return {
            "id": row["id"],
            "title": row["title"],
            "status": row["status"],
            "priority": row["priority"],
            "effort": row["effort"],
            "deck_name": row["deck_name"],
            "owner_name": row["owner_name"],
            "content": row["content"],
            "is_doc": bool(row["is_doc"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "tags": tags,
            "fetched_at": row["fetched_at"],
        }
