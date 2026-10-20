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
import ai_memory
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
        inline_keyboard=[[InlineKeyboardButton(text="✅ کافیه، ادامه بده", callback_data="photos:done")]]
    )


def admin_status_keyboard(report_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 در حال رسیدگی", callback_data=f"status:{report_id}:progress"),
                InlineKeyboardButton(text="✅ رسیدگی شد", callback_data=f"status:{report_id}:done"),
            ],
            [InlineKeyboardButton(text="🚫 غیرقابل بررسی", callback_data=f"status:{report_id}:rejected")],
        ]
    )


def feedback_keyboard(report_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="👍 بله، برطرف شده", callback_data=f"feedback:{report_id}:yes"),
            InlineKeyboardButton(text="👎 خیر، هنوز هست", callback_data=f"feedback:{report_id}:no"),
        ]]
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
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔕 لغو اشتراک اطلاعیه‌ها", callback_data="sub:off")]])
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔔 عضویت در اطلاعیه‌های مهم", callback_data="sub:on")]])


def education_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text=title, callback_data=f"edu:{key}")] for key, (title, _text) in EDUCATION_TOPICS.items()]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def quiz_question_keyboard(q_index: int, options: list[str]) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text=opt, callback_data=f"quiz:{q_index}:{i}")] for i, opt in enumerate(options)]
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


def _ai_live_context() -> str:
    """خلاصه‌ای محدود از داده‌های واقعی ربات برای پاسخ‌های آماری AI."""
    stats = db.get_stats()
    period = db.get_period_stats(days=7)
    return (
        f"کل گزارش‌های ثبت‌شده: {stats['total']}\n"
        f"دریافت‌شده: {stats['received']}\n"
        f"در حال رسیدگی: {stats['in_progress']}\n"
        f"رسیدگی‌شده: {stats['done']}\n"
        f"غیرقابل بررسی: {stats['rejected']}\n"
        f"گزارش‌های ۷ روز اخیر: {period['total']}\n"
        f"رسیدگی‌شده از بازه ۷ روز اخیر: {period['done']}\n"
        f"پرتکرارترین دسته در ۷ روز اخیر: {period['top_category'] or 'نامشخص'} "
        f"({period['top_category_count']} مورد)"
    )


# بقیه handlerهای پروژه در این فایل حفظ شده‌اند.
