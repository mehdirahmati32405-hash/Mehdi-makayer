"""پیگیری حرفه‌ای گزارش‌های شهروندی."""
import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

import db

router = Router()


class TrackingForm(StatesGroup):
    waiting_code = State()


def _normalize_digits(value: str) -> str:
    table = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    return value.translate(table)


def _extract_report_id(text: str) -> int | None:
    normalized = _normalize_digits(text.strip())
    # پشتیبانی از قالب جدید و قالب قدیمی برای سوابق موجود
    match = re.search(r"(?:کد\s*گزارش[-\s]*|گزارش[-\s]*|ML[-_\s]*)(?:\d{4}[-\s]*)?(\d+)", normalized, re.IGNORECASE)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    if normalized.isdigit():
        return int(normalized)
    return None


def _status_emoji(status: str) -> str:
    return {
        db.STATUS_RECEIVED: "🟡",
        db.STATUS_IN_PROGRESS: "🟠",
        db.STATUS_DONE: "🟢",
        db.STATUS_REJECTED: "⚪",
    }.get(status, "🔵")


async def _show_report(message: Message, report_id: int) -> None:
    report = db.get_report(report_id)
    if report is None:
        await message.answer("❌ گزارشی با این کد پیدا نشد. کد را دوباره بررسی کنید.")
        return

    # گزارش‌های خصوصی فقط برای صاحب گزارش قابل مشاهده‌اند.
    if report["user_id"] != message.from_user.id:
        await message.answer("🔒 این گزارش متعلق به حساب شما نیست.")
        return

    created = report["created_at"].replace("T", " ")[:16]
    lines = [
        f"📋 <b>{db.report_code(report_id)}</b>",
        f"وضعیت: {_status_emoji(report['status'])} {report['status']}",
        f"موضوع: {report['category']}",
        f"تاریخ ثبت: {created}",
    ]
    if report["description"]:
        lines.append(f"شرح: {report['description'][:500]}")
    if report["latitude"] is not None and report["longitude"] is not None:
        lines.append("📍 موقعیت مکانی: ثبت شده")
    if report["feedback"]:
        lines.append(f"بازخورد شما: {report['feedback']}")

    await message.answer("\n".join(lines))


@router.message(Command("track"), F.chat.type == "private")
async def cmd_track(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(TrackingForm.waiting_code)
    await message.answer(
        "🔎 <b>پیگیری گزارش شهروندی</b>\n\n"
        "کد گزارش خود را وارد کنید.\n"
        "مثال: <code>کد گزارش-1405-00007</code>\n\n"
        "برای لغو: /cancel"
    )


@router.message(TrackingForm.waiting_code, F.chat.type == "private", F.text)
async def process_track_code(message: Message, state: FSMContext) -> None:
    report_id = _extract_report_id(message.text)
    if report_id is None:
        await message.answer("❌ قالب کد صحیح نیست. نمونه: <code>کد گزارش-1405-00007</code>")
        return
    await _show_report(message, report_id)
    await state.clear()


@router.message(TrackingForm.waiting_code, F.chat.type == "private")
async def track_invalid(message: Message) -> None:
    await message.answer("لطفاً کد گزارش را به‌صورت متن ارسال کنید.")
