"""OpenAI AI assistant for the Malayer citizen-report bot."""

import asyncio
import json
import os
from urllib import request

OPENAI_API_URL = "https://api.openai.com/v1/responses"
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna").strip()
REQUEST_TIMEOUT_SECONDS = 30
MAX_ANSWER_TOKENS = 400

NOT_CONFIGURED_MESSAGE = "این قابلیت هنوز فعال نشده. لطفاً بعداً دوباره امتحان کنید."
ERROR_MESSAGE = "متأسفانه الان نمی‌تونم به این سؤال جواب بدم (مشکل فنی موقت). لطفاً چند لحظه بعد دوباره امتحان کنید."


def build_system_prompt(duties_text: str, categories: list[str]) -> str:
    return (
        "تو دستیار هوشمند ربات گزارش‌دهی شهروندی معاونت خدمات شهری شهرداری ملایر هستی. "
        "به سؤالات شهروندان به فارسی ساده، کوتاه، مؤدبانه و دقیق پاسخ بده.\n\n"
        f"دسته‌بندی‌های گزارش: {'، '.join(categories)}.\n\n"
        f"شرح وظایف رسمی معاونت خدمات شهری:\n{duties_text}\n\n"
        "اگر سؤال درباره مشکل شهری بود، بگو با /start می‌توانند گزارش ثبت کنند. "
        "اگر سؤال بی‌ربط بود، مؤدبانه توضیح بده این ربات برای خدمات شهری طراحی شده است. "
        "اطلاعات نامطمئن یا حدسی ارائه نده."
    )


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
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        return ERROR_MESSAGE

    text = data.get("output_text")
    if isinstance(text, str) and text.strip():
        return text.strip()

    parts = []
    for item in data.get("output", []):
        if isinstance(item, dict):
            for block in item.get("content", []):
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    parts.append(block["text"].strip())
    return "\n".join(x for x in parts if x) or ERROR_MESSAGE


async def ask_ai(question: str, api_key: str | None, system_prompt: str) -> str:
    key = (api_key or os.getenv("OPENAI_API_KEY", "")).strip()
    if not key:
        return NOT_CONFIGURED_MESSAGE
    return await asyncio.to_thread(_call_openai, question.strip(), key, system_prompt)


# Compatibility with the current handlers.py.
# It may still pass config.DEEPSEEK_API_KEY; requests are sent only to OpenAI.
try:
    import config as _config
    if not hasattr(_config, "DEEPSEEK_API_KEY"):
        setattr(_config, "DEEPSEEK_API_KEY", os.getenv("OPENAI_API_KEY", "").strip())
except Exception:
    pass
