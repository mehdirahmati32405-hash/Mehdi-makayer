import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH = "reports.db"

STATUS_RECEIVED = "دریافت شد"
STATUS_IN_PROGRESS = "در حال رسیدگی"
STATUS_DONE = "رسیدگی شد"
STATUS_REJECTED = "غیرقابل بررسی"


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                user_name TEXT,
                category TEXT NOT NULL,
                description TEXT,
                latitude REAL,
                longitude REAL,
                photo_file_id TEXT,
                status TEXT NOT NULL DEFAULT 'دریافت شد',
                admin_chat_id INTEGER,
                admin_message_id INTEGER,
                feedback TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        # مهاجرت ساده برای پایگاه‌داده‌های قدیمی‌تر که این ستون‌ها را ندارند
        existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(reports)")}
        if "feedback" not in existing_columns:
            conn.execute("ALTER TABLE reports ADD COLUMN feedback TEXT")
        if "extra_photos" not in existing_columns:
            conn.execute("ALTER TABLE reports ADD COLUMN extra_photos TEXT")
        if "voice_file_id" not in existing_columns:
            conn.execute("ALTER TABLE reports ADD COLUMN voice_file_id TEXT")


def report_code(report_id: int) -> str:
    return f"ML-{report_id:04d}"


def create_report(
    user_id: int,
    user_name: str,
    category: str,
    description: str,
    latitude: float,
    longitude: float,
    photo_file_id: str,
    extra_photos: list[str] | None = None,
    voice_file_id: str | None = None,
) -> int:
    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO reports
                (user_id, user_name, category, description, latitude, longitude,
                 photo_file_id, extra_photos, voice_file_id, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                user_name,
                category,
                description,
                latitude,
                longitude,
                photo_file_id,
                json.dumps(extra_photos) if extra_photos else None,
                voice_file_id,
                STATUS_RECEIVED,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        return cursor.lastrowid


def set_admin_message(report_id: int, chat_id: int, message_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE reports SET admin_chat_id = ?, admin_message_id = ? WHERE id = ?",
            (chat_id, message_id, report_id),
        )


def update_status(report_id: int, status: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE reports SET status = ? WHERE id = ?", (status, report_id))


def set_feedback(report_id: int, feedback: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE reports SET feedback = ? WHERE id = ?", (feedback, report_id))


def get_report(report_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        cursor = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,))
        return cursor.fetchone()


def get_reports_by_user(user_id: int, limit: int = 5) -> list[sqlite3.Row]:
    with get_conn() as conn:
        cursor = conn.execute(
            "SELECT * FROM reports WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )
        return cursor.fetchall()


def get_stats() -> dict:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM reports").fetchone()["c"]
        by_status = {
            row["status"]: row["c"]
            for row in conn.execute(
                "SELECT status, COUNT(*) AS c FROM reports GROUP BY status"
            )
        }
    return {
        "total": total,
        "received": by_status.get(STATUS_RECEIVED, 0),
        "in_progress": by_status.get(STATUS_IN_PROGRESS, 0),
        "done": by_status.get(STATUS_DONE, 0),
        "rejected": by_status.get(STATUS_REJECTED, 0),
    }
