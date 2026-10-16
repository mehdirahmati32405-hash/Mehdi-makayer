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


# کانال خصوصی گزارش‌های کنترل موش؛ در محیط اجرا با شناسه عددی مانند -100... تنظیم شود.
RODENT_REPORT_CHANNEL_ID_RAW = os.getenv("RODENT_REPORT_CHANNEL_ID")
RODENT_REPORT_CHANNEL_ID = int(RODENT_REPORT_CHANNEL_ID_RAW) if RODENT_REPORT_CHANNEL_ID_RAW else None

# اتصال امن سمت سرور به پنل مدیریت Supabase.
# این مقدار هرگز نباید در کد یا مرورگر قرار بگیرد.
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://aoafbwnqjyocbyyknkhh.supabase.co")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
