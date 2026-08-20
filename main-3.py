import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

import config
import db
from handlers import router


async def set_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="شروع / ثبت گزارش جدید"),
            BotCommand(command="myreports", description="گزارش‌های من"),
            BotCommand(command="khadamat", description="خدمات و اطلاعات شهرداری"),
            BotCommand(command="amoozesh", description="آموزش شهروندی"),
            BotCommand(command="stats", description="آمار کلی گزارش‌ها"),
            BotCommand(command="cancel", description="لغو عملیات جاری"),
        ]
    )


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

    logging.info("ربات در حال اجراست...")
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
