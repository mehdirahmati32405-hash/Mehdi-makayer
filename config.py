import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_GROUP_ID_RAW = os.getenv("ADMIN_GROUP_ID")

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN تنظیم نشده است. یک فایل .env بسازید و مقدار آن را از BotFather قرار دهید."
    )

if not ADMIN_GROUP_ID_RAW:
    raise RuntimeError(
        "ADMIN_GROUP_ID تنظیم نشده است. شناسه گروه ادمین را در فایل .env قرار دهید."
    )

ADMIN_GROUP_ID = int(ADMIN_GROUP_ID_RAW)
