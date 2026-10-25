"""نظرسنجی‌های شهروندی با Poll واقعی تلگرام."""
import json
import logging
from io import BytesIO
from datetime import datetime, timezone

from aiogram import F, Bot, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message, PollAnswer

import config
import db
from openpyxl import Workbook

router = Router()


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
    _ensure_tables()
    with db.get_conn() as conn:
        return conn.execute(
            "SELECT * FROM surveys WHERE is_active = 1 ORDER BY id DESC LIMIT 1"
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
    if survey is None:
        await message.answer("📊 در حال حاضر نظرسنجی فعالی وجود ندارد.")
        return
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
    if survey is None:
        await callback.answer("در حال حاضر نظرسنجی فعالی وجود ندارد.", show_alert=True)
        return
    ok, reason = await _send_survey_poll(bot, survey, callback.from_user.id)
    if ok:
        await callback.answer("نظرسنجی برای شما ارسال شد.")
    elif reason == "already_sent":
        await callback.answer("شما قبلاً این نظرسنجی را دریافت کرده‌اید.", show_alert=True)
    else:
        await callback.answer("ارسال نظرسنجی ناموفق بود.", show_alert=True)


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
            with db.get_conn() as conn:
                survey = conn.execute(
                    "SELECT * FROM surveys ORDER BY id DESC LIMIT 1"
                ).fetchone()
    if survey is None:
        await message.answer(
            "📊 هنوز نظرسنجی‌ای ثبت نشده است.\n"
            "برای دیدن نتایج یک نظرسنجی مشخص: /survey_results شناسه"
        )
        return
    options = json.loads(survey["options_json"])
    counts = [0] * len(options)
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT option_ids FROM survey_answers WHERE survey_id = ?",
            (int(survey["id"]),),
        ).fetchall()
    for row in rows:
        for raw_index in str(row["option_ids"]).split(","):
            if raw_index.strip().isdigit():
                index = int(raw_index)
                if 0 <= index < len(counts):
                    counts[index] += 1
    total = len(rows)
    status = "🟢 فعال" if int(survey["is_active"]) else "⚪ بسته"
    lines = [
        f"📊 <b>نتایج نظرسنجی شماره {survey['id']}</b> — {status}",
        "",
        str(survey["question"]),
        f"تعداد شهروندان پاسخ‌دهنده: {total}",
        "",
    ]
    for i, option in enumerate(options):
        percent = (counts[i] / total * 100) if total else 0
        lines.append(f"{i + 1}. {option}: <b>{counts[i]}</b> رأی ({percent:.1f}٪)")
    lines.extend(["", "برای نتایج نظرسنجی دیگر: /survey_results شناسه"])
    await message.answer("\n".join(lines))


@router.message(Command("survey_templates"))
async def survey_templates(message: Message) -> None:
    if message.chat.id != config.ADMIN_GROUP_ID:
        return
    await message.answer(
        "🧩 <b>قالب‌های آماده نظرسنجی</b>\n\n"
        "۱) رضایت از نظافت معابر\n"
        "<code>/survey کیفیت نظافت معابر شهر ملایر را چگونه ارزیابی می‌کنید؟ | عالی | خوب | متوسط | ضعیف</code>\n\n"
        "۲) اولویت خدمات شهری\n"
        "<code>/survey کدام خدمت شهری باید در اولویت قرار گیرد؟ | جمع‌آوری پسماند | نگهداری فضای سبز | رفع آب‌گرفتگی | کنترل جانوران موذی</code>\n\n"
        "۳) رضایت از رسیدگی به گزارش‌ها\n"
        "<code>/survey میزان رضایت شما از رسیدگی به گزارش‌های شهروندی چقدر است؟ | کاملاً راضی | راضی | تاحدی راضی | ناراضی</code>"
    )


@router.message(Command("survey_stats"))
async def survey_stats(message: Message) -> None:
    if message.chat.id != config.ADMIN_GROUP_ID:
        return
    _ensure_tables()
    with db.get_conn() as conn:
        surveys = conn.execute(
            "SELECT COUNT(*) AS total, COALESCE(SUM(is_active), 0) AS active FROM surveys"
        ).fetchone()
        answers = conn.execute(
            "SELECT COUNT(*) AS total FROM survey_answers"
        ).fetchone()["total"]
        rows = conn.execute(
            "SELECT s.id, s.question, s.is_active, "
            "COUNT(DISTINCT d.user_id) AS delivered, "
            "COUNT(DISTINCT a.user_id) AS answered "
            "FROM surveys s "
            "LEFT JOIN survey_deliveries d ON d.survey_id = s.id "
            "LEFT JOIN survey_answers a ON a.survey_id = s.id "
            "GROUP BY s.id ORDER BY s.id DESC LIMIT 10"
        ).fetchall()
    lines = [
        "📈 <b>گزارش مدیریتی نظرسنجی‌ها</b>",
        "",
        f"تعداد کل نظرسنجی‌ها: <b>{surveys['total']}</b>",
        f"تعداد نظرسنجی‌های فعال: <b>{surveys['active']}</b>",
        f"کل پاسخ‌های ثبت‌شده: <b>{answers}</b>",
        "",
        "<b>آخرین نظرسنجی‌ها و میزان مشارکت</b>",
    ]
    if not rows:
        lines.append("هنوز نظرسنجی‌ای ثبت نشده است.")
    for row in rows:
        question = str(row["question"]).replace("\\n", " ")
        if len(question) > 55:
            question = question[:52] + "..."
        delivered = int(row["delivered"] or 0)
        answered = int(row["answered"] or 0)
        rate = answered / delivered * 100 if delivered else 0
        status = "فعال" if int(row["is_active"]) else "بسته"
        lines.append(
            f"\\n#{row['id']} — {status}\\n{question}\\n"
            f"ارسال‌شده: {delivered} | پاسخ‌دهنده: {answered} | مشارکت: {rate:.1f}٪"
        )
    await message.answer("\\n".join(lines))


@router.message(Command("suggestions"))
async def list_suggestions(message: Message) -> None:
    if message.chat.id != config.ADMIN_GROUP_ID:
        return
    rows = db.get_all_suggestions(limit=30)
    if not rows:
        await message.answer("💡 هنوز پیشنهادی از شهروندان ثبت نشده است.")
        return
    lines = ["💡 <b>آخرین پیشنهادهای شهروندان</b>", ""]
    for row in rows:
        created = str(row["created_at"]).replace("T", " ")[:16]
        user_name = str(row["user_name"] or "شهروند")
        suggestion = str(row["text"]).replace("\\n", " ")
        if len(suggestion) > 450:
            suggestion = suggestion[:447] + "..."
        lines.append(f"#{row['id']} | {created}\\nاز طرف: {user_name}\\n{suggestion}\\n")
    await message.answer("\\n".join(lines))


@router.message(Command("survey_export"))
async def export_survey_results(message: Message) -> None:
    if message.chat.id != config.ADMIN_GROUP_ID:
        return
    _ensure_tables()
    raw = (message.text or "").split(maxsplit=1)
    survey_id = int(raw[1].strip()) if len(raw) > 1 and raw[1].strip().isdigit() else None
    with db.get_conn() as conn:
        if survey_id is None:
            survey = conn.execute(
                "SELECT * FROM surveys ORDER BY id DESC LIMIT 1"
            ).fetchone()
        else:
            survey = conn.execute(
                "SELECT * FROM surveys WHERE id = ?", (survey_id,)
            ).fetchone()
        if survey is None:
            await message.answer("برای خروجی، نظرسنجی‌ای پیدا نشد.")
            return
        options = json.loads(survey["options_json"])
        answer_rows = conn.execute(
            "SELECT user_id, option_ids, answered_at FROM survey_answers WHERE survey_id = ? ORDER BY answered_at",
            (int(survey["id"]),),
        ).fetchall()
        delivery_count = conn.execute(
            "SELECT COUNT(*) AS n FROM survey_deliveries WHERE survey_id = ?",
            (int(survey["id"]),),
        ).fetchone()["n"]
    workbook = Workbook()
    summary = workbook.active
    summary.title = "خلاصه"
    summary.append(["شناسه نظرسنجی", int(survey["id"])])
    summary.append(["پرسش", str(survey["question"])])
    summary.append(["وضعیت", "فعال" if int(survey["is_active"]) else "بسته"])
    summary.append(["تعداد ارسال ثبت‌شده", int(delivery_count)])
    summary.append(["تعداد پاسخ‌دهندگان", len(answer_rows)])
    summary.append(["درصد مشارکت", round(len(answer_rows) / delivery_count * 100, 1) if delivery_count else 0])
    summary.append([])
    summary.append(["گزینه", "تعداد رأی", "درصد از پاسخ‌ها"])
    counts = [0] * len(options)
    for row in answer_rows:
        for raw_index in str(row["option_ids"]).split(","):
            if raw_index.strip().isdigit():
                idx = int(raw_index)
                if 0 <= idx < len(counts):
                    counts[idx] += 1
    total_votes = sum(counts)
    for idx, option in enumerate(options):
        summary.append([option, counts[idx], round(counts[idx] / total_votes * 100, 1) if total_votes else 0])
    details = workbook.create_sheet("پاسخ‌ها")
    details.append(["شناسه شهروند", "شناسه گزینه انتخابی", "زمان پاسخ"])
    for row in answer_rows:
        details.append([int(row["user_id"]), str(row["option_ids"]), str(row["answered_at"])])
    for sheet in workbook.worksheets:
        sheet.freeze_panes = "A2"
        for column in sheet.columns:
            max_length = max((len(str(cell.value or "")) for cell in column), default=10)
            sheet.column_dimensions[column[0].column_letter].width = min(max(max_length + 2, 12), 55)
    output = BytesIO()
    workbook.save(output)
    filename = f"survey_{int(survey['id'])}_results.xlsx"
    await message.answer_document(
        BufferedInputFile(output.getvalue(), filename=filename),
        caption=f"📊 خروجی اکسل نظرسنجی شماره {survey['id']}",
    )


@router.message(Command("survey_history"))
async def survey_history(message: Message) -> None:
    if message.chat.id != config.ADMIN_GROUP_ID:
        return
    _ensure_tables()
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT id, question, created_at, is_active FROM surveys ORDER BY id DESC LIMIT 10"
        ).fetchall()
    if not rows:
        await message.answer("📊 هنوز هیچ نظرسنجی‌ای ثبت نشده است.")
        return
    lines = ["📚 <b>۱۰ نظرسنجی اخیر</b>", ""]
    for row in rows:
        status = "🟢 فعال" if int(row["is_active"]) else "⚪ بسته"
        question = str(row["question"]).replace("\n", " ")
        if len(question) > 55:
            question = question[:52] + "..."
        lines.append(f"#{row['id']} | {status}\n{question}\n")
    await message.answer("\n".join(lines))


@router.message(Command("survey_close"))
async def close_survey(message: Message) -> None:
    if message.chat.id != config.ADMIN_GROUP_ID:
        return
    _ensure_tables()
    raw = (message.text or "").split(maxsplit=1)
    with db.get_conn() as conn:
        if len(raw) > 1 and raw[1].strip().isdigit():
            cur = conn.execute(
                "UPDATE surveys SET is_active = 0 WHERE id = ? AND is_active = 1",
                (int(raw[1].strip()),),
            )
        else:
            cur = conn.execute("UPDATE surveys SET is_active = 0 WHERE is_active = 1")
    if cur.rowcount:
        await message.answer(
            "🛑 نظرسنجی بسته شد. نتایج آن با دستور /survey_results قابل مشاهده است."
        )
    else:
        await message.answer(
            "نظرسنجی فعالی برای بستن پیدا نشد. برای بستن یک نظرسنجی مشخص: /survey_close شناسه"
        )


@router.poll_answer()
async def save_poll_answer(answer: PollAnswer) -> None:
    try:
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
    except Exception:
        logging.exception("ثبت رأی نظرسنجی %s ناموفق بود.", answer.poll_id)
