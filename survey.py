"""نظرسنجی‌های شهروندی با Poll واقعی تلگرام."""
import json
import logging
from io import BytesIO
from datetime import datetime, timezone

from aiogram import F, Bot, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message

import config
import db
from openpyxl import Workbook

router = Router()

DEFAULT_SURVEY_QUESTION = "میزان رضایت شما از خدمات شهری شهرداری ملایر چقدر است؟"
DEFAULT_SURVEY_OPTIONS = ["عالی", "خوب", "متوسط", "ضعیف"]


def _ensure_tables() -> None:
    with db.get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS surveys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                options_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS survey_deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                survey_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                telegram_poll_id TEXT UNIQUE NOT NULL,
                sent_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS survey_answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                survey_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                option_ids TEXT NOT NULL,
                answered_at TEXT NOT NULL,
                UNIQUE(survey_id, user_id)
            )
        """)


def _parse_survey(text: str) -> tuple[str, list[str]] | None:
    parts = [p.strip() for p in text.split("|") if p.strip()]
    if len(parts) < 3:
        return None
    question = parts[0]
    options = parts[1:11]
    if not 3 <= len(question) <= 300 or len(options) < 2:
        return None
    if any(not 1 <= len(option) <= 100 for option in options):
        return None
    return question, options


def _active_survey():
    """برگرداندن نظرسنجی فعال؛ در نبود آن یک نظرسنجی پایه ایجاد می‌کند."""
    _ensure_tables()
    with db.get_conn() as conn:
        survey = conn.execute(
            "SELECT * FROM surveys WHERE is_active = 1 ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if survey is not None:
            return survey

        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "INSERT INTO surveys(question, options_json, created_at, is_active) VALUES (?, ?, ?, 1)",
            (
                DEFAULT_SURVEY_QUESTION,
                json.dumps(DEFAULT_SURVEY_OPTIONS, ensure_ascii=False),
                now,
            ),
        )
        return conn.execute(
            "SELECT * FROM surveys WHERE id = ?", (int(cur.lastrowid),)
        ).fetchone()


def _already_delivered(survey_id: int, user_id: int) -> bool:
    _ensure_tables()
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM survey_deliveries WHERE survey_id = ? AND user_id = ? LIMIT 1",
            (survey_id, user_id),
        ).fetchone()
    return row is not None


async def _send_survey_poll(bot: Bot, survey, user_id: int) -> tuple[bool, str]:
    survey_id = int(survey["id"])
    if _already_delivered(survey_id, user_id):
        return False, "already_sent"
    try:
        options = json.loads(survey["options_json"])
        if not isinstance(options, list) or not 2 <= len(options) <= 10:
            return False, "invalid_options"
        poll = await bot.send_poll(
            chat_id=user_id,
            question=str(survey["question"]),
            options=[str(option) for option in options],
            is_anonymous=False,
            allows_multiple_answers=False,
        )
    except Exception:
        logging.exception("ارسال نظرسنجی %s به کاربر %s ناموفق بود.", survey_id, user_id)
        return False, "send_failed"
    try:
        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO survey_deliveries(survey_id, user_id, telegram_poll_id, sent_at) VALUES (?, ?, ?, ?)",
                (survey_id, int(user_id), poll.poll.id, datetime.now(timezone.utc).isoformat()),
            )
    except Exception:
        logging.exception("ثبت ارسال نظرسنجی %s برای کاربر %s ناموفق بود.", survey_id, user_id)
        return False, "db_failed"
    return True, "sent"


@router.message(Command("survey"))
async def create_survey(message: Message, bot: Bot) -> None:
    if message.chat.id != config.ADMIN_GROUP_ID:
        return
    raw = (message.text or "").split(maxsplit=1)
    if len(raw) < 2:
        await message.answer(
            "📊 <b>ساخت نظرسنجی</b>\n\n"
            "قالب:\n<code>/survey سوال | گزینه اول | گزینه دوم | گزینه سوم</code>\n\n"
            "حداکثر ۱۰ گزینه. سؤال حداکثر ۳۰۰ و هر گزینه حداکثر ۱۰۰ نویسه."
        )
        return
    parsed = _parse_survey(raw[1])
    if parsed is None:
        await message.answer("فرمت نظرسنجی صحیح نیست. سؤال و حداقل دو گزینه معتبر وارد کنید.")
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
    skipped = 0
    failed = 0
    survey = {"id": survey_id, "question": question, "options_json": json.dumps(options, ensure_ascii=False)}
    for row in subscribers:
        ok, reason = await _send_survey_poll(bot, survey, int(row["user_id"]))
        if ok:
            sent += 1
        elif reason == "already_sent":
            skipped += 1
        else:
            failed += 1

    await message.answer(
        f"📊 <b>نظرسنجی فعال شد.</b>\n\n"
        f"ارسال موفق: {sent}\n"
        f"قبلاً ارسال شده: {skipped}\n"
        f"ارسال ناموفق: {failed}\n"
        f"شناسه نظرسنجی: {survey_id}"
    )


@router.message(Command("survey_current"), F.chat.type == "private")
async def current_survey(message: Message, bot: Bot) -> None:
    survey = _active_survey()
    ok, reason = await _send_survey_poll(bot, survey, message.from_user.id)
    if ok:
        await message.answer("📊 نظرسنجی فعال برای شما ارسال شد. ممنون که نظر می‌دهید. 🌹")
    elif reason == "already_sent":
        await message.answer("✅ شما قبلاً این نظرسنجی را دریافت کرده‌اید.")
    else:
        await message.answer("ارسال نظرسنجی انجام نشد. لطفاً کمی بعد دوباره تلاش کنید.")


@router.callback_query(F.data == "menu:survey")
async def menu_survey(callback: CallbackQuery, bot: Bot) -> None:
    survey = _active_survey()
    ok, reason = await _send_survey_poll(bot, survey, callback.from_user.id)
    if ok:
        await callback.answer("📊 نظرسنجی برای شما ارسال شد.")
    elif reason == "already_sent":
        await callback.answer("✅ شما قبلاً این نظرسنجی را دریافت کرده‌اید.", show_alert=True)
    else:
        await callback.answer("ارسال نظرسنجی ناموفق بود. لطفاً دوباره تلاش کنید.", show_alert=True)


@router.message(Command("survey_results"))
async def survey_results(message: Message) -> None:
    if message.chat.id != config.ADMIN_GROUP_ID:
        return
    _ensure_tables()
    raw = (message.text or "").split(maxsplit=1)
    survey = None
    if len(raw) > 1 and raw[1].strip().isdigit():
        with db.get_conn() as conn:
            survey = conn.execute(
                "SELECT * FROM surveys WHERE id = ?", (int(raw[1].strip()),)
            ).fetchone()
    else:
        survey = _active_survey()
    if survey is None:
        await message.answer("📊 هنوز نظرسنجی‌ای ثبت نشده است.")
        return
    options = json.loads(survey["options_json"])
    counts = [0] * len(options)
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT option_ids FROM survey_answers WHERE survey_id = ?",
            (int(survey["id"]),),
        ).fetchall()
    for row in rows:
        for value in str(row["option_ids"]).split(","):
            if value.strip().isdigit():
                index = int(value.strip())
                if 0 <= index < len(counts):
                    counts[index] += 1
    total = sum(counts)
    lines = [
        f"📊 <b>نتایج نظرسنجی {survey['id']}</b>",
        f"سؤال: {survey['question']}",
        f"تعداد پاسخ‌ها: {total}",
        "",
    ]
    for index, option in enumerate(options):
        percent = (counts[index] / total * 100) if total else 0
        lines.append(f"{option}: {counts[index]} رأی ({percent:.1f}٪)")
    await message.answer("\n".join(lines))
