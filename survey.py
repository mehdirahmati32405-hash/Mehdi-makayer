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


def _workbook_bytes(workbook: Workbook) -> bytes:
    """Serialize an Excel workbook to bytes for Telegram document delivery."""
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _style_sheet(sheet) -> None:
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    sheet.sheet_view.rightToLeft = True
    sheet.freeze_panes = "A2"
    for cell in sheet[1]:
        cell.font = Font(name="Arial", bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F4E5F")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for column in sheet.columns:
        values = [len(str(cell.value or "")) for cell in column]
        width = min(max(max(values, default=10) + 2, 12), 42)
        sheet.column_dimensions[get_column_letter(column[0].column)].width = width


def export_survey_results(survey_id: int | None = None) -> bytes:
    """Create an Excel file containing the selected survey's option counts."""
    _ensure_tables()
    with db.get_conn() as conn:
        if survey_id is None:
            survey = conn.execute(
                "SELECT * FROM surveys ORDER BY is_active DESC, id DESC LIMIT 1"
            ).fetchone()
        else:
            survey = conn.execute(
                "SELECT * FROM surveys WHERE id = ?", (int(survey_id),)
            ).fetchone()
        if survey is None:
            raise ValueError("نظرسنجی‌ای برای تهیه خروجی وجود ندارد.")
        answers = conn.execute(
            "SELECT option_ids FROM survey_answers WHERE survey_id = ?",
            (int(survey["id"]),),
        ).fetchall()

    options = json.loads(survey["options_json"])
    counts = [0] * len(options)
    for answer in answers:
        for raw_index in str(answer["option_ids"] or "").split(","):
            raw_index = raw_index.strip()
            if raw_index.isdigit():
                index = int(raw_index)
                if 0 <= index < len(counts):
                    counts[index] += 1

    total = sum(counts)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "نتایج نظرسنجی"
    sheet.append(["شناسه نظرسنجی", int(survey["id"])])
    sheet.append(["سؤال", str(survey["question"])])
    sheet.append([])
    sheet.append(["گزینه", "تعداد رأی", "درصد"])
    for option, count in zip(options, counts):
        sheet.append([str(option), count, round(count / total * 100, 1) if total else 0])
    _style_sheet(sheet)
    return _workbook_bytes(workbook)


def export_monthly_management_report(year: int | None = None, month: int | None = None) -> bytes:
    """Build a five-sheet monthly management workbook from local database records.

    When year/month are omitted, the current UTC month is used. The function
    returns XLSX bytes so callers can send it as a Telegram document.
    """
    now = datetime.now(timezone.utc)
    year = int(year if year is not None else now.year)
    month = int(month if month is not None else now.month)
    if not 1 <= month <= 12:
        raise ValueError("ماه باید بین ۱ تا ۱۲ باشد.")
    period = f"{year:04d}-{month:02d}"
    _ensure_tables()

    with db.get_conn() as conn:
        reports = conn.execute(
            "SELECT id, user_name, category, description, status, created_at, latitude, longitude "
            "FROM reports WHERE created_at LIKE ? ORDER BY id",
            (period + "%",),
        ).fetchall()
        surveys = conn.execute(
            "SELECT id, question, is_active, created_at FROM surveys "
            "WHERE created_at LIKE ? ORDER BY id",
            (period + "%",),
        ).fetchall()
        suggestions = conn.execute(
            "SELECT user_name, text, created_at FROM suggestions "
            "WHERE created_at LIKE ? ORDER BY id",
            (period + "%",),
        ).fetchall()
        appreciations = conn.execute(
            "SELECT user_name, text, created_at FROM appreciations "
            "WHERE created_at LIKE ? ORDER BY id",
            (period + "%",),
        ).fetchall()
        survey_answer_rows = conn.execute(
            "SELECT s.id, s.question, a.option_ids FROM surveys s "
            "LEFT JOIN survey_answers a ON a.survey_id = s.id "
            "WHERE s.created_at LIKE ? ORDER BY s.id",
            (period + "%",),
        ).fetchall()

    workbook = Workbook()
    summary = workbook.active
    summary.title = "خلاصه مدیریتی"
    summary.append(["عنوان شاخص", "مقدار"])
    summary.append(["دوره گزارش", period])
    summary.append(["تعداد گزارش‌های شهروندی", len(reports)])
    summary.append(["تعداد نظرسنجی‌های ایجادشده", len(surveys)])
    summary.append(["تعداد پاسخ‌های نظرسنجی", sum(1 for row in survey_answer_rows if row["option_ids"] is not None)])
    summary.append(["تعداد پیشنهادهای ثبت‌شده", len(suggestions)])
    summary.append(["تعداد پیام‌های قدردانی", len(appreciations)])

    report_sheet = workbook.create_sheet("گزارش‌های شهروندی")
    report_sheet.append(["شناسه", "نام شهروند", "دسته‌بندی", "شرح", "وضعیت", "تاریخ ثبت", "عرض جغرافیایی", "طول جغرافیایی"])
    for row in reports:
        report_sheet.append([row["id"], row["user_name"], row["category"], row["description"],
                             row["status"], row["created_at"], row["latitude"], row["longitude"]])

    survey_sheet = workbook.create_sheet("نظرسنجی‌ها")
    survey_sheet.append(["شناسه", "پرسش", "فعال", "تاریخ ایجاد"])
    for row in surveys:
        survey_sheet.append([row["id"], row["question"], "بله" if row["is_active"] else "خیر", row["created_at"]])

    suggestion_sheet = workbook.create_sheet("پیشنهادها")
    suggestion_sheet.append(["نام شهروند", "متن پیشنهاد", "تاریخ ثبت"])
    for row in suggestions:
        suggestion_sheet.append([row["user_name"], row["text"], row["created_at"]])

    appreciation_sheet = workbook.create_sheet("قدردانی‌ها")
    appreciation_sheet.append(["نام شهروند", "متن قدردانی", "تاریخ ثبت"])
    for row in appreciations:
        appreciation_sheet.append([row["user_name"], row["text"], row["created_at"]])

    for sheet in workbook.worksheets:
        _style_sheet(sheet)
    return _workbook_bytes(workbook)
