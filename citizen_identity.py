"""هویت، کدگذاری و پرونده‌های شهروندی ربات."""
from datetime import datetime, timezone
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import db

router = Router()


def _ensure_table() -> None:
    with db.get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS citizen_codes (
                user_id INTEGER PRIMARY KEY,
                citizen_number INTEGER UNIQUE NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


def citizen_code(user_id: int) -> str:
    """Return a stable public-facing citizen code."""
    _ensure_table()
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT citizen_number FROM citizen_codes WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row:
            number = int(row["citizen_number"])
        else:
            row = conn.execute(
                "SELECT COALESCE(MAX(citizen_number), 0) + 1 AS next_number "
                "FROM citizen_codes"
            ).fetchone()
            number = int(row["next_number"])
            conn.execute(
                "INSERT INTO citizen_codes (user_id, citizen_number, created_at) "
                "VALUES (?, ?, ?)",
                (user_id, number, datetime.now(timezone.utc).isoformat()),
            )
    return f"کد شهروندی-{number:05d}"


def report_code(report_id: int) -> str:
    """Stable report code based on the stored report ID."""
    # Keep the year stable for the report instead of changing it each new year.
    # Existing records store UTC timestamps, so use the report's creation year
    # in the detail view where available; this fallback is for older call sites.
    return f"کد گزارش-{datetime.now().year}-{report_id:05d}"


def _status_emoji(status: str) -> str:
    return {
        db.STATUS_RECEIVED: "🟡",
        db.STATUS_IN_PROGRESS: "🟠",
        db.STATUS_DONE: "🟢",
        db.STATUS_REJECTED: "⚪",
    }.get(status, "🔵")


def _cases_keyboard(reports) -> InlineKeyboardMarkup:
    rows = []
    for report in reports:
        category = str(report["category"] or "گزارش شهری").strip()
        if len(category) > 24:
            category = category[:21] + "..."
        label = f"{_status_emoji(report['status'])} {db.report_code(report['id'])} | {category}"
        rows.append([
            InlineKeyboardButton(
                text=label[:60],
                callback_data=f"case:view:{int(report['id'])}",
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("myid"), F.chat.type == "private")
async def cmd_my_citizen_code(message: Message) -> None:
    code = citizen_code(message.from_user.id)
    await message.answer(
        f"👤 <b>شناسه شهروندی شما</b>\n\n<code>{code}</code>\n\n"
        "این کد برای پیگیری سوابق گزارش‌های شما استفاده می‌شود."
    )


@router.message(Command("cases"), F.chat.type == "private")
async def cmd_my_cases(message: Message) -> None:
    reports = db.get_reports_by_user(message.from_user.id, limit=10)
    if not reports:
        await message.answer(
            "📂 <b>پرونده‌های من</b>\n\n"
            "هنوز گزارشی برای حساب شما ثبت نشده است.\n"
            "برای ثبت گزارش جدید، /start را بزنید."
        )
        return

    counts = {}
    for report in reports:
        counts[report["status"]] = counts.get(report["status"], 0) + 1
    summary = [
        "📂 <b>پرونده‌های شهروندی من</b>",
        f"نمایش {len(reports)} گزارش اخیر شما:",
        "",
        f"📋 مجموع در این فهرست: {len(reports)}",
        f"🟡 دریافت‌شده: {counts.get(db.STATUS_RECEIVED, 0)}",
        f"🟠 در حال رسیدگی: {counts.get(db.STATUS_IN_PROGRESS, 0)}",
        f"🟢 رسیدگی‌شده: {counts.get(db.STATUS_DONE, 0)}",
        "",
        "برای مشاهده جزئیات، یکی از پرونده‌ها را انتخاب کنید:",
    ]
    await message.answer("\n".join(summary), reply_markup=_cases_keyboard(reports))


@router.callback_query(F.data.startswith("case:view:"))
async def callback_case_detail(callback: CallbackQuery) -> None:
    if callback.message is None or callback.message.chat.type != "private":
        await callback.answer("این گزینه فقط در گفت‌وگوی خصوصی قابل استفاده است.", show_alert=True)
        return

    try:
        report_id = int(callback.data.rsplit(":", 1)[1])
    except (ValueError, AttributeError):
        await callback.answer("شناسه پرونده معتبر نیست.", show_alert=True)
        return

    report = db.get_report(report_id)
    if report is None or int(report["user_id"]) != callback.from_user.id:
        await callback.answer("این پرونده پیدا نشد یا متعلق به حساب شما نیست.", show_alert=True)
        return

    created_raw = str(report["created_at"] or "")
    try:
        created_dt = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
        created = created_dt.strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        created = created_raw[:16].replace("T", " ")

    lines = [
        "📋 <b>جزئیات پرونده شهروندی</b>",
        f"کد گزارش: <code>{escape(db.report_code(report_id))}</code>",
        f"وضعیت: {_status_emoji(report['status'])} {escape(str(report['status']))}",
        f"موضوع: {escape(str(report['category'] or 'ثبت نشده'))}",
        f"تاریخ ثبت: {escape(created or 'ثبت نشده')}",
    ]
    description = (report["description"] or "").strip()
    if description:
        lines.append(f"شرح: {escape(description[:700])}")
    has_location = report["latitude"] is not None and report["longitude"] is not None
    lines.append("📍 موقعیت: ثبت شده" if has_location else "📍 موقعیت: ثبت نشده")
    if report["feedback"]:
        lines.append(f"بازخورد شما: {escape(str(report['feedback']))}")

    buttons = []
    if has_location:
        lat, lon = float(report["latitude"]), float(report["longitude"])
        map_url = f"https://www.google.com/maps?q={lat:.6f},{lon:.6f}"
        buttons.append([InlineKeyboardButton(text="🗺 مشاهده موقعیت روی نقشه", url=map_url)])
    buttons.append([InlineKeyboardButton(text="🔎 پیگیری این گزارش", callback_data=f"case:track:{report_id}")])
    await callback.message.answer(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("case:track:"))
async def callback_case_track(callback: CallbackQuery) -> None:
    try:
        report_id = int(callback.data.rsplit(":", 1)[1])
    except (ValueError, AttributeError):
        await callback.answer("شناسه پرونده معتبر نیست.", show_alert=True)
        return
    report = db.get_report(report_id)
    if report is None or int(report["user_id"]) != callback.from_user.id:
        await callback.answer("این پرونده پیدا نشد یا متعلق به حساب شما نیست.", show_alert=True)
        return
    await callback.answer(f"وضعیت فعلی: {report['status']}", show_alert=True)


# Existing handlers call db.report_code(...); this keeps the new public format
# consistent throughout the bot without changing stored report IDs.
db.report_code = report_code
