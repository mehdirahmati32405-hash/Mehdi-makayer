"""نظرسنجی‌های شهروندی با Poll واقعی تلگرام."""
from datetime import datetime, timezone

from aiogram import F, Bot, Router
from aiogram.filters import Command
from aiogram.types import Message, PollAnswer

import config
import db

router = Router()


def _ensure_tables() -> None:
    with db.get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS surveys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                options_json TEXT NOT NULL,
                telegram_poll_id TEXT UNIQUE,
                created_at TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS survey_answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                survey_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                option_ids TEXT NOT NULL,
                answered_at TEXT NOT NULL,
                UNIQUE(survey_id, user_id)
            )
            """
        )


def _parse_survey(text: str) -> tuple[str, list[str]] | None:
    parts = [p.strip() for p in text.split("|") if p.strip()]
    if len(parts) < 3:
        return None
    question = parts[0]
    options = parts[1:11]
    if len(question) < 3 or len(options) < 2:
        return None
    return question, options


def _active_survey():
    _ensure_tables()
    with db.get_conn() as conn:
        return conn.execute(
            "SELECT * FROM surveys WHERE is_active = 1 ORDER BY id DESC LIMIT 1"
        ).fetchone()


@router.message(Command("survey"))
async def create_survey(message: Message, bot: Bot) -> None:
    if message.chat.id != config.ADMIN_GROUP_ID:
        return
    raw = (message.text or "").split(maxsplit=1)
    if len(raw) < 2:
        await message.answer(
            "📊 <b>ساخت نظرسنجی</b>\n\n"
            "قالب:\n<code>/survey سوال | گزینه اول | گزینه دوم | گزینه سوم</code>\n\n"
            "حداکثر ۱۰ گزینه می‌توان ثبت کرد."
        )
        return
    parsed = _parse_survey(raw[1])
    if parsed is None:
        await message.answer("فرمت نظرسنجی صحیح نیست. حداقل یک سؤال و دو گزینه وارد کنید.")
        return
    question, options = parsed
    _ensure_tables()
    import json
    with db.get_conn() as conn:
        conn.execute("UPDATE surveys SET is_active = 0 WHERE is_active = 1")
        cur = conn.execute(
            "INSERT INTO surveys(question, options_json, created_at, is_active) VALUES (?, ?, ?, 1)",
            (question, json.dumps(options, ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
        )
        survey_id = int(cur.lastrowid)

    subscribers = db.get_subscribers()
    sent = 0
    failed = 0
    poll_id = None
    for row in subscribers:
        try:
            poll = await bot.send_poll(
                chat_id=int(row["user_id"]),
                question=question,
                options=options,
                is_anonymous=False,
                allows_multiple_answers=False,
            )
            poll_id = poll.poll.id
            sent += 1
        except Exception:
            failed += 1

    if poll_id:
        with db.get_conn() as conn:
            conn.execute("UPDATE surveys SET telegram_poll_id = ? WHERE id = ?", (poll_id, survey_id))
    await message.answer(
        f"📊 نظرسنجی فعال شد.\n"
        f"ارسال موفق: {sent}\n"
        f"ارسال ناموفق: {failed}\n"
        f"شناسه نظرسنجی: {survey_id}"
    )


@router.message(Command("survey_current"), F.chat.type == "private")
async def current_survey(message: Message, bot: Bot) -> None:
    survey = _active_survey()
    if survey is None:
        await message.answer("📊 در حال حاضر نظرسنجی فعالی وجود ندارد.")
        return
    import json
    options = json.loads(survey["options_json"])
    await bot.send_poll(
        chat_id=message.chat.id,
        question=survey["question"],
        options=options,
        is_anonymous=False,
        allows_multiple_answers=False,
    )


@router.poll_answer()
async def save_poll_answer(answer: PollAnswer) -> None:
    _ensure_tables()
    with db.get_conn() as conn:
        survey = conn.execute(
            "SELECT id FROM surveys WHERE telegram_poll_id = ? AND is_active = 1",
            (answer.poll_id,),
        ).fetchone()
        if survey is None:
            return
        conn.execute(
            """
            INSERT INTO survey_answers(survey_id, user_id, option_ids, answered_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(survey_id, user_id) DO UPDATE SET
                option_ids = excluded.option_ids,
                answered_at = excluded.answered_at
            """,
            (
                int(survey["id"]),
                int(answer.user.id),
                ",".join(str(x) for x in answer.option_ids),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
