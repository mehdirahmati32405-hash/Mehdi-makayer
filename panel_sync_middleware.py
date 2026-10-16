import logging

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

import db
import supabase_sync
from categories import CATEGORIES


class PanelSyncMiddleware(BaseMiddleware):
    """Bridge Telegram reports/statuses with the municipal Supabase panel.

    The panel remains an independent system. If the bridge is unavailable,
    the Telegram bot continues working normally.
    """

    async def __call__(self, handler, event, data):
        panel_row = None
        callback = event if isinstance(event, CallbackQuery) else None

        try:
            if callback is not None and callback.message is not None:
                callback_data = callback.data or ""
                state: FSMContext | None = data.get("state")

                if callback_data in {"confirm:yes", "confirm:anon"} and state is not None:
                    form = await state.get_data()
                    if form.get("latitude") is not None and form.get("longitude") is not None:
                        submission_key = (
                            f"confirm:{callback.message.chat.id}:{callback.message.message_id}"
                        )
                        user = callback.from_user
                        reporter_name = (
                            "شهروند ناشناس"
                            if callback_data == "confirm:anon"
                            else user.full_name
                        )
                        report_type = (
                            "rat"
                            if form.get("category") == CATEGORIES.get("rats")
                            else "other"
                        )
                        panel_row = await supabase_sync.ingest_report(
                            external_ref=submission_key,
                            telegram_user_id=user.id,
                            reporter_name=reporter_name,
                            category=form.get("category", "نامشخص"),
                            description=form.get("description", "ندارد"),
                            latitude=float(form["latitude"]),
                            longitude=float(form["longitude"]),
                            report_type=report_type,
                        )

                elif callback_data.startswith("status:"):
                    parts = callback_data.split(":")
                    if len(parts) == 3:
                        try:
                            local_report_id = int(parts[1])
                            status_key = parts[2]
                            report = db.get_report(local_report_id)
                            if report is not None:
                                await supabase_sync.sync_status(
                                    report["submission_key"], status_key
                                )
                        except Exception:
                            logging.exception("همگام‌سازی وضعیت گزارش با پنل ناموفق بود.")

                elif callback_data.startswith("feedback:"):
                    parts = callback_data.split(":")
                    if len(parts) == 3:
                        try:
                            local_report_id = int(parts[1])
                            report = db.get_report(local_report_id)
                            if report is not None:
                                feedback = (
                                    "مشکل برطرف شده ✅"
                                    if parts[2] == "yes"
                                    else "مشکل هنوز هست ❌"
                                )
                                await supabase_sync.sync_status(
                                    report["submission_key"], "done", feedback
                                )
                        except Exception:
                            logging.exception("همگام‌سازی بازخورد با پنل ناموفق بود.")

        except Exception:
            logging.exception("پل ارتباطی ربات و پنل در مرحله پیش‌پردازش ناموفق بود.")

        result = await handler(event, data)

        # بعد از ثبت موفق گزارش، شناسه پیام مدیران را نیز در پنل نگه می‌داریم.
        if panel_row and callback is not None:
            try:
                submission_key = (
                    f"confirm:{callback.message.chat.id}:{callback.message.message_id}"
                )
                with db.get_conn() as conn:
                    local = conn.execute(
                        "SELECT admin_chat_id, admin_message_id FROM reports WHERE submission_key = ?",
                        (submission_key,),
                    ).fetchone()
                if local is not None:
                    await supabase_sync.mark_synced(
                        panel_row["report_id"],
                        "new",
                        local["admin_chat_id"],
                        local["admin_message_id"],
                    )
            except Exception:
                logging.exception("ذخیره شناسه پیام ادمین در پنل ناموفق بود.")

        return result
