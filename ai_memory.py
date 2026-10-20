"""Persistent per-user conversation memory for the smart assistant."""

import json
from datetime import datetime, timezone

import db

MAX_MESSAGES = 8
MAX_CONTENT_CHARS = 6000


def get_history(user_id: int) -> list[dict]:
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT messages FROM ai_conversations WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            return []
        try:
            data = json.loads(row["messages"])
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)][-MAX_MESSAGES:]


def append_turn(user_id: int, question: str, answer: str) -> None:
    history = get_history(user_id)
    history.extend([
        {"role": "user", "content": question[:MAX_CONTENT_CHARS]},
        {"role": "assistant", "content": answer[:MAX_CONTENT_CHARS]},
    ])
    history = history[-MAX_MESSAGES:]
    with db.get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_conversations (
                user_id INTEGER PRIMARY KEY,
                messages TEXT NOT NULL DEFAULT '[]',
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO ai_conversations(user_id, messages, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                messages=excluded.messages,
                updated_at=excluded.updated_at
            """,
            (user_id, json.dumps(history, ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
        )


def clear(user_id: int) -> None:
    with db.get_conn() as conn:
        conn.execute("DELETE FROM ai_conversations WHERE user_id = ?", (user_id,))
