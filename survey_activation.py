"""سرویس مشترک نظرسنجی شهروندی و ثبت پاسخ Poll."""
import json
import logging
from datetime import datetime, timezone

from aiogram import Bot, Router
from aiogram.types import PollAnswer

import db

router = Router()

DEFAULT_QUESTION = "میزان رضایت شما از خدمات شهری شهرداری ملایر چقدر است؟"
DEFAULT_OPTIONS = ["عالی", "خوب", "متوسط", "ضعیف"]


def _ensure_tables() -> None:
    with db.get_conn() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS surveys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            options_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS survey_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            survey_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            telegram_poll_id TEXT UNIQUE NOT NULL,
            sent_at TEXT NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS survey_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            survey_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            option_ids TEXT NOT NULL,
            answered_at TEXT NOT NULL,
            UNIQUE(survey_id, user_id)
        )""")


def get_or_create_active_survey():
    _ensure_tables()
    with db.get_conn() as conn:
        survey = conn.execute("SELECT * FROM surveys WHERE is_active = 1 ORDER BY id DESC LIMIT 1").fetchone()
        if survey is not None:
            return survey
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "INSERT INTO surveys(question, options_json, created_at, is_active) VALUES (?, ?, ?, 1)",
            (DEFAULT_QUESTION, json.dumps(DEFAULT_OPTIONS, ensure_ascii=False), now),
        )
        return conn.execute("SELECT * FROM surveys WHERE id = ?", (int(cur.lastrowid),)).fetchone()


async def send_active_survey(bot: Bot, user_id: int, force: bool = False) -> str:
    survey = get_or_create_active_survey()
    survey_id = int(survey["id"])
    if not force:
        with db.get_conn() as conn:
            delivered = conn.execute(
                "SELECT 1 FROM survey_deliveries WHERE survey_id = ? AND user_id = ? LIMIT 1",
                (survey_id, int(user_id)),
            ).fetchone()
        if delivered:
            return "already_sent"
    try:
        options = json.loads(survey["options_json"])
        poll = await bot.send_poll(
            chat_id=int(user_id),
            question=str(survey["question"]),
            options=[str(x) for x in options],
            is_anonymous=False,
            allows_multiple_answers=False,
        )
    except Exception:
        logging.exception("ارسال نظرسنجی فعال برای کاربر %s ناموفق بود.", user_id)
        return "send_failed"
    try:
        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO survey_deliveries(survey_id, user_id, telegram_poll_id, sent_at) VALUES (?, ?, ?, ?)",
                (survey_id, int(user_id), poll.poll.id, datetime.now(timezone.utc).isoformat()),
            )
    except Exception:
        logging.exception("ثبت تحویل نظرسنجی %s ناموفق بود.", survey_id)
        return "db_failed"
    return "sent"


@router.poll_answer()
async def save_poll_answer(answer: PollAnswer) -> None:
    if not answer.user:
        return
    _ensure_tables()
    with db.get_conn() as conn:
        delivery = conn.execute(
            "SELECT survey_id FROM survey_deliveries WHERE telegram_poll_id = ? LIMIT 1",
            (answer.poll_id,),
        ).fetchone()
        if delivery is None:
            return
        conn.execute(
            """INSERT INTO survey_answers(survey_id, user_id, option_ids, answered_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(survey_id, user_id) DO UPDATE SET
                   option_ids = excluded.option_ids,
                   answered_at = excluded.answered_at""",
            (int(delivery["survey_id"]), int(answer.user.id), ",".join(str(i) for i in answer.option_ids), datetime.now(timezone.utc).isoformat()),
        )
