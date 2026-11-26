"""Security checks for callback buttons that expose report-management actions."""

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery

import config
import db


class CallbackSecurityMiddleware(BaseMiddleware):
    """Prevent forged/stale inline callbacks from changing another user's report."""

    async def __call__(self, handler, event, data):
        if not isinstance(event, CallbackQuery):
            return await handler(event, data)

        callback_data = event.data or ""

        # Status changes require both the configured admin group and an actual
        # Telegram group administrator/creator. Group membership alone is not enough.
        if callback_data.startswith("status:"):
            if event.message is None or event.message.chat.id != config.ADMIN_GROUP_ID:
                await event.answer("این عملیات فقط برای مدیران مجاز است.", show_alert=True)
                return None
            try:
                member = await event.bot.get_chat_member(
                    chat_id=config.ADMIN_GROUP_ID,
                    user_id=event.from_user.id,
                )
            except Exception:
                # Fail closed if Telegram cannot verify the caller's role.
                await event.answer(
                    "امکان تأیید سطح دسترسی شما وجود ندارد. لطفاً دوباره تلاش کنید.",
                    show_alert=True,
                )
                return None

            if member.status not in {"administrator", "creator"}:
                await event.answer(
                    "فقط مدیران گروه اجازه تغییر وضعیت گزارش را دارند.",
                    show_alert=True,
                )
                return None

        # Feedback/reopen buttons belong to the report owner.
        if callback_data.startswith("feedback:") or callback_data.startswith("reopen:"):
            try:
                parts = callback_data.split(":")
                report_id = int(parts[1])
            except (IndexError, ValueError):
                await event.answer("شناسه گزارش نامعتبر است.", show_alert=True)
                return None

            report = db.get_report(report_id)
            if report is None:
                await event.answer("این گزارش پیدا نشد.", show_alert=True)
                return None
            if int(report["user_id"]) != int(event.from_user.id):
                await event.answer("این عملیات فقط برای صاحب گزارش مجاز است.", show_alert=True)
                return None

        return await handler(event, data)
