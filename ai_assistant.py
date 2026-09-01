"""پاسخ‌گویی هوشمند به سؤالات آزاد شهروندان با استفاده از API دیپ‌سیک.

این ماژول عمداً از aiogram جدا نگه داشته شده تا بدون نیاز به کتابخانه‌های
ربات هم قابل تست باشد. اگر DEEPSEEK_API_KEY تنظیم نشده باشد، تابع اصلی یک
پیام مشخص برمی‌گرداند تا handlers.py بداند این قابلیت غیرفعال است.
"""

import aiohttp

DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-v4-flash"
REQUEST_TIMEOUT_SECONDS = 20
MAX_ANSWER_TOKENS = 400

NOT_CONFIGURED_MESSAGE = (
    "این قابلیت هنوز فعال نشده. لطفاً بعداً امتحان کنید یا سؤالتون رو با دستور "
    "/khadamat یا /amoozesh پیگیری کنید."
)

ERROR_MESSAGE = (
    "متأسفانه الان نمی‌تونم به این سؤال جواب بدم (مشکل فنی موقت). "
    "می‌تونید دوباره امتحان کنید یا از منوی /khadamat یا /amoozesh استفاده کنید."
)


def build_system_prompt(duties_text: str, categories: list[str]) -> str:
    categories_line = "، ".join(categories)
    return (
        "تو دستیار هوشمند ربات گزارش‌دهی شهروندی معاونت خدمات شهری شهرداری ملایر هستی. "
        "به سؤالات شهروندان به زبان فارسی ساده و محاوره‌ای، کوتاه (حداکثر ۴-۵ جمله) و "
        "مؤدبانه جواب بده.\n\n"
        f"دسته‌بندی‌های گزارشی که این ربات پشتیبانی می‌کند: {categories_line}.\n\n"
        f"شرح وظایف رسمی معاونت خدمات شهری:\n{duties_text}\n\n"
        "اگر سؤال درباره گزارش مشکل شهری بود، بگو با دستور /start می‌توانند گزارش ثبت کنند. "
        "اگر سؤال کاملاً بی‌ربط به خدمات شهری/شهرداری بود، مؤدبانه بگو این ربات فقط برای "
        "موضوعات خدمات شهری طراحی شده. اطلاعات نامطمئن یا حدسی ارائه نده؛ اگر پاسخ دقیق را "
        "نمی‌دانی، صادقانه بگو و به تماس با شهرداری ارجاع بده."
    )


async def ask_ai(question: str, api_key: str | None, system_prompt: str) -> str:
    if not api_key:
        return NOT_CONFIGURED_MESSAGE

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
        "max_tokens": MAX_ANSWER_TOKENS,
        "temperature": 0.4,
    }

    try:
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(DEEPSEEK_API_URL, headers=headers, json=payload) as resp:
                if resp.status != 200:
                    return ERROR_MESSAGE
                data = await resp.json()
                return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return ERROR_MESSAGE
