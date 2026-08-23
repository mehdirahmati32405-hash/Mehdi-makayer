import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

import config
import db
from handlers import router

REMINDER_CHECK_INTERVAL_SECONDS = 60 * 60          # هر ساعت چک می‌کند
REMINDER_STALE_HOURS = 48                          # بعد از ۴۸ ساعت یادآوری می‌کند
WEEKLY_SUMMARY_CHECK_INTERVAL_SECONDS = 60 * 60     # هر ساعت چک می‌کند
WEEKLY_SUMMARY_WEEKDAY = 6                          # یکشنبه (دوشنبه=0 ... یکشنبه=6)
WEEKLY_SUMMARY_HOUR_UTC = 5                         # تقریباً ساعت ۸:۳۰ صبح به‌وقت ایران

PERSIAN_WEEKDAYS = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]


async def set_commands(bot: Bot) -> None:
    base_commands = [
        BotCommand(command="start", description="شروع / ثبت گزارش جدید"),
        BotCommand(command="myreports", description="گزارش‌های من"),
        BotCommand(command="khadamat", description="خدمات و اطلاعات شهرداری"),
        BotCommand(command="amoozesh", description="آموزش شهروندی"),
        BotCommand(command="quiz", description="آزمون شهروند نمونه"),
        BotCommand(command="quiz_top", description="جدول امتیازات آزمون"),
        BotCommand(command="stats", description="آمار کلی گزارش‌ها"),
        BotCommand(command="cancel", description="لغو عملیات جاری"),
    ]
    await bot.set_my_commands(base_commands, scope=BotCommandScopeDefault())

    # دستور /search فقط برای گروه ادمین نمایش داده می‌شود (چون جزئیات گزارش دیگران را نشان می‌دهد)
    admin_commands = base_commands + [
        BotCommand(command="search", description="جست‌وجوی گزارش‌ها"),
    ]
    try:
        await bot.set_my_commands(
            admin_commands, scope=BotCommandScopeChat(chat_id=config.ADMIN_GROUP_ID)
        )
    except Exception:
        # اگر ربات هنوز عضو گروه ادمین نباشد یا دسترسی نداشته باشد، از این مرحله بی‌سروصدا عبور می‌کنیم
        logging.warning("تنظیم دستورات ویژه گروه ادمین ممکن نشد.")


async def reminder_loop(bot: Bot) -> None:
    while True:
        try:
            stale_reports = db.get_stale_reports(hours=REMINDER_STALE_HOURS)
            for report in stale_reports:
                if not report["admin_chat_id"] or not report["admin_message_id"]:
                    continue
                try:
                    await bot.send_message(
                        chat_id=report["admin_chat_id"],
                        text=(
                            f"⏰ یادآوری: گزارش {db.report_code(report['id'])} بیش از "
                            f"{REMINDER_STALE_HOURS} ساعت است در وضعیت «{report['status']}» "
                            "باقی مانده. لطفاً بررسی شود."
                        ),
                        reply_to_message_id=report["admin_message_id"],
                    )
                    db.mark_reminded(report["id"])
                except Exception:
                    logging.exception("ارسال یادآوری برای گزارش %s ناموفق بود.", report["id"])
        except Exception:
            logging.exception("خطا در بررسی گزارش‌های راکد.")

        await asyncio.sleep(REMINDER_CHECK_INTERVAL_SECONDS)


async def weekly_summary_loop(bot: Bot) -> None:
    while True:
        try:
            now = datetime.now(timezone.utc)
            already_sent_key = db.get_state("last_weekly_summary_date")
            today_str = now.strftime("%Y-%m-%d")
            if (
                now.weekday() == WEEKLY_SUMMARY_WEEKDAY
                and now.hour == WEEKLY_SUMMARY_HOUR_UTC
                and already_sent_key != today_str
            ):
                stats = db.get_period_stats(days=7)
                top_reporters = db.get_top_reporters(days=30, limit=5)

                lines = [
                    "📊 گزارش هفتگی خودکار — عملکرد ربات گزارش شهروندی\n",
                    f"گزارش‌های ثبت‌شده در ۷ روز اخیر: {stats['total']}",
                    f"رسیدگی‌شده از همین بازه: {stats['done']}",
                ]
                if stats["top_category"]:
                    lines.append(
                        f"پرتکرارترین دسته: {stats['top_category']} ({stats['top_category_count']} مورد)"
                    )

                if top_reporters:
                    lines.append("\n🌟 فعال‌ترین شهروندان (۳۰ روز اخیر):")
                    for i, r in enumerate(top_reporters, start=1):
                        lines.append(f"{i}. {r['user_name']} — {r['c']} گزارش")

                try:
                    await bot.send_message(chat_id=config.ADMIN_GROUP_ID, text="\n".join(lines))
                    db.set_state("last_weekly_summary_date", today_str)
                except Exception:
                    logging.exception("ارسال گزارش هفتگی ناموفق بود.")
        except Exception:
            logging.exception("خطا در بررسی زمان‌بندی گزارش هفتگی.")

        await asyncio.sleep(WEEKLY_SUMMARY_CHECK_INTERVAL_SECONDS)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    db.init_db()

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    await set_commands(bot)

    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(router)

    asyncio.create_task(reminder_loop(bot))
    asyncio.create_task(weekly_summary_loop(bot))

    logging.info("ربات در حال اجراست...")
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
