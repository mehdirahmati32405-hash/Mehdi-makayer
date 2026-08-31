from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

import ai_assistant
import config
import db
import export
from categories import CATEGORIES, SOCIAL_HELP_HOTLINE, SOCIAL_REFERRAL_CATEGORY_KEYS
from services_content import SCHEDULE_TEXT, ACTIVITIES_TEXT, DUTIES_TEXT
from education_content import TOPICS as EDUCATION_TOPICS
from quiz_content import QUESTIONS as QUIZ_QUESTIONS, get_result_message

router = Router()

# نگاشت شماره روز هفته پایتون (دوشنبه=0) به نام روز هفته فارسی
PERSIAN_WEEKDAYS = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]

MAX_PHOTOS = 3


class ReportForm(StatesGroup):
    waiting_media = State()       # عکس اول یا پیام صوتی
    waiting_more_photos = State() # عکس‌های اضافی (اختیاری)
    waiting_location = State()
    waiting_category = State()
    waiting_description = State()
    confirm = State()


class QuizForm(StatesGroup):
    answering = State()


class SuggestionForm(StatesGroup):
    waiting_text = State()


class AskAIForm(StatesGroup):
    waiting_question = State()


class AppreciationForm(StatesGroup):
    waiting_text = State()


class BroadcastForm(StatesGroup):
    waiting_text = State()


def categories_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=label, callback_data=f"cat:{key}")]
        for key, label in CATEGORIES.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ ارسال گزارش", callback_data="confirm:yes")],
            [InlineKeyboardButton(text="🕵️ ارسال ناشناس", callback_data="confirm:anon")],
            [InlineKeyboardButton(text="❌ انصراف", callback_data="confirm:no")],
        ]
    )


def more_photos_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ کافیه، ادامه بده", callback_data="photos:done")],
        ]
    )


def admin_status_keyboard(report_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 در حال رسیدگی", callback_data=f"status:{report_id}:progress"),
                InlineKeyboardButton(text="✅ رسیدگی شد", callback_data=f"status:{report_id}:done"),
            ],
            [
                InlineKeyboardButton(text="🚫 غیرقابل بررسی", callback_data=f"status:{report_id}:rejected"),
            ],
        ]
    )


def feedback_keyboard(report_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👍 بله، برطرف شده", callback_data=f"feedback:{report_id}:yes"),
                InlineKeyboardButton(text="👎 خیر، هنوز هست", callback_data=f"feedback:{report_id}:no"),
            ],
        ]
    )


WEBSITE_URL = "https://mehditorkashvand1365.github.io/MalayerKhadanatShahri/"


def services_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 برنامه و زمان‌بندی خدمات", callback_data="info:schedule")],
            [InlineKeyboardButton(text="📰 فعالیت‌ها و پروژه‌های اخیر", callback_data="info:activities")],
            [InlineKeyboardButton(text="📋 شرح وظایف معاونت خدمات شهری", callback_data="info:duties")],
            [InlineKeyboardButton(text="🌐 مشاهده وب‌سایت خدمات شهری", url=WEBSITE_URL)],
        ]
    )


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📸 ثبت گزارش جدید", callback_data="menu:new_report")],
            [InlineKeyboardButton(text="📋 گزارش‌های من", callback_data="menu:myreports")],
            [InlineKeyboardButton(text="🏛 خدمات شهرداری", callback_data="menu:khadamat")],
            [InlineKeyboardButton(text="📚 آموزش شهروندی", callback_data="menu:amoozesh")],
            [InlineKeyboardButton(text="🎮 آزمون شهروند نمونه", callback_data="menu:quiz")],
            [InlineKeyboardButton(text="💡 پیشنهاد به شهرداری", callback_data="menu:pishnahad")],
            [InlineKeyboardButton(text="🙏 تشکر از عوامل خدمات شهری", callback_data="menu:appreciation")],
            [InlineKeyboardButton(text="🔔 اطلاعیه‌های مهم", callback_data="menu:subscribe")],
            [InlineKeyboardButton(text="🤖 پرسش هوشمند", callback_data="menu:ask_ai")],
            [InlineKeyboardButton(text="🌐 وب‌سایت خدمات شهری", url=WEBSITE_URL)],
            [InlineKeyboardButton(text="📊 آمار کلی گزارش‌ها", callback_data="menu:stats")],
        ]
    )


def subscribe_keyboard(is_subscribed: bool) -> InlineKeyboardMarkup:
    if is_subscribed:
        return InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔕 لغو اشتراک اطلاعیه‌ها", callback_data="sub:off")]]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔔 عضویت در اطلاعیه‌های مهم", callback_data="sub:on")]]
    )


def education_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=title, callback_data=f"edu:{key}")]
        for key, (title, _text) in EDUCATION_TOPICS.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def quiz_question_keyboard(q_index: int, options: list[str]) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=opt, callback_data=f"quiz:{q_index}:{i}")]
        for i, opt in enumerate(options)
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


location_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="📍 ارسال موقعیت مکانی", request_location=True)]],
    resize_keyboard=True,
    one_time_keyboard=True,
)

STATUS_MAP = {
    "progress": db.STATUS_IN_PROGRESS,
    "done": db.STATUS_DONE,
    "rejected": db.STATUS_REJECTED,
}

WELCOME_TEXT = (
    "🏛 <b>ربات گزارش‌دهی شهروندی</b>\n"
    "<b>معاونت خدمات شهری شهرداری ملایر</b>\n\n"
    "با سلام و احترام؛\n"
    "این ربات با هدف تسهیل ارتباط میان شهروندان گرامی و معاونت خدمات شهری "
    "راه‌اندازی شده است. از این پس می‌توانید گزارش‌های خود از قبیل زباله "
    "رهاشده، آسیب‌دیدگی فضای سبز، مشاهده سگ‌های بلاصاحب، مشاهده موش‌های "
    "فاضلابی، دفع غیراصولی نخاله‌های ساختمانی و موارد مشابه را به‌سرعت و "
    "بدون واسطه به شهرداری گزارش دهید.\n\n"
    "برای شروع، از گزینه‌های زیر استفاده کنید یا مستقیم یک عکس (یا پیام صوتی) از محل مورد "
    "نظر ارسال نمایید.\n\n"
    "مشارکت شما، گامی مؤثر در راستای شهری تمیزتر است. 🌿\n"
    "<i>(برای لغو در هر مرحله: /cancel)</i>"
)


async def send_welcome(target: Message, state: FSMContext) -> None:
    await state.clear()
    await target.answer(WELCOME_TEXT, reply_markup=main_menu_keyboard())
    await state.set_state(ReportForm.waiting_media)


async def send_myreports(target: Message, user_id: int) -> None:
    reports = db.get_reports_by_user(user_id, limit=5)
    if not reports:
        await target.answer("شما هنوز هیچ گزارشی ثبت نکرده‌اید. برای شروع /start را بزنید.")
        return

    lines = ["📋 آخرین گزارش‌های شما:\n"]
    reopen_buttons = []
    for r in reports:
        entry = (
            f"کد {db.report_code(r['id'])} — {r['category']}\n"
            f"وضعیت: {r['status']}"
        )
        if r["feedback"]:
            entry += f"\nبازخورد شما: {r['feedback']}"
        lines.append(entry + "\n")
        if r["status"] == db.STATUS_DONE:
            reopen_buttons.append(
                [InlineKeyboardButton(
                    text=f"🔓 هنوز حل نشده؟ ({db.report_code(r['id'])})",
                    callback_data=f"reopen:{r['id']}",
                )]
            )

    keyboard = InlineKeyboardMarkup(inline_keyboard=reopen_buttons) if reopen_buttons else None
    await target.answer("\n".join(lines), reply_markup=keyboard)


async def send_stats(target: Message) -> None:
    s = db.get_stats()
    text = (
        "📊 آمار کلی گزارش‌های شهروندی\n\n"
        f"مجموع گزارش‌های ثبت‌شده: {s['total']}\n"
        f"دریافت شد: {s['received']}\n"
        f"در حال رسیدگی: {s['in_progress']}\n"
        f"رسیدگی شد: {s['done']}\n"
        f"غیرقابل بررسی: {s['rejected']}"
    )
    await target.answer(text)


async def send_quiz_leaderboard(target: Message) -> None:
    board = db.get_quiz_leaderboard(limit=10)
    if not board:
        await target.answer("هنوز کسی تو آزمون شرکت نکرده. اولین نفر باش! /quiz")
        return
    lines = ["🏆 جدول امتیازات آزمون شهروند نمونه:\n"]
    for i, row in enumerate(board, start=1):
        lines.append(f"{i}. {row['user_name']} — {row['best_score']} از {row['total']}")
    await target.answer("\n".join(lines))


@router.message(Command("quiz_top"), F.chat.type == "private")
async def cmd_quiz_top(message: Message) -> None:
    await send_quiz_leaderboard(message)


@router.message(CommandStart(), F.chat.type == "private")
async def cmd_start(message: Message, state: FSMContext) -> None:
    await send_welcome(message, state)


@router.message(Command("cancel"), F.chat.type == "private")
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "عملیات لغو شد. برای شروع دوباره /start را بزنید.",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(Command("myreports"), F.chat.type == "private")
async def cmd_myreports(message: Message) -> None:
    await send_myreports(message, message.from_user.id)


@router.message(Command("stats"), F.chat.type == "private")
async def cmd_stats(message: Message) -> None:
    await send_stats(message)


@router.message(Command("search"))
async def cmd_search(message: Message) -> None:
    if message.chat.id != config.ADMIN_GROUP_ID:
        # این دستور فقط برای مسئولان در گروه ادمین است، چون جزئیات گزارش‌های
        # سایر شهروندان را نشان می‌دهد و نباید در چت خصوصی در دسترس باشد.
        return

    query = (message.text or "").split(maxsplit=1)
    if len(query) < 2 or not query[1].strip():
        await message.answer(
            "برای جست‌وجو، بعد از دستور یک کلمه بنویسید. مثال:\n"
            "/search زباله\n"
            "/search در حال رسیدگی"
        )
        return

    keyword = query[1].strip()
    results = db.search_reports(keyword)
    if not results:
        await message.answer(f"چیزی برای «{keyword}» پیدا نشد.")
        return

    lines = [f"🔎 نتایج جست‌وجو برای «{keyword}» ({len(results)} مورد):\n"]
    for r in results:
        lines.append(
            f"کد {db.report_code(r['id'])} — {r['category']}\n"
            f"وضعیت: {r['status']} | از: {r['user_name']}\n"
        )
    await message.answer("\n".join(lines))


@router.message(Command("export"))
async def cmd_export(message: Message, bot: Bot) -> None:
    if message.chat.id != config.ADMIN_GROUP_ID:
        return

    reports = db.get_all_reports()
    if not reports:
        await message.answer("هنوز هیچ گزارشی ثبت نشده.")
        return

    xlsx_bytes = export.build_report_workbook(reports)
    file = BufferedInputFile(xlsx_bytes, filename="گزارش‌های-شهروندی.xlsx")
    await bot.send_document(
        chat_id=message.chat.id,
        document=file,
        caption=f"📊 خروجی کامل گزارش‌ها ({len(reports)} مورد)",
    )


@router.message(Command("hotspots"))
async def cmd_hotspots(message: Message, bot: Bot) -> None:
    if message.chat.id != config.ADMIN_GROUP_ID:
        return

    clusters = db.get_hotspot_clusters(limit=5)
    if not clusters:
        await message.answer("در حال حاضر نقطه داغی (گزارش باز) وجود ندارد. 👍")
        return

    lines = ["🔥 نقاط داغ (پرتکرارترین محل‌های گزارش باز):\n"]
    for i, c in enumerate(clusters, start=1):
        lines.append(f"{i}. {c['count']} گزارش در این نزدیکی")
    await message.answer("\n".join(lines))

    for i, c in enumerate(clusters, start=1):
        await bot.send_location(
            chat_id=message.chat.id,
            latitude=c["latitude"],
            longitude=c["longitude"],
        )


@router.callback_query(F.data == "menu:new_report")
async def menu_new_report(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message is not None:
        await callback.message.answer(
            "برای ثبت گزارش جدید، یک عکس از محل مورد نظر بفرستید، "
            "یا اگه راحت‌ترید، یک پیام صوتی بفرستید و توضیح بدید."
        )
    await state.set_state(ReportForm.waiting_media)
    await callback.answer()


@router.callback_query(F.data == "menu:myreports")
async def menu_myreports(callback: CallbackQuery) -> None:
    if callback.message is not None:
        await send_myreports(callback.message, callback.from_user.id)
    await callback.answer()


@router.callback_query(F.data == "menu:stats")
async def menu_stats(callback: CallbackQuery) -> None:
    if callback.message is not None:
        await send_stats(callback.message)
    await callback.answer()


@router.message(Command("pishnahad"), F.chat.type == "private")
async def cmd_pishnahad(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(SuggestionForm.waiting_text)
    await message.answer(
        "💡 پیشنهادتون برای بهتر شدن خدمات شهری چیه؟\n"
        "همینجا بنویسید (این فرق داره با گزارش مشکل — اینجا برای ایده و پیشنهاده)."
    )


@router.callback_query(F.data == "menu:pishnahad")
async def menu_pishnahad(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(SuggestionForm.waiting_text)
    if callback.message is not None:
        await callback.message.answer(
            "💡 پیشنهادتون برای بهتر شدن خدمات شهری چیه؟\n"
            "همینجا بنویسید (این فرق داره با گزارش مشکل — اینجا برای ایده و پیشنهاده)."
        )
    await callback.answer()


@router.message(SuggestionForm.waiting_text, F.chat.type == "private", F.text)
async def process_suggestion(message: Message, state: FSMContext, bot: Bot) -> None:
    text = message.text.strip()
    if not text:
        await message.answer("لطفاً یک متن بنویسید.")
        return

    user = message.from_user
    db.save_suggestion(user.id, user.full_name, text)

    try:
        await bot.send_message(
            chat_id=config.ADMIN_GROUP_ID,
            text=(
                "💡 پیشنهاد جدید شهروندی\n\n"
                f"{text}\n\n"
                f"از طرف: {user.full_name} (@{user.username or '-'})"
            ),
        )
    except Exception:
        pass

    await state.clear()
    await message.answer("پیشنهادتون ثبت و برای شهرداری ارسال شد. ممنون از مشارکتتون 🙏")


@router.message(SuggestionForm.waiting_text, F.chat.type == "private")
async def suggestion_invalid(message: Message) -> None:
    await message.answer("لطفاً پیشنهادتون رو به‌صورت متن بنویسید.")


@router.message(Command("ask"), F.chat.type == "private")
async def cmd_ask(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AskAIForm.waiting_question)
    await message.answer("🤖 سؤالتون رو درباره خدمات شهری یا نحوه کار ربات بپرسید.")


@router.callback_query(F.data == "menu:ask_ai")
async def menu_ask_ai(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AskAIForm.waiting_question)
    if callback.message is not None:
        await callback.message.answer("🤖 سؤالتون رو درباره خدمات شهری یا نحوه کار ربات بپرسید.")
    await callback.answer()


@router.message(AskAIForm.waiting_question, F.chat.type == "private", F.text)
async def process_ai_question(message: Message, state: FSMContext) -> None:
    question = message.text.strip()
    if not question:
        await message.answer("لطفاً یک سؤال بنویسید.")
        return

    thinking_msg = await message.answer("در حال بررسی... ⏳")

    system_prompt = ai_assistant.build_system_prompt(DUTIES_TEXT, list(CATEGORIES.values()))
    answer = await ai_assistant.ask_ai(question, config.DEEPSEEK_API_KEY, system_prompt)

    await thinking_msg.edit_text(answer)
    await state.clear()


@router.message(AskAIForm.waiting_question, F.chat.type == "private")
async def ai_question_invalid(message: Message) -> None:
    await message.answer("لطفاً سؤالتون رو به‌صورت متن بنویسید.")


@router.message(Command("subscribe"), F.chat.type == "private")
async def cmd_subscribe(message: Message) -> None:
    db.subscribe_user(message.from_user.id, message.from_user.full_name)
    await message.answer(
        "🔔 عضو اطلاعیه‌های مهم شهرداری شدید (قطعی آب، اطلاعیه‌های اضطراری و...).\n"
        "برای لغو در هر زمان، دستور /unsubscribe را بزنید."
    )


@router.message(Command("unsubscribe"), F.chat.type == "private")
async def cmd_unsubscribe(message: Message) -> None:
    db.unsubscribe_user(message.from_user.id)
    await message.answer("🔕 اشتراک شما از اطلاعیه‌های مهم لغو شد.")


@router.callback_query(F.data == "menu:subscribe")
async def menu_subscribe(callback: CallbackQuery) -> None:
    subscribed = db.is_subscribed(callback.from_user.id)
    if callback.message is not None:
        text = (
            "شما الان مشترک اطلاعیه‌های مهم شهرداری هستید. می‌خواهید لغو کنید؟"
            if subscribed
            else "با عضویت، اطلاعیه‌های مهم و فوری (قطعی آب، اطلاعیه‌های اضطراری و...) را مستقیم دریافت می‌کنید."
        )
        await callback.message.answer(text, reply_markup=subscribe_keyboard(subscribed))
    await callback.answer()


@router.callback_query(F.data == "sub:on")
async def sub_on(callback: CallbackQuery) -> None:
    db.subscribe_user(callback.from_user.id, callback.from_user.full_name)
    if callback.message is not None:
        await callback.message.edit_text("🔔 عضو اطلاعیه‌های مهم شدید.")
    await callback.answer()


@router.callback_query(F.data == "sub:off")
async def sub_off(callback: CallbackQuery) -> None:
    db.unsubscribe_user(callback.from_user.id)
    if callback.message is not None:
        await callback.message.edit_text("🔕 اشتراک شما لغو شد.")
    await callback.answer()


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext) -> None:
    if message.chat.id != config.ADMIN_GROUP_ID:
        return
    await state.clear()
    await state.set_state(BroadcastForm.waiting_text)
    subscriber_count = db.count_subscribers()
    await message.answer(
        f"📢 متن اطلاعیه را بفرستید تا برای {subscriber_count} مشترک ارسال شود.\n"
        "برای لغو، /cancel را بزنید."
    )


@router.message(BroadcastForm.waiting_text, F.text)
async def process_broadcast(message: Message, state: FSMContext, bot: Bot) -> None:
    if message.chat.id != config.ADMIN_GROUP_ID:
        return

    text = message.text.strip()
    subscribers = db.get_all_subscribers()
    sent = 0
    failed = 0
    for sub in subscribers:
        try:
            await bot.send_message(
                chat_id=sub["user_id"],
                text=f"📢 اطلاعیه مهم شهرداری ملایر\n\n{text}",
            )
            sent += 1
        except Exception:
            failed += 1

    await state.clear()
    await message.answer(f"ارسال شد ✅ موفق: {sent} | ناموفق: {failed}")


@router.message(Command("tashakor"), F.chat.type == "private")
async def cmd_appreciation(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AppreciationForm.waiting_text)
    await message.answer(
        "🙏 از کدوم تیم یا نقطه شهر می‌خواید تشکر کنید؟ کوتاه بنویسید."
    )


@router.callback_query(F.data == "menu:appreciation")
async def menu_appreciation(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AppreciationForm.waiting_text)
    if callback.message is not None:
        await callback.message.answer(
            "🙏 از کدوم تیم یا نقطه شهر می‌خواید تشکر کنید؟ کوتاه بنویسید."
        )
    await callback.answer()


@router.message(AppreciationForm.waiting_text, F.chat.type == "private", F.text)
async def process_appreciation(message: Message, state: FSMContext, bot: Bot) -> None:
    text = message.text.strip()
    if not text:
        await message.answer("لطفاً یک متن بنویسید.")
        return

    user = message.from_user
    db.save_appreciation(user.id, user.full_name, text)

    try:
        await bot.send_message(
            chat_id=config.ADMIN_GROUP_ID,
            text=(
                "🙏 تشکر از شهروند\n\n"
                f"{text}\n\n"
                f"از طرف: {user.full_name} (@{user.username or '-'})"
            ),
        )
    except Exception:
        pass

    await state.clear()
    await message.answer("پیام تشکرتون ثبت و به شهرداری منتقل شد 🌿")


@router.message(AppreciationForm.waiting_text, F.chat.type == "private")
async def appreciation_invalid(message: Message) -> None:
    await message.answer("لطفاً پیام تشکرتون رو به‌صورت متن بنویسید.")


@router.message(Command("khadamat"), F.chat.type == "private")
async def cmd_khadamat(message: Message) -> None:
    await message.answer(
        "اطلاعات خدمات شهری را انتخاب کنید:",
        reply_markup=services_menu_keyboard(),
    )


@router.message(Command("amoozesh"), F.chat.type == "private")
async def cmd_amoozesh(message: Message) -> None:
    await message.answer(
        "موضوع مورد نظر رو انتخاب کن:",
        reply_markup=education_menu_keyboard(),
    )


@router.callback_query(F.data == "menu:khadamat")
async def menu_khadamat(callback: CallbackQuery) -> None:
    if callback.message is not None:
        await callback.message.answer(
            "اطلاعات خدمات شهری را انتخاب کنید:",
            reply_markup=services_menu_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data == "menu:amoozesh")
async def menu_amoozesh(callback: CallbackQuery) -> None:
    if callback.message is not None:
        await callback.message.answer(
            "موضوع مورد نظر رو انتخاب کن:",
            reply_markup=education_menu_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data == "info:schedule")
async def info_schedule(callback: CallbackQuery) -> None:
    if callback.message is not None:
        await callback.message.answer(SCHEDULE_TEXT)
    await callback.answer()


@router.callback_query(F.data == "info:activities")
async def info_activities(callback: CallbackQuery) -> None:
    if callback.message is not None:
        await callback.message.answer(ACTIVITIES_TEXT)
    await callback.answer()


@router.callback_query(F.data == "info:duties")
async def info_duties(callback: CallbackQuery) -> None:
    if callback.message is not None:
        await callback.message.answer(DUTIES_TEXT)
    await callback.answer()


@router.callback_query(F.data.startswith("edu:"))
async def show_education_topic(callback: CallbackQuery) -> None:
    key = callback.data.split(":", 1)[1]
    topic = EDUCATION_TOPICS.get(key)
    if topic is None:
        await callback.answer("این موضوع پیدا نشد.", show_alert=True)
        return
    _title, text = topic
    if callback.message is not None:
        await callback.message.answer(text)
    await callback.answer()


async def send_quiz_question(target: Message, state: FSMContext, q_index: int) -> None:
    if q_index >= len(QUIZ_QUESTIONS):
        data = await state.get_data()
        score = data.get("quiz_score", 0)
        total = len(QUIZ_QUESTIONS)
        result_line = get_result_message(score, total)
        share_text = (
            f"من تو آزمون شهروند نمونه ملایر {score} از {total} امتیاز گرفتم! "
            "تو چند می‌گیری؟ 👉 @GozareshShahrvandi_bot"
        )
        await target.answer(
            f"🏁 آزمون تموم شد!\n\n"
            f"امتیاز تو: {score} از {total}\n"
            f"{result_line}\n\n"
            f"می‌تونی این نتیجه رو با دوستات هم به اشتراک بذاری:\n\n"
            f"{share_text}"
        )
        user = target.chat
        db.save_quiz_result(user.id, user.full_name or "کاربر", score, total)
        await state.clear()
        return

    q = QUIZ_QUESTIONS[q_index]
    await state.update_data(quiz_index=q_index)
    await target.answer(
        f"سؤال {q_index + 1} از {len(QUIZ_QUESTIONS)}\n\n{q['question']}",
        reply_markup=quiz_question_keyboard(q_index, q["options"]),
    )


@router.message(Command("quiz"), F.chat.type == "private")
async def cmd_quiz(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(quiz_score=0)
    await state.set_state(QuizForm.answering)
    await send_quiz_question(message, state, 0)


@router.callback_query(F.data == "menu:quiz")
async def menu_quiz(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(quiz_score=0)
    await state.set_state(QuizForm.answering)
    if callback.message is not None:
        await send_quiz_question(callback.message, state, 0)
    await callback.answer()


@router.callback_query(QuizForm.answering, F.data.startswith("quiz:"))
async def quiz_answer(callback: CallbackQuery, state: FSMContext) -> None:
    _, q_index_str, option_index_str = callback.data.split(":")
    q_index = int(q_index_str)
    option_index = int(option_index_str)

    data = await state.get_data()
    current_index = data.get("quiz_index")
    if current_index != q_index:
        # این دکمه مال یه سؤال قدیمی‌تره (کاربر شاید دوباره روش زده)
        await callback.answer("این سؤال قبلاً پاسخ داده شده.", show_alert=True)
        return

    q = QUIZ_QUESTIONS[q_index]
    is_correct = option_index == q["correct_index"]
    score = data.get("quiz_score", 0)
    if is_correct:
        score += 1
        await state.update_data(quiz_score=score)

    feedback = "✅ درسته!" if is_correct else f"❌ نه، جواب درست: {q['options'][q['correct_index']]}"
    if callback.message is not None:
        await callback.message.edit_text(f"{q['question']}\n\n{feedback}\n\n{q['explanation']}")
        await send_quiz_question(callback.message, state, q_index + 1)
    await callback.answer()


@router.message(QuizForm.answering, F.chat.type == "private")
async def quiz_waiting_for_button(message: Message) -> None:
    await message.answer("لطفاً یکی از گزینه‌های بالا رو با لمس‌کردن انتخاب کن.")


@router.message(ReportForm.waiting_media, F.photo, F.chat.type == "private")
async def process_first_photo(message: Message, state: FSMContext) -> None:
    photo_file_id = message.photo[-1].file_id
    await state.update_data(photos=[photo_file_id], voice_file_id=None)
    await message.answer(
        "عکس دریافت شد ✅\n"
        f"می‌تونید تا {MAX_PHOTOS} عکس بفرستید، یا همین یکی کافیه.",
        reply_markup=more_photos_keyboard(),
    )
    await state.set_state(ReportForm.waiting_more_photos)


@router.message(ReportForm.waiting_media, F.voice, F.chat.type == "private")
async def process_voice(message: Message, state: FSMContext) -> None:
    await state.update_data(photos=[], voice_file_id=message.voice.file_id)
    await message.answer(
        "پیام صوتی دریافت شد ✅\nحالا لطفاً موقعیت مکانی محل را با دکمه زیر ارسال کنید.",
        reply_markup=location_keyboard,
    )
    await state.set_state(ReportForm.waiting_location)


@router.message(ReportForm.waiting_media, F.chat.type == "private")
async def media_missing(message: Message) -> None:
    await message.answer("لطفاً یک عکس یا یک پیام صوتی از محل ارسال کنید.")


@router.message(ReportForm.waiting_more_photos, F.photo, F.chat.type == "private")
async def process_more_photos(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    photos = data.get("photos", [])
    if len(photos) >= MAX_PHOTOS:
        await message.answer(
            f"به سقف {MAX_PHOTOS} عکس رسیدید. برای ادامه، دکمه «کافیه، ادامه بده» را بزنید.",
            reply_markup=more_photos_keyboard(),
        )
        return
    photos.append(message.photo[-1].file_id)
    await state.update_data(photos=photos)
    if len(photos) >= MAX_PHOTOS:
        await message.answer(
            f"عکس {len(photos)} دریافت شد ✅ (به سقف {MAX_PHOTOS} عکس رسیدید)\n"
            "حالا لطفاً موقعیت مکانی محل را با دکمه زیر ارسال کنید.",
            reply_markup=location_keyboard,
        )
        await state.set_state(ReportForm.waiting_location)
    else:
        await message.answer(
            f"عکس {len(photos)} دریافت شد ✅ می‌تونید یکی دیگه بفرستید یا ادامه بدید.",
            reply_markup=more_photos_keyboard(),
        )


@router.callback_query(ReportForm.waiting_more_photos, F.data == "photos:done")
async def more_photos_done(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is not None:
        await callback.message.answer(
            "لطفاً موقعیت مکانی محل را با دکمه زیر ارسال کنید.",
            reply_markup=location_keyboard,
        )
    await state.set_state(ReportForm.waiting_location)
    await callback.answer()


@router.message(ReportForm.waiting_more_photos, F.chat.type == "private")
async def more_photos_invalid(message: Message) -> None:
    await message.answer(
        "یک عکس دیگه بفرستید، یا دکمه «کافیه، ادامه بده» رو بزنید.",
        reply_markup=more_photos_keyboard(),
    )


@router.message(ReportForm.waiting_location, F.location, F.chat.type == "private")
async def process_location(message: Message, state: FSMContext) -> None:
    await state.update_data(
        latitude=message.location.latitude,
        longitude=message.location.longitude,
    )
    await message.answer("موقعیت مکانی دریافت شد ✅", reply_markup=ReplyKeyboardRemove())
    await message.answer("دسته‌بندی گزارش را انتخاب کنید:", reply_markup=categories_keyboard())
    await state.set_state(ReportForm.waiting_category)


@router.message(ReportForm.waiting_location, F.chat.type == "private")
async def location_missing(message: Message) -> None:
    await message.answer("لطفاً از دکمه «ارسال موقعیت مکانی» استفاده کنید.")


@router.callback_query(ReportForm.waiting_category, F.data.startswith("cat:"))
async def process_category(callback: CallbackQuery, state: FSMContext) -> None:
    key = callback.data.split(":", 1)[1]
    label = CATEGORIES.get(key, "سایر")
    is_social = key in SOCIAL_REFERRAL_CATEGORY_KEYS
    await state.update_data(category=label, is_social=is_social)

    if callback.message is not None:
        if is_social:
            await callback.message.answer(
                "متشکریم که به فکر این موضوع هستید 🙏\n\n"
                "لطفاً در توضیحات فقط به شرایط و مکان اشاره کنید (نه جزئیات "
                "هویتی فرد) تا با احترام به کرامت ایشان، مورد به نهاد حمایتی "
                "مربوطه ارجاع داده شود. اگر توضیحی ندارید، بنویسید «ندارد»."
            )
        else:
            await callback.message.answer(
                "در صورت تمایل توضیح کوتاهی درباره محل بنویسید، یا بنویسید «ندارد»."
            )
    await state.set_state(ReportForm.waiting_description)
    await callback.answer()


@router.message(ReportForm.waiting_description, F.chat.type == "private")
async def process_description(message: Message, state: FSMContext) -> None:
    await state.update_data(description=message.text or "ندارد")
    data = await state.get_data()
    is_social = data.get("is_social", False)

    if is_social:
        summary = (
            "📋 خلاصه مورد شما:\n\n"
            f"دسته‌بندی: {data['category']}\n"
            f"توضیحات: {data['description']}\n"
            "موقعیت مکانی و عکس: ثبت شد\n\n"
            "این مورد برای پیگیری به نهاد حمایتی مرتبط ارجاع داده می‌شود. آیا ارسال شود؟"
        )
    else:
        summary = (
            "📋 خلاصه گزارش شما:\n\n"
            f"دسته‌بندی: {data['category']}\n"
            f"توضیحات: {data['description']}\n"
            "موقعیت مکانی و عکس: ثبت شد\n\n"
            "آیا این گزارش برای شهرداری ارسال شود؟"
        )
    await message.answer(summary, reply_markup=confirm_keyboard())
    await state.set_state(ReportForm.confirm)


async def submit_report(callback: CallbackQuery, state: FSMContext, bot: Bot, is_anonymous: bool) -> None:
    data = await state.get_data()
    user = callback.from_user
    is_social = data.get("is_social", False)
    photos: list[str] = data.get("photos", [])
    voice_file_id = data.get("voice_file_id")

    report_id = db.create_report(
        user_id=user.id,
        user_name=user.full_name,
        category=data.get("category", "نامشخص"),
        description=data.get("description", "ندارد"),
        latitude=data["latitude"],
        longitude=data["longitude"],
        photo_file_id=photos[0] if photos else "",
        extra_photos=photos[1:] if len(photos) > 1 else None,
        voice_file_id=voice_file_id,
        is_anonymous=is_anonymous,
    )
    code = db.report_code(report_id)
    from_line = "شهروند ناشناس 🕵️" if is_anonymous else f"{user.full_name} (@{user.username or '-'})"

    if is_social:
        caption = (
            f"🆘 مورد نیازمند ارجاع به کمک اجتماعی — {code}\n\n"
            f"توضیحات: {data.get('description', 'ندارد')}\n"
            f"از طرف: {from_line}\n"
            f"وضعیت: {db.STATUS_RECEIVED}\n\n"
            "لطفاً برای پیگیری با نهاد حمایتی/بهزیستی هماهنگ شود."
        )
    else:
        caption = (
            f"🆕 گزارش جدید شهروندی — {code}\n\n"
            f"دسته‌بندی: {data.get('category', 'نامشخص')}\n"
            f"توضیحات: {data.get('description', 'ندارد')}\n"
            f"از طرف: {from_line}\n"
            f"وضعیت: {db.STATUS_RECEIVED}"
        )

    # ارسال رسانه (عکس‌ها یا پیام صوتی) بدون کپشن/دکمه — کپشن و دکمه‌ها در یک پیام جدا می‌آیند
    if voice_file_id:
        await bot.send_voice(chat_id=config.ADMIN_GROUP_ID, voice=voice_file_id)
    elif len(photos) > 1:
        media_group = [InputMediaPhoto(media=p) for p in photos]
        await bot.send_media_group(chat_id=config.ADMIN_GROUP_ID, media=media_group)
    elif len(photos) == 1:
        await bot.send_photo(chat_id=config.ADMIN_GROUP_ID, photo=photos[0])

    await bot.send_location(
        chat_id=config.ADMIN_GROUP_ID,
        latitude=data["latitude"],
        longitude=data["longitude"],
    )

    sent_caption = await bot.send_message(
        chat_id=config.ADMIN_GROUP_ID,
        text=caption,
        reply_markup=admin_status_keyboard(report_id),
    )
    db.set_admin_message(report_id, sent_caption.chat.id, sent_caption.message_id)

    if callback.message is not None:
        if is_social:
            await callback.message.edit_text(
                "مورد شما با موفقیت ثبت و برای پیگیری ارسال شد. ✅\n"
                f"کد پیگیری: {code}\n\n"
                f"در صورت نیاز فوری، می‌توانید مستقیم با خط اورژانس اجتماعی "
                f"تماس بگیرید: {SOCIAL_HELP_HOTLINE}\n\n"
                "از توجه و مسئولیت‌پذیری‌تان سپاسگزاریم 🙏\n"
                "برای ثبت مورد جدید، دستور /start را بزنید."
            )
        else:
            report_count = db.count_reports_by_user(user.id)
            milestone_note = f"\n\nاین {report_count}اُمین گزارش شماست 🌟" if report_count > 1 else ""
            anon_note = "\n(به‌صورت ناشناس ثبت شد 🕵️)" if is_anonymous else ""
            await callback.message.edit_text(
                "گزارش شما با موفقیت ثبت و برای شهرداری ارسال شد. ✅\n"
                f"کد پیگیری گزارش شما: {code}"
                f"{anon_note}\n"
                "می‌توانید وضعیت آن را بعداً با دستور /myreports ببینید."
                f"{milestone_note}\n\n"
                "از مشارکت شما در پاکیزگی شهر سپاسگزاریم 🙏\n"
                "برای ثبت گزارش جدید، دستور /start را بزنید."
            )
    await state.clear()
    await callback.answer()


@router.callback_query(ReportForm.confirm, F.data == "confirm:yes")
async def confirm_yes(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await submit_report(callback, state, bot, is_anonymous=False)


@router.callback_query(ReportForm.confirm, F.data == "confirm:anon")
async def confirm_anonymous(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await submit_report(callback, state, bot, is_anonymous=True)


@router.callback_query(ReportForm.confirm, F.data == "confirm:no")
async def confirm_no(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is not None:
        await callback.message.edit_text("گزارش لغو شد. برای شروع مجدد /start را بزنید.")
    await state.clear()
    await callback.answer()


@router.callback_query(F.data.startswith("status:"))
async def admin_update_status(callback: CallbackQuery, bot: Bot) -> None:
    _, report_id_str, status_key = callback.data.split(":")
    report_id = int(report_id_str)
    new_status = STATUS_MAP.get(status_key)
    if new_status is None:
        await callback.answer("وضعیت نامعتبر است.", show_alert=True)
        return

    report = db.get_report(report_id)
    if report is None:
        await callback.answer("این گزارش پیدا نشد.", show_alert=True)
        return

    db.update_status(report_id, new_status)

    # به‌روزرسانی متن پیام در گروه ادمین
    if callback.message is not None:
        code = db.report_code(report_id)
        is_social_report = report["category"] == CATEGORIES.get("social_help")
        from_line = "شهروند ناشناس 🕵️" if report["is_anonymous"] else report["user_name"]
        if is_social_report:
            new_caption = (
                f"🆘 مورد نیازمند ارجاع به کمک اجتماعی — {code}\n\n"
                f"توضیحات: {report['description']}\n"
                f"از طرف: {from_line}\n"
                f"وضعیت: {new_status}\n\n"
                "لطفاً برای پیگیری با نهاد حمایتی/بهزیستی هماهنگ شود."
            )
        else:
            new_caption = (
                f"🆕 گزارش جدید شهروندی — {code}\n\n"
                f"دسته‌بندی: {report['category']}\n"
                f"توضیحات: {report['description']}\n"
                f"از طرف: {from_line}\n"
                f"وضعیت: {new_status}"
            )
        await callback.message.edit_text(
            new_caption,
            reply_markup=admin_status_keyboard(report_id),
        )

    # اطلاع‌رسانی خودکار به شهروند
    try:
        await bot.send_message(
            chat_id=report["user_id"],
            text=(
                f"🔔 وضعیت گزارش شما (کد {db.report_code(report_id)}) به‌روزرسانی شد:\n"
                f"وضعیت جدید: {new_status}"
            ),
        )
        if new_status == db.STATUS_DONE:
            await bot.send_message(
                chat_id=report["user_id"],
                text="آیا مشکل واقعاً برطرف شده؟ نظر شما به بهبود کیفیت خدمات کمک می‌کند 🙏",
                reply_markup=feedback_keyboard(report_id),
            )
    except Exception:
        # کاربر ممکن است ربات را مسدود کرده باشد؛ خطا را نادیده می‌گیریم
        pass

    await callback.answer("وضعیت با موفقیت به‌روزرسانی شد ✅")


@router.callback_query(F.data.startswith("feedback:"))
async def citizen_feedback(callback: CallbackQuery, bot: Bot) -> None:
    _, report_id_str, answer = callback.data.split(":")
    report_id = int(report_id_str)

    report = db.get_report(report_id)
    if report is None:
        await callback.answer("این گزارش پیدا نشد.", show_alert=True)
        return

    feedback_label = "مشکل برطرف شده ✅" if answer == "yes" else "مشکل هنوز برطرف نشده ❌"
    db.set_feedback(report_id, feedback_label)

    if callback.message is not None:
        await callback.message.edit_text(
            f"متشکریم از بازخوردتان 🙏\nثبت شد: {feedback_label}"
        )
    await callback.answer()

    # بازخورد شهروند (چه مثبت چه منفی) را برای گروه ادمین هم ارسال کن
    if report["admin_chat_id"] and report["admin_message_id"]:
        weekday_name = PERSIAN_WEEKDAYS[datetime.now().weekday()]
        if answer == "no":
            admin_text = (
                "❌ مشکل موجود کماکان برطرف نشده و نیاز به بررسی مجدد دارد\n"
                f"روز بازخورد: {weekday_name}"
            )
        else:
            admin_text = (
                "✅ مشکل موجود توسط عوامل مربوطه رسیدگی و رفع شد\n"
                f"روز بازخورد: {weekday_name}"
            )
        try:
            await bot.send_message(
                chat_id=report["admin_chat_id"],
                text=admin_text,
                reply_to_message_id=report["admin_message_id"],
            )
        except Exception:
            pass


@router.callback_query(F.data.startswith("reopen:"))
async def reopen_report_handler(callback: CallbackQuery, bot: Bot) -> None:
    report_id = int(callback.data.split(":")[1])
    report = db.get_report(report_id)
    if report is None:
        await callback.answer("این گزارش پیدا نشد.", show_alert=True)
        return
    if report["user_id"] != callback.from_user.id:
        await callback.answer("این گزارش مال شما نیست.", show_alert=True)
        return
    if report["status"] != db.STATUS_DONE:
        await callback.answer("این گزارش در وضعیت «رسیدگی شد» نیست.", show_alert=True)
        return

    db.reopen_report(report_id)
    code = db.report_code(report_id)

    if callback.message is not None:
        await callback.message.answer(
            f"گزارش {code} دوباره باز شد و برای بررسی مجدد به شهرداری ارسال شد. 🔓"
        )
    await callback.answer()

    # به‌روزرسانی پیام اصلی در گروه ادمین (اگر هنوز موجود باشد)
    if report["admin_chat_id"] and report["admin_message_id"]:
        is_social_report = report["category"] == CATEGORIES.get("social_help")
        from_line = "شهروند ناشناس 🕵️" if report["is_anonymous"] else report["user_name"]
        if is_social_report:
            new_caption = (
                f"🆘 مورد نیازمند ارجاع به کمک اجتماعی — {code}\n\n"
                f"توضیحات: {report['description']}\n"
                f"از طرف: {from_line}\n"
                f"وضعیت: {db.STATUS_RECEIVED}\n\n"
                "لطفاً برای پیگیری با نهاد حمایتی/بهزیستی هماهنگ شود."
            )
        else:
            new_caption = (
                f"🆕 گزارش جدید شهروندی — {code}\n\n"
                f"دسته‌بندی: {report['category']}\n"
                f"توضیحات: {report['description']}\n"
                f"از طرف: {from_line}\n"
                f"وضعیت: {db.STATUS_RECEIVED}"
            )
        try:
            await bot.edit_message_text(
                chat_id=report["admin_chat_id"],
                message_id=report["admin_message_id"],
                text=new_caption,
                reply_markup=admin_status_keyboard(report_id),
            )
            await bot.send_message(
                chat_id=report["admin_chat_id"],
                text=f"🔓 شهروند اعلام کرده گزارش {code} هنوز حل نشده و دوباره باز شد.",
                reply_to_message_id=report["admin_message_id"],
            )
        except Exception:
            pass


@router.message(F.chat.type == "private")
async def fallback(message: Message) -> None:
    await message.answer(
        "برای شروع ثبت گزارش جدید، دستور /start را بزنید.\n"
        "برای دیدن وضعیت گزارش‌های قبلی، دستور /myreports را بزنید."
    )
