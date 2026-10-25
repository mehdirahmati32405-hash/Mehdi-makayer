"""نظرسنجی‌های شهروندی با Poll واقعی تلگرام."""
import json
from datetime import datetime, timezone

from aiogram import F, Bot, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, PollAnswer

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
                created_at TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS survey_deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                survey_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                telegram_poll_id TEXT UNIQUE NOT NULL,
                sent_at TEXT NOT NULL
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


async def _send_survey_poll(bot: Bot, survey, user_id: int) -> bool:
    options = json.loads(survey["options_json"])
    try:
        poll = await bot.send_poll(
            chat_id=user_id,
            question=survey["question"],
            options=options,
            is_anonymous=False,
            allows_multiple_answers=False,
        )
    except Exception:
        return False
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO survey_deliveries(survey_id, user_id, telegram_poll_id, sent_at) VALUES (?, ?, ?, ?)",
            (int(survey["id"]), int(user_id), poll.poll.id, datetime.now(timezone.utc).isoformat()),
        )
    return True


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
    with db.get_conn() as conn:
        conn.execute("UPDATE surveys SET is_active = 0 WHERE is_active = 1")
        cur = conn.execute(
            "INSERT INTO surveys(question, options_json, created_at, is_active) VALUES (?, ?, ?, 1)",
            (question, json.dumps(options, ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
        )
        survey_id = int(cur.lastrowid)

    subscribers = db.get_all_subscribers()
    sent = 0
    failed = 0
    for row in subscribers:
        if await _send_survey_poll(bot, {"id": survey_id, "question": question, "options_json": json.dumps(options, ensure_ascii=False)}, int(row["user_id"])):
            sent += 1
        else:
            failed += 1

    await message.answer(
        f"📊 <b>نظرسنجی فعال شد.</b>\n\n"
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
    if await _send_survey_poll(bot, survey, message.from_user.id):
        await message.answer("📊 نظرسنجی فعال برای شما ارسال شد. ممنون که نظر می‌دهید. 🌹")
    else:
        await message.answer("ارسال نظرسنجی انجام نشد. لطفاً کمی بعد دوباره تلاش کنید.")


@router.callback_query(F.data == "menu:survey")
async def menu_survey(callback: CallbackQuery, bot: Bot) -> None:
    survey = _active_survey()
    if survey is None:
        await callback.answer("در حال حاضر نظرسنجی فعالی وجود ندارد.", show_alert=True)
        return
    if await _send_survey_poll(bot, survey, callback.from_user.id):
        await callback.answer("نظرسنجی برای شما ارسال شد.")
    else:
        await callback.answer("ارسال نظرسنجی ناموفق بود.", show_alert=True)


@router.poll_answer()
async def save_poll_answer(answer: PollAnswer) -> None:
    _ensure_tables()
    with db.get_conn() as conn:
        delivery = conn.execute(
            "SELECT survey_id, user_id FROM survey_deliveries WHERE telegram_poll_id = ?",
            (answer.poll_id,),
        ).fetchone()
        if delivery is None:
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
                int(delivery["survey_id"]),
                int(answer.user.id),
                ",".join(str(x) for x in answer.option_ids),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
