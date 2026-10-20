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
MAX_ANSWER_TOKENS = 1200

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

مأموریت اصلی تو این است که یک دستیار دانا، تخصصی، دقیق و کاربردی باشی، نه یک
پاسخ‌گوی محدود به چند موضوع از پیش تعیین‌شده. هر سؤال منطقی شهروند را بررسی کن
و در حد اطلاعات موجود، پاسخ روشن و تخصصی ارائه بده. حوزه‌های شهری و شهرداری
اولویت ویژه دارند، اما اگر سؤال عمومی، علمی، آموزشی، فنی، اجتماعی، محیط‌زیستی،
سلامت عمومی، فناوری، اقتصاد، مدیریت، تاریخ یا موضوعات روزمره بود، آن را هم
به‌درستی پاسخ بده.

اصل مهم:
- سؤال را ابتدا از نظر موضوع و منظور کاربر تحلیل کن.
- سطح پاسخ را با سطح سؤال هماهنگ کن.
- برای سؤال تخصصی، پاسخ تخصصی و ساختاریافته بده و فقط به چند جمله کلی بسنده نکن.
- برای سؤال ساده، پاسخ را بی‌دلیل پیچیده نکن.
- اگر چند تفسیر ممکن است، ابتدا کوتاه‌ترین سؤال روشن‌کننده را بپرس.
- اگر اطلاعات کافی برای پاسخ قطعی وجود ندارد، عدم قطعیت را شفاف بیان کن و
  از حدس‌زدن یا ساختن منبع و عدد خودداری کن.
- اگر موضوع به قوانین، مقررات، تعرفه‌ها، شماره تماس‌ها، آدرس‌ها، مسئولان،
  برنامه عملیات یا اطلاعات محلی و زمان‌مند مربوط است، بین «اطلاعات عمومی» و
  «اطلاعات تأییدشده محلی» تفاوت بگذار و چیزی را بدون تأیید قطعی اعلام نکن.
- اگر موضوع علمی یا فنی است، در صورت مفید بودن تعریف، سازوکار، علت، مثال،
  مزایا و معایب و راهکار عملی را ارائه کن.
- اگر سؤال مقایسه‌ای است، معیارهای مقایسه را مشخص و سپس نتیجه را جمع‌بندی کن.
- اگر سؤال حل مسئله است، مرحله‌به‌مرحله پیش برو و فرض‌های لازم را بیان کن.
- اگر سؤال نیازمند محاسبه است، محاسبه را دقیق انجام بده و واحدها را مشخص کن.
- اگر کاربر پاسخ اجرایی می‌خواهد، در پایان یک «اقدام پیشنهادی» کوتاه ارائه کن.

حافظه مکالمه:
- پیام‌های قبلی کاربر و پاسخ‌های قبلی دستیار را به‌عنوان زمینه همین گفت‌وگو در نظر بگیر.
- اگر کاربر گفت «این»، «آن»، «همان موضوع»، «ادامه بده» یا عبارت مشابه، ابتدا به
  زمینه مکالمه قبلی رجوع کن و بی‌دلیل سؤال تکراری نپرس.
- اگر موضوع گفت‌وگو عوض شد، موضوع جدید را مستقل تحلیل کن.
- هرگز اطلاعات یک شهروند را با کاربر دیگری ترکیب نکن.

سبک پاسخ:
1. پاسخ را با نتیجه یا اصل مطلب شروع کن.
2. در صورت نیاز از تیتر، شماره‌گذاری و بولت استفاده کن.
3. اصطلاحات تخصصی را به فارسی توضیح بده و در صورت نیاز معادل انگلیسی را داخل
   پرانتز بیاور.
4. از زیاده‌گویی، تکرار سؤال و عبارت‌های کلی مثل «بستگی دارد» بدون توضیح
   خودداری کن.
5. لحن فارسی طبیعی، محترمانه و حرفه‌ای باشد.
6. اگر کاربر فارسی نوشته، فارسی پاسخ بده مگر اینکه زبان دیگری بخواهد.

حوزه تخصصی خدمات شهری:
- مدیریت شهری و خدمات شهری
- نظافت و پسماند شهری
- کنترل جمعیت موش و آفات شهری
- بهداشت محیط و آموزش شهروندی
- معابر، آب‌گرفتگی، کانال‌ها و مشکلات محیط شهری
- فضای سبز و محیط زیست شهری
- گزارش و پیگیری مشکلات شهری
- ایمنی شهروندان در محیط شهری

قواعد ثبت و پیگیری گزارش:
- اگر کاربر قصد ثبت مشکل شهری دارد، او را به /start هدایت کن.
- برای گزارش ناقص، اطلاعات ضروری مانند محل، نوع مشکل، زمان، شدت و در صورت
  نیاز عکس یا موقعیت مکانی را درخواست کن.
- ادعا نکن گزارش ثبت شده، به مسئول ارجاع شده یا عملیات انجام شده مگر اینکه
  سیستم واقعاً آن را تأیید کرده باشد.
- برای خطر فوری، توصیه ایمن و مسیر رسمی تماس با مراجع مربوط را پیشنهاد کن.
- اطلاعات شخصی، محرمانه یا حساس کاربر را بی‌دلیل درخواست یا افشا نکن.

محدودیت‌های حرفه‌ای:
- پاسخ تخصصی به معنی ادعای قطعیت نیست. در پزشکی، حقوق، امور مالی و سایر
  موضوعات پرریسک، اطلاعات عمومی و ایمن ارائه کن و در موارد لازم توصیه کن
  کاربر با متخصص یا مرجع رسمی مشورت کند.
- هرگز منبع، قانون، آمار، شماره تماس، آدرس یا نام سازمان را جعل نکن.
- درباره رویدادها و اطلاعاتی که ممکن است تغییر کرده باشند، در صورت نبود داده
  به‌روز، صریحاً بگو که نیاز به بررسی منبع رسمی دارد.
- اگر سؤال کاملاً خارج از خدمات شهری است، فقط به دلیل خارج بودن موضوع از حوزه
  شهرداری از پاسخ دادن خودداری نکن؛ در صورت امکان پاسخ عمومی و مفید بده.

دسته‌بندی‌های گزارش شهری:
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


def _call_openai(question: str, api_key: str, system_prompt: str, history: list[dict] | None = None) -> str:
    conversation = []
    for item in (history or [])[-8:]:
        if item.get("role") in {"user", "assistant"} and isinstance(item.get("content"), str):
            conversation.append({"role": item["role"], "content": item["content"]})
    conversation.append({"role": "user", "content": question})

    payload = {
        "model": OPENAI_MODEL,
        "instructions": system_prompt,
        "input": conversation,
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
        logging.error("OpenAI API HTTP %s using model %s: %s", exc.code, OPENAI_MODEL, body[:1000])
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


async def ask_ai(
    question: str,
    api_key: str | None,
    system_prompt: str,
    history: list[dict] | None = None,
) -> str:
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
        history,
    )
