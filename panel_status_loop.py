import asyncio
import logging

from aiogram import Bot

import db
import supabase_sync
from handlers import feedback_keyboard


POLL_SECONDS = 30

STATUS_TEXT = {
    "assigned": "📌 این گزارش از پنل مدیریتی به تیم عملیاتی ارجاع شد.",
    "in_progress": "🔄 وضعیت این گزارش در پنل به «در حال اجرا» تغییر کرد.",
    "closed": "✅ این گزارش در پنل مدیریتی مختومه شد.",
    "rejected": "🚫 این گزارش در پنل مدیریتی به‌عنوان غیرقابل بررسی ثبت شد.",
    "reviewing": "🔎 این گزارش در پنل وارد مرحله بررسی شد.",
}


async def _find_local_report(external_ref: str):
    with db.get_conn() as conn:
        return conn.execute(
            "SELECT * FROM reports WHERE submission_key = ? LIMIT 1",
            (external_ref,),
        ).fetchone()


async def panel_status_loop(bot: Bot) -> None:
    while True:
        try:
            changes = await supabase_sync.get_status_changes()
            for change in changes:
                status = change.get("status")
                text = STATUS_TEXT.get(status)
                if not text:
                    await supabase_sync.mark_synced(change["report_id"], status)
                    continue

                local = await _find_local_report(change.get("external_ref"))
                admin_chat_id = change.get("telegram_admin_chat_id")
                admin_message_id = change.get("telegram_admin_message_id")

                # اطلاع مدیران از تغییری که از خود پنل انجام شده است.
                if admin_chat_id:
                    try:
                        await bot.send_message(
                            chat_id=admin_chat_id,
                            text=f"🖥️ همگام‌سازی پنل\nکد: {change.get('report_code', '—')}\n{text}",
                            reply_to_message_id=admin_message_id or None,
                        )
                    except Exception:
                        logging.exception("اطلاع‌رسانی تغییر پنل به مدیران ناموفق بود.")

                # اطلاع شهروند و در صورت مختومه‌شدن، درخواست بازخورد.
                user_id = change.get("telegram_user_id")
                if user_id:
                    try:
                        await bot.send_message(
                            chat_id=int(user_id),
                            text=(
                                f"🔔 وضعیت گزارش شما (کد {change.get('report_code', '—')}) به‌روزرسانی شد.\n\n"
                                f"{text}"
                            ),
                        )
                        if status == "closed" and local is not None:
                            await bot.send_message(
                                chat_id=int(user_id),
                                text="آیا مشکل واقعاً برطرف شده؟ نظر شما به بهبود کیفیت خدمات کمک می‌کند 🙏",
                                reply_markup=feedback_keyboard(int(local["id"])),
                            )
                    except Exception:
                        # شهروند ممکن است ربات را مسدود کرده باشد.
                        pass

                await supabase_sync.mark_synced(
                    change["report_id"],
                    status,
                    admin_chat_id,
                    admin_message_id,
                )

        except Exception:
            logging.exception("خطا در همگام‌سازی پنل با ربات تلگرام.")

        await asyncio.sleep(POLL_SECONDS)
