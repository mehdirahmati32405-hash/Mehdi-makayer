"""OpenAI-powered smart assistant for the Malayer citizen-report Telegram bot."""

import asyncio
import json
import logging
import os
from urllib import request
from urllib.error import HTTPError, URLError

OPENAI_API_URL = "https://api.openai.com/v1/responses"
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-6-luna").strip() or "gpt-6-luna"
REQUEST_TIMEOUT_SECONDS = 35
MAX_ANSWER_TOKENS = 700

NOT_CONFIGURED_MESSAGE = (
    "قابلیت دستیار هوشمند هنوز فعال نشده است. "
    "لطفاً تنظیم OPENAI_API_KEY را بررسی کنید."
)

ERROR_MESSAGE = (
    "متأسفانه در حال حاضر امکان پاسخ‌گویی هوشمند وجود ندارد. "
    "لطفاً چند لحظه بعد دوباره امتحان کنید."
)


def build_system_prompt(duties_text: str, categories: list[str]) -> str:
    categories_line = "، ".join(categories)
    return f"""
تو «دستیار هوشمند صدای شهروند» برای معاونت خدمات شهری شهرداری ملایر هستی.

هدف تو پاسخ‌گویی مفید، دقیق و قابل فهم درباره خدمات شهری، ثبت و پیگیری گزارش‌ها
و آموزش شهروندی است.

قواعد:
1. همیشه فارسی پاسخ بده مگر کاربر زبان دیگری بخواهد.
2. لحن محترمانه، صمیمی، آرام و حرفه‌ای باشد.
3. برای سؤال ساده کوتاه و برای سؤال تخصصی کامل‌تر پاسخ بده.
4. در صورت نیاز از تیتر، شماره‌گذاری و بولت استفاده کن.
5. اطلاعات ساختگی درباره قوانین، تلفن، آدرس یا زمان عملیات نده.
6. اگر اطلاعات کافی نداری صادقانه بگو و مسیر رسمی پیگیری را پیشنهاد کن.
7. اگر کاربر قصد ثبت مشکل شهری دارد او را به /start هدایت کن.
8. برای گزارش ناقص، سؤال تکمیلی مشخص بپرس.
9. در موارد خطر فوری، مسیر رسمی و ایمن را پیشنهاد کن.
10. اگر سؤال خارج از حوزه خدمات شهری ملایر است، محترمانه محدودیت حوزه ربات را بگو.
11. ادعا نکن گزارش ثبت یا عملیات انجام شده مگر سیستم آن را تأیید کرده باشد.

دسته‌بندی‌های گزارش:
{categories_line}

شرح وظایف رسمی معاونت خدمات شهری:
{duties_text}
""".strip()


def _extract_response_text(data: dict) -> str:
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

    except HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        logging.error(
            "OpenAI API HTTP %s using model %s: %s",
            exc.code,
            OPENAI_MODEL,
            body[:1000],
        )
        return ERROR_MESSAGE
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        logging.error("OpenAI API connection error using model %s: %s", OPENAI_MODEL, exc)
        return ERROR_MESSAGE
    except Exception:
        logging.exception("Unexpected OpenAI assistant error using model %s", OPENAI_MODEL)
        return ERROR_MESSAGE

    answer = _extract_response_text(data)
    if not answer:
        logging.error("OpenAI returned no text. Response keys: %s", list(data.keys()))
        return ERROR_MESSAGE
    return answer


async def ask_ai(question: str, api_key: str | None, system_prompt: str) -> str:
    key = (api_key or os.getenv("OPENAI_API_KEY", "")).strip()
    if not key:
        logging.error("OPENAI_API_KEY is empty at runtime.")
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
