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
PERSIAN_WEEKDAYS = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]
MAX_PHOTOS = 3

class ReportForm(StatesGroup):
    waiting_media = State()
    waiting_more_photos = State()
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
    buttons = [[InlineKeyboardButton(text=label, callback_data=f"cat:{key}")] for key, label in CATEGORIES.items()]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ارسال گزارش", callback_data="confirm:yes")],
        [InlineKeyboardButton(text="🕵️ ارسال ناشناس", callback_data="confirm:anon")],
        [InlineKeyboardButton(text="❌ انصراف", callback_data="confirm:no")],
    ])

def more_photos_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ کافیه، ادامه بده", callback_data="photos:done")]])

def admin_status_keyboard(report_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 در حال رسیدگی", callback_data=f"status:{report_id}:progress"), InlineKeyboardButton(text="✅ رسیدگی شد", callback_data=f"status:{report_id}:done")],
        [InlineKeyboardButton(text="🚫 غیرقابل بررسی", callback_data=f"status:{report_id}:rejected")],
    ])

def feedback_keyboard(report_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👍 بله، برطرف شده", callback_data=f"feedback:{report_id}:yes"), InlineKeyboardButton(text="👎 خیر، هنوز هست", callback_data=f"feedback:{report_id}:no")]])

WEBSITE_URL = "https://mehditorkashvand1365.github.io/MalayerKhadanatShahri/"

def services_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 برنامه و زمان‌بندی خدمات", callback_data="info:schedule")],
        [InlineKeyboardButton(text="📰 فعالیت‌ها و پروژه‌های اخیر", callback_data="info:activities")],
        [InlineKeyboardButton(text="📋 شرح وظایف معاونت خدمات شهری", callback_data="info:duties")],
        [InlineKeyboardButton(text="🌐 مشاهده وب‌سایت خدمات شهری", url=WEBSITE_URL)],
    ])

def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📸 ثبت گزارش جدید", callback_data="menu:new_report")],
        [InlineKeyboardButton(text="📋 گزارش‌های من", callback_data="menu:myreports")],
        [InlineKeyboardButton(text="📊 نظرسنجی شهروندی", callback_data="menu:survey")],
        [InlineKeyboardButton(text="🏛 خدمات شهرداری", callback_data="menu:khadamat")],
        [InlineKeyboardButton(text="📚 آموزش شهروندی", callback_data="menu:amoozesh")],
        [InlineKeyboardButton(text="🎮 آزمون شهروند نمونه", callback_data="menu:quiz")],
        [InlineKeyboardButton(text="💡 پیشنهاد به شهرداری", callback_data="menu:pishnahad")],
        [InlineKeyboardButton(text="🙏 تشکر از عوامل خدمات شهری", callback_data="menu:appreciation")],
        [InlineKeyboardButton(text="🔔 اطلاعیه‌های مهم", callback_data="menu:subscribe")],
        [InlineKeyboardButton(text="🤖 پرسش هوشمند", callback_data="menu:ask_ai")],
        [InlineKeyboardButton(text="🌐 وب‌سایت خدمات شهری", url=WEBSITE_URL)],
        [InlineKeyboardButton(text="📊 آمار کلی گزارش‌ها", callback_data="menu:stats")],
    ])

def subscribe_keyboard(is_subscribed: bool) -> InlineKeyboardMarkup:
    if is_subscribed:
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔕 لغو اشتراک اطلاعیه‌های مهم", callback_data="sub:off")]])
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔔 عضویت در اطلاعیه‌های مهم", callback_data="sub:on")]])

def education_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=title, callback_data=f"edu:{key}")] for key, (title, _text) in EDUCATION_TOPICS.items()])

def quiz_question_keyboard(q_index: int, options: list[str]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=opt, callback_data=f"quiz:{q_index}:{i}")] for i, opt in enumerate(options)])

location_keyboard = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📍 ارسال موقعیت مکانی", request_location=True)]], resize_keyboard=True, one_time_keyboard=True)
STATUS_MAP = {"progress": db.STATUS_IN_PROGRESS, "done": db.STATUS_DONE, "rejected": db.STATUS_REJECTED}

WELCOME_TEXT = ("🏛 <b>ربات گزارش‌دهی شهروندی</b>\n<b>معاونت خدمات شهری شهرداری ملایر</b>\n\n"
"با سلام و احترام؛\nاین ربات با هدف تسهیل ارتباط میان شهروندان گرامی و معاونت خدمات شهری راه‌اندازی شده است. از این پس می‌توانید گزارش‌های خود از قبیل زباله رهاشده، آسیب‌دیدگی فضای سبز، مشاهده سگ‌های بلاصاحب، مشاهده موش‌های فاضلابی، دفع غیراصولی نخاله‌های ساختمانی و موارد مشابه را به‌سرعت و بدون واسطه به شهرداری گزارش دهید.\n\n"
"برای شروع، از گزینه‌های زیر استفاده کنید یا مستقیم یک عکس (یا پیام صوتی) از محل مورد نظر ارسال نمایید.\n\nمشارکت شما، گامی مؤثر در راستای شهری تمیزتر است. 🌿\n<i>(برای لغو در هر مرحله: /cancel)</i>")

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
        entry = f"کد {db.report_code(r['id'])} — {r['category']}\nوضعیت: {r['status']}"
        if r["feedback"]:
            entry += f"\nبازخورد شما: {r['feedback']}"
        lines.append(entry + "\n")
        if r["status"] == db.STATUS_DONE:
            reopen_buttons.append([InlineKeyboardButton(text=f"🔓 هنوز حل نشده؟ ({db.report_code(r['id'])})", callback_data=f"reopen:{r['id']}")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=reopen_buttons) if reopen_buttons else None
    await target.answer("\n".join(lines), reply_markup=keyboard)

async def send_stats(target: Message) -> None:
    s = db.get_stats()
    await target.answer(f"📊 آمار کلی گزارش‌های شهروندی\n\nمجموع گزارش‌های ثبت‌شده: {s['total']}\nدریافت شد: {s['received']}\nدر حال رسیدگی: {s['in_progress']}\nرسیدگی شد: {s['done']}\nغیرقابل بررسی: {s['rejected']}")

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
    await message.answer("عملیات لغو شد. برای شروع دوباره /start را بزنید.", reply_markup=ReplyKeyboardRemove())

@router.message(Command("myreports"), F.chat.type == "private")
async def cmd_myreports(message: Message) -> None:
    await send_myreports(message, message.from_user.id)

@router.message(Command("stats"), F.chat.type == "private")
async def cmd_stats(message: Message) -> None:
    await send_stats(message)

@router.message(Command("search"))
async def cmd_search(message: Message) -> None:
    if message.chat.id != config.ADMIN_GROUP_ID:
        return
    query = (message.text or "").split(maxsplit=1)
    if len(query) < 2 or not query[1].strip():
        await message.answer("برای جست‌وجو، بعد از دستور یک کلمه بنویسید. مثال:\n/search زباله\n/search در حال رسیدگی")
        return
    keyword = query[1].strip()
    results = db.search_reports(keyword)
    if not results:
        await message.answer(f"چیزی برای «{keyword}» پیدا نشد.")
        return
    lines = [f"🔎 نتایج جست‌وجو برای «{keyword}» ({len(results)} مورد):\n"]
    for r in results:
        lines.append(f"کد {db.report_code(r['id'])} — {r['category']}\nوضعیت: {r['status']} | از: {r['user_name']}\n")
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
    await bot.send_document(chat_id=message.chat.id, document=file, caption=f"📊 خروجی کامل گزارش‌ها ({len(reports)} مورد)")

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
    for c in clusters:
        map_url = f"https://www.google.com/maps?q={c['latitude']:.6f},{c['longitude']:.6f}"
        await message.answer(f"📍 {c['count']} گزارش نزدیک این نقطه:\n{map_url}")

@router.callback_query(F.data == "menu:survey")
async def _menu_survey_fallback(callback: CallbackQuery) -> None:
    # The dedicated survey router owns this callback; this handler intentionally does nothing.
    await callback.answer()
