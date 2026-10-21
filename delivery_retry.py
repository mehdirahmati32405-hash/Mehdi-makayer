"""Reliable retry for reports that were saved but not delivered to admins."""

import json
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.types import InputMediaPhoto

import config
import db

RETRY_INTERVAL_MINUTES = 5
RETRY_BATCH_SIZE = 10


def get_pending_reports(limit: int = RETRY_BATCH_SIZE):
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=RETRY_INTERVAL_MINUTES)).isoformat()
    with db.get_conn() as conn:
        return conn.execute(
            """
            SELECT * FROM reports
            WHERE admin_message_id IS NULL
              AND created_at <= ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (cutoff, limit),
        ).fetchall()


async def retry_pending_admin_reports(bot: Bot) -> tuple[int, int]:
    """Retry delivery without creating a second report record.

    A report is already persisted before Telegram delivery starts, so a
    temporary Telegram/Railway failure can be repaired by this loop.
    """
    success = failed = 0
    for report in get_pending_reports():
        report_id = int(report["id"])
        try:
            photos = []
            if report["photo_file_id"]:
                photos.append(report["photo_file_id"])
            if report["extra_photos"]:
                try:
                    photos.extend(json.loads(report["extra_photos"]))
                except (TypeError, ValueError, json.JSONDecodeError):
                    logging.warning("تصاویر اضافی گزارش %s قابل بازیابی نبودند.", report_id)

            sender = "گزارش ناشناس" if report["is_anonymous"] else f"{report['user_name']}"
            caption = (
                f"📣 گزارش شهروندی (ارسال مجدد)\n\n"
                f"کد پیگیری: {db.report_code(report_id)}\n"
                f"دسته‌بندی: {report['category']}\n"
                f"توضیحات: {report['description'] or 'ندارد'}\n"
                f"از طرف: {sender}\n"
                f"وضعیت: {db.STATUS_RECEIVED}"
            )

            if report["voice_file_id"]:
                await bot.send_voice(chat_id=config.ADMIN_GROUP_ID, voice=report["voice_file_id"])
            elif len(photos) > 1:
                await bot.send_media_group(
                    chat_id=config.ADMIN_GROUP_ID,
                    media=[InputMediaPhoto(media=p) for p in photos],
                )
            elif len(photos) == 1:
                await bot.send_photo(chat_id=config.ADMIN_GROUP_ID, photo=photos[0])

            await bot.send_location(
                chat_id=config.ADMIN_GROUP_ID,
                latitude=report["latitude"],
                longitude=report["longitude"],
            )
            sent = await bot.send_message(
                chat_id=config.ADMIN_GROUP_ID,
                text=caption,
            )
            db.set_admin_message(report_id, sent.chat.id, sent.message_id)
            success += 1
        except Exception:
            failed += 1
            logging.exception("ارسال مجدد گزارش %s ناموفق بود.", report_id)

    return success, failed
