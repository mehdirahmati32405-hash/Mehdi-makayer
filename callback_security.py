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

        # Status buttons are management actions and must only work in the admin group.
        if callback_data.startswith("status:"):
            if event.message is None or event.message.chat.id != config.ADMIN_GROUP_ID:
                await event.answer("این عملیات فقط برای مدیران مجاز است.", show_alert=True)
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
