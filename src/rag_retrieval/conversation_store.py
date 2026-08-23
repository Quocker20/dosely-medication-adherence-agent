from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

MAX_EXCHANGES = 20


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017


class ConversationLimitError(Exception):
    pass


class ConversationStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    status TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_messages_conversation
                    ON messages(conversation_id, id);
                """
            )

    def create(self, title: str = "Cuộc trò chuyện mới") -> dict:
        conversation_id = str(uuid.uuid4())
        timestamp = _now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO conversations(id,title,created_at,updated_at) VALUES(?,?,?,?)",
                (conversation_id, title[:80], timestamp, timestamp),
            )
        return self.get(conversation_id)

    def list(self, limit: int = 50) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT c.*, COUNT(CASE WHEN m.role='user' THEN 1 END) AS exchange_count
                FROM conversations c LEFT JOIN messages m ON m.conversation_id=c.id
                GROUP BY c.id ORDER BY c.updated_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get(self, conversation_id: str) -> dict:
        with self._connect() as connection:
            conversation = connection.execute(
                "SELECT * FROM conversations WHERE id=?", (conversation_id,)
            ).fetchone()
            if conversation is None:
                raise KeyError(conversation_id)
            messages = connection.execute(
                "SELECT role,content,status,created_at FROM messages WHERE conversation_id=? ORDER BY id",
                (conversation_id,),
            ).fetchall()
        result = dict(conversation)
        result["messages"] = [dict(message) for message in messages]
        result["exchange_count"] = sum(message["role"] == "user" for message in messages)
        result["max_exchanges"] = MAX_EXCHANGES
        return result

    def delete(self, conversation_id: str) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM conversations WHERE id=?", (conversation_id,)
            )
            if cursor.rowcount == 0:
                raise KeyError(conversation_id)

    def append_exchange(
        self, conversation_id: str, question: str, answer: str, status: str
    ) -> dict:
        with self._lock, self._connect() as connection:
            conversation = connection.execute(
                "SELECT title FROM conversations WHERE id=?", (conversation_id,)
            ).fetchone()
            if conversation is None:
                raise KeyError(conversation_id)
            count = connection.execute(
                "SELECT COUNT(*) FROM messages WHERE conversation_id=? AND role='user'",
                (conversation_id,),
            ).fetchone()[0]
            if count >= MAX_EXCHANGES:
                raise ConversationLimitError(conversation_id)
            timestamp = _now()
            connection.executemany(
                "INSERT INTO messages(conversation_id,role,content,status,created_at) VALUES(?,?,?,?,?)",
                [
                    (conversation_id, "user", question, None, timestamp),
                    (conversation_id, "assistant", answer, status, timestamp),
                ],
            )
            title = conversation["title"]
            if count == 0 and title == "Cuộc trò chuyện mới":
                title = " ".join(question.split())[:60]
            connection.execute(
                "UPDATE conversations SET title=?,updated_at=? WHERE id=?",
                (title, timestamp, conversation_id),
            )
        return self.get(conversation_id)
