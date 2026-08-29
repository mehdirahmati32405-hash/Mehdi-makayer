import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

# مسیر فایل پایگاه‌داده — اگر متغیر محیطی DB_PATH تنظیم شده باشد (مثلاً روی یک
# Volume دائمی در Railway)، از همان استفاده می‌شود؛ در غیر این صورت، همان مسیر
# قبلی (کنار خود کد) به‌عنوان پیش‌فرض به کار می‌رود.
DB_PATH = os.getenv("DB_PATH", "reports.db")

# اگر مسیر شامل یک پوشه باشد (مثل /data/reports.db) و آن پوشه هنوز وجود نداشته
# باشد، بی‌سروصدا ساخته می‌شود تا اتصال به پایگاه‌داده با خطا مواجه نشود.
_db_dir = os.path.dirname(DB_PATH)
if _db_dir:
    os.makedirs(_db_dir, exist_ok=True)

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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS quiz_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                user_name TEXT,
                score INTEGER NOT NULL,
                total INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS suggestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                user_name TEXT,
                text TEXT NOT NULL,
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
        if "last_reminded_at" not in existing_columns:
            conn.execute("ALTER TABLE reports ADD COLUMN last_reminded_at TEXT")
        if "is_anonymous" not in existing_columns:
            conn.execute("ALTER TABLE reports ADD COLUMN is_anonymous INTEGER DEFAULT 0")


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
    is_anonymous: bool = False,
) -> int:
    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO reports
                (user_id, user_name, category, description, latitude, longitude,
                 photo_file_id, extra_photos, voice_file_id, is_anonymous, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                1 if is_anonymous else 0,
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


# ---------------------------------------------------------------------------
# حالت کلی ربات (برای جلوگیری از ارسال تکراری یادآوری/گزارش دوره‌ای)
# ---------------------------------------------------------------------------

def get_state(key: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM bot_state WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None


def set_state(key: str, value: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO bot_state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


# ---------------------------------------------------------------------------
# یادآوری گزارش‌های راکد
# ---------------------------------------------------------------------------

def get_stale_reports(hours: int = 48) -> list[sqlite3.Row]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    with get_conn() as conn:
        cursor = conn.execute(
            """
            SELECT * FROM reports
            WHERE status IN (?, ?)
              AND created_at <= ?
              AND (last_reminded_at IS NULL OR last_reminded_at <= ?)
            ORDER BY id
            """,
            (STATUS_RECEIVED, STATUS_IN_PROGRESS, cutoff, cutoff),
        )
        return cursor.fetchall()


def mark_reminded(report_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE reports SET last_reminded_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), report_id),
        )


# ---------------------------------------------------------------------------
# گزارش دوره‌ای (هفتگی/ماهانه) و جدول فعال‌ترین شهروندان
# ---------------------------------------------------------------------------

def get_period_stats(days: int = 7) -> dict:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with get_conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS c FROM reports WHERE created_at >= ?", (since,)
        ).fetchone()["c"]
        done = conn.execute(
            "SELECT COUNT(*) AS c FROM reports WHERE created_at >= ? AND status = ?",
            (since, STATUS_DONE),
        ).fetchone()["c"]
        top_category_row = conn.execute(
            """
            SELECT category, COUNT(*) AS c FROM reports
            WHERE created_at >= ?
            GROUP BY category ORDER BY c DESC LIMIT 1
            """,
            (since,),
        ).fetchone()
    return {
        "total": total,
        "done": done,
        "top_category": top_category_row["category"] if top_category_row else None,
        "top_category_count": top_category_row["c"] if top_category_row else 0,
    }


def get_top_reporters(days: int = 30, limit: int = 5) -> list[sqlite3.Row]:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with get_conn() as conn:
        cursor = conn.execute(
            """
            SELECT user_name, COUNT(*) AS c FROM reports
            WHERE created_at >= ?
            GROUP BY user_id
            ORDER BY c DESC
            LIMIT ?
            """,
            (since, limit),
        )
        return cursor.fetchall()


def count_reports_by_user(user_id: int) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM reports WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row["c"]


# ---------------------------------------------------------------------------
# جست‌وجو (برای ادمین)
# ---------------------------------------------------------------------------

def search_reports(query: str, limit: int = 15) -> list[sqlite3.Row]:
    like = f"%{query}%"
    with get_conn() as conn:
        cursor = conn.execute(
            """
            SELECT * FROM reports
            WHERE category LIKE ? OR status LIKE ? OR description LIKE ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (like, like, like, limit),
        )
        return cursor.fetchall()


# ---------------------------------------------------------------------------
# کوییز شهروند نمونه
# ---------------------------------------------------------------------------

def save_quiz_result(user_id: int, user_name: str, score: int, total: int) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO quiz_scores (user_id, user_name, score, total, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, user_name, score, total, datetime.now(timezone.utc).isoformat()),
        )


def get_quiz_leaderboard(limit: int = 5) -> list[sqlite3.Row]:
    with get_conn() as conn:
        cursor = conn.execute(
            """
            SELECT user_name, MAX(score) AS best_score, total
            FROM quiz_scores
            GROUP BY user_id
            ORDER BY best_score DESC, MIN(created_at) ASC
            LIMIT ?
            """,
            (limit,),
        )
        return cursor.fetchall()


# ---------------------------------------------------------------------------
# خروجی کامل برای اکسل (ادمین)
# ---------------------------------------------------------------------------

def get_all_reports() -> list[sqlite3.Row]:
    with get_conn() as conn:
        cursor = conn.execute("SELECT * FROM reports ORDER BY id")
        return cursor.fetchall()


# ---------------------------------------------------------------------------
# صندوق پیشنهادات
# ---------------------------------------------------------------------------

def save_suggestion(user_id: int, user_name: str, text: str) -> int:
    with get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO suggestions (user_id, user_name, text, created_at) VALUES (?, ?, ?, ?)",
            (user_id, user_name, text, datetime.now(timezone.utc).isoformat()),
        )
        return cursor.lastrowid


def get_all_suggestions(limit: int = 50) -> list[sqlite3.Row]:
    with get_conn() as conn:
        cursor = conn.execute(
            "SELECT * FROM suggestions ORDER BY id DESC LIMIT ?", (limit,)
        )
        return cursor.fetchall()


# ---------------------------------------------------------------------------
# نقاط داغ (خلاصه ساده، بدون سرویس نقشه خارجی)
# ---------------------------------------------------------------------------

def get_hotspot_clusters(limit: int = 5) -> list[dict]:
    """گزارش‌های باز را بر اساس نزدیکی مکانی (تقریب ۳ رقم اعشار، حدود ۱۰۰ متر)
    خوشه‌بندی می‌کند و پرتکرارترین نقاط را برمی‌گرداند."""
    with get_conn() as conn:
        cursor = conn.execute(
            """
            SELECT latitude, longitude, category, id
            FROM reports
            WHERE status IN (?, ?)
            """,
            (STATUS_RECEIVED, STATUS_IN_PROGRESS),
        )
        rows = cursor.fetchall()

    clusters: dict[tuple, dict] = {}
    for r in rows:
        if r["latitude"] is None or r["longitude"] is None:
            continue
        key = (round(r["latitude"], 3), round(r["longitude"], 3))
        if key not in clusters:
            clusters[key] = {"latitude": key[0], "longitude": key[1], "count": 0, "report_ids": []}
        clusters[key]["count"] += 1
        clusters[key]["report_ids"].append(r["id"])

    sorted_clusters = sorted(clusters.values(), key=lambda c: c["count"], reverse=True)
    return sorted_clusters[:limit]
