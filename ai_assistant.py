"""OpenAI-powered smart assistant for the Malayer citizen-report Telegram bot.

This module is designed to work with the existing handlers.py without requiring
aiohttp or DeepSeek. It uses the OpenAI Responses API through Python's standard
library only.

Environment variables:
    OPENAI_API_KEY   Required
    OPENAI_MODEL     Optional; defaults to gpt-5.6-luna
"""

import asyncio
import json
import os
from urllib import request
from urllib.error import HTTPError, URLError

OPENAI_API_URL = "https://api.openai.com/v1/responses"
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna").strip()

REQUEST_TIMEOUT_SECONDS = 35
MAX_ANSWER_TOKENS = 700

NOT_CONFIGURED_MESSAGE = (
    "قابلیت دستیار هوشمند هنوز فعال نشده است. لطفاً بعداً دوباره امتحان کنید."
)

ERROR_MESSAGE = (
    "متأسفانه در حال حاضر امکان پاسخ‌گویی هوشمند وجود ندارد. "
    "لطفاً چند لحظه بعد دوباره امتحان کنید."
)


def build_system_prompt(duties_text: str, categories: list[str]) -> str:
    """Build the assistant's behavior and municipal-service knowledge prompt."""

    categories_line = "، ".join(categories)

    return f"""
تو «دستیار هوشمند صدای شهروند» برای معاونت خدمات شهری شهرداری ملایر هستی.

هدف تو این است که به شهروندان درباره موضوعات مرتبط با خدمات شهری،
ثبت گزارش، پیگیری و آموزش شهروندی پاسخ‌های مفید، دقیق و قابل فهم بدهی.

قواعد اصلی پاسخ‌گویی:
1. همیشه فارسی پاسخ بده، مگر اینکه کاربر زبان دیگری بخواهد.
2. لحن تو محترمانه، صمیمی، آرام، حرفه‌ای و شهروندمدار باشد.
3. پاسخ‌ها دیگر محدود به چند جمله نباشند؛ برای سؤال‌های ساده کوتاه و برای
   سؤال‌های تخصصی یا آموزشی کامل‌تر توضیح بده.
4. پاسخ را ساختارمند کن. در صورت نیاز از تیتر، شماره‌گذاری و بولت استفاده کن.
5. از اطلاعات ساختگی، حدس درباره قوانین، شماره تلفن، آدرس، زمان‌بندی عملیات
   یا تصمیمات شهرداری خودداری کن.
6. اگر اطلاعات دقیق در متن وظایف رسمی وجود ندارد، صادقانه بگو که اطلاعات کافی
   در اختیار نداری و در صورت نیاز پیشنهاد کن موضوع از شهرداری پیگیری شود.
7. اگر شهروند قصد ثبت مشکل شهری دارد، او را به /start هدایت کن و تأکید کن
   که آدرس دقیق، محله/خیابان، شرح مشکل و در صورت امکان عکس ارائه کند.
8. اگر گزارش ناقص است، سؤال‌های تکمیلی مشخص بپرس؛ مثلاً «مکان دقیق کجاست؟»
   یا «مشکل چه زمانی مشاهده شده است؟».
9. در موضوعات ایمنی، بهداشت عمومی یا خطر فوری، از ارائه دستورالعمل خطرناک
   خودداری کن و شهروند را به مسیر رسمی و ایمن ارجاع بده.
10. اگر سؤال خارج از حوزه خدمات شهری و شهرداری است، کوتاه و مؤدبانه توضیح بده
    که ربات برای خدمات شهری ملایر طراحی شده است.
11. هیچ‌وقت وانمود نکن که گزارش ثبت شده یا عملیات اجرایی انجام شده است،
    مگر اینکه سیستم صراحتاً چنین اطلاعاتی را در اختیار تو گذاشته باشد.
12. اگر کاربر فقط یک تشکر یا سلام ساده کرد، پاسخ طبیعی و کوتاه بده.
13. از عبارت‌های خشک و رباتیک کمتر استفاده کن و پاسخ را شبیه یک کارشناس
    پاسخ‌گوی شهروندان بنویس.
14. در پاسخ‌های آموزشی، ابتدا پاسخ مستقیم را بده و سپس توضیح تکمیلی را اضافه کن.
15. اگر چند راهکار وجود دارد، مناسب‌ترین و کم‌خطرترین راهکار را اول بیاور.

دسته‌بندی‌های گزارش این ربات:
{categories_line}

شرح وظایف رسمی معاونت خدمات شهری:
{duties_text}

نمونه رفتار:
- سؤال «چطور گزارش جمع‌آوری زباله ثبت کنم؟» → مراحل ثبت گزارش را توضیح بده
  و کاربر را به /start هدایت کن.
- سؤال «در کوچه ما موش زیاد شده، چه کار کنیم؟» → علت‌های عمومی و راهکارهای
  پیشگیری را توضیح بده، سپس پیشنهاد ثبت گزارش دقیق در /start بده.
- سؤال «سگ ولگرد دیدم» → از ثبت مکان دقیق و زمان مشاهده بگو و از /start
  برای گزارش استفاده شود.
- سؤال «وظیفه خدمات شهری چیست؟» → بر اساس متن رسمی بالا توضیح بده.
- سؤال نامرتبط مثل «قیمت گوشی چیست؟» → مؤدبانه بگو حوزه این ربات خدمات شهری است.

هرگز اطلاعاتی را که نمی‌دانی به‌عنوان واقعیت ارائه نکن.
""".strip()


def _extract_response_text(data: dict) -> str:
    """Extract text robustly from a Responses API response."""

    text = data.get("output_text")
    if isinstance(text, str) and text.strip():
        return text.strip()

    parts: list[str] = []

    for item in data.get("output", []):
        if not isinstance(item, dict):
            continue

        for block in item.get("content", []):
            if not isinstance(block, dict):
                continue

            block_text = block.get("text")
            if isinstance(block_text, str) and block_text.strip():
                parts.append(block_text.strip())

    return "\n".join(parts).strip()


def _call_openai(question: str, api_key: str, system_prompt: str) -> str:
    payload = {
        "model": OPENAI_MODEL,
        "instructions": system_prompt,
        "input": question,
        "max_output_tokens": MAX_ANSWER_TOKENS,
    }

    req = request.Request(
        OPENAI_API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
            data = json.loads(raw)

    except HTTPError:
        return ERROR_MESSAGE
    except (URLError, TimeoutError, json.JSONDecodeError, OSError):
        return ERROR_MESSAGE
    except Exception:
        return ERROR_MESSAGE

    answer = _extract_response_text(data)

    if not answer:
        return ERROR_MESSAGE

    return answer


async def ask_ai(
    question: str,
    api_key: str | None,
    system_prompt: str,
) -> str:
    """Async wrapper compatible with the existing handlers.py."""

    key = (api_key or os.getenv("OPENAI_API_KEY", "")).strip()

    if not key:
        return NOT_CONFIGURED_MESSAGE

    clean_question = (question or "").strip()

    if not clean_question:
        return "لطفاً سؤال یا توضیح موردنظرتان را بنویسید."

    return await asyncio.to_thread(
        _call_openai,
        clean_question,
        key,
        system_prompt,
    )


# Compatibility with the current handlers.py:
# handlers.py may still pass config.DEEPSEEK_API_KEY.
# We intentionally map that name to OPENAI_API_KEY so no DeepSeek request is made.
try:
    import config as _config

    if not hasattr(_config, "DEEPSEEK_API_KEY"):
        setattr(
            _config,
            "DEEPSEEK_API_KEY",
            os.getenv("OPENAI_API_KEY", "").strip(),
        )
except Exception:
    pass
