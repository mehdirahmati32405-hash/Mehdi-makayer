"""SQLite-backed aiogram FSM storage.

Stores conversation state and FSM data in the same persistent SQLite database
as citizen reports. Each operation opens its own short-lived connection.
"""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StorageKey


class SQLiteStorage(BaseStorage):
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS fsm_storage (
                    storage_key TEXT PRIMARY KEY,
                    state TEXT,
                    data TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL
                )
                """
            )

    @contextmanager
    def _connect(self):
        """Open a short-lived connection and always commit/close it."""
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.execute("PRAGMA busy_timeout = 15000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _serialize_key(key: StorageKey) -> str:
        return json.dumps(
            [
                key.bot_id,
                key.chat_id,
                key.user_id,
                key.thread_id,
                key.business_connection_id,
                key.destiny,
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )

    async def set_state(self, key: StorageKey, state: str | State | None = None) -> None:
        state_value = state.state if isinstance(state, State) else state
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO fsm_storage (storage_key, state, data, updated_at)
                VALUES (?, ?, '{}', ?)
                ON CONFLICT(storage_key) DO UPDATE SET
                    state = excluded.state,
                    updated_at = excluded.updated_at
                """,
                (
                    self._serialize_key(key),
                    state_value,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    async def get_state(self, key: StorageKey) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT state FROM fsm_storage WHERE storage_key = ?",
                (self._serialize_key(key),),
            ).fetchone()
        return row[0] if row else None

    async def set_data(self, key: StorageKey, data: dict[str, Any]) -> None:
        encoded = json.dumps(data, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO fsm_storage (storage_key, state, data, updated_at)
                VALUES (?, NULL, ?, ?)
                ON CONFLICT(storage_key) DO UPDATE SET
                    data = excluded.data,
                    updated_at = excluded.updated_at
                """,
                (
                    self._serialize_key(key),
                    encoded,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data FROM fsm_storage WHERE storage_key = ?",
                (self._serialize_key(key),),
            ).fetchone()
        if not row or not row[0]:
            return {}
        try:
            value = json.loads(row[0])
        except (TypeError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    async def close(self) -> None:
        # Connections are scoped to individual operations and are already closed.
        return None
