import asyncio
import time

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery


class ConfirmationDedupMiddleware(BaseMiddleware):
    """Prevents duplicate processing of the same report-confirmation callback."""

    def __init__(self, ttl_seconds: int = 180) -> None:
        self.ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()
        self._processed: dict[tuple[int, int, int, str], float] = {}

    async def __call__(self, handler, event, data):
        if not isinstance(event, CallbackQuery):
            return await handler(event, data)

        callback_data = event.data or ""
        if not callback_data.startswith("confirm:"):
            return await handler(event, data)

        message = event.message
        if message is None or event.from_user is None:
            return await handler(event, data)

        key = (
            event.from_user.id,
            message.chat.id,
            message.message_id,
            callback_data,
        )

        async with self._lock:
            now = time.monotonic()

            expired = [
                item_key
                for item_key, timestamp in self._processed.items()
                if now - timestamp > self.ttl_seconds
            ]
            for item_key in expired:
                self._processed.pop(item_key, None)

            if key in self._processed:
                await event.answer(
                    "این گزارش قبلاً در حال ثبت/ثبت شده است؛ گزارش دیگری ایجاد نمی‌شود. ✅",
                    show_alert=True,
                )
                return None

            # Mark before entering the handler so a second rapid callback
            # cannot execute submit_report() a second time.
            self._processed[key] = now
            return await handler(event, data)
