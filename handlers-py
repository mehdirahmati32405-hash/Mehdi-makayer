from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

import config
import db
from categories import CATEGORIES, SOCIAL_HELP_HOTLINE, SOCIAL_REFERRAL_CATEGORY_KEYS
from services_content import SCHEDULE_TEXT, ACTIVITIES_TEXT

router = Router()

# نگاشت شماره روز هفته پایتون (دوشنبه=0) به نام روز هفته فارسی
PERSIAN_WEEKDAYS = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]


class ReportForm(StatesGroup):
    waiting_photo = State()
    waiting_location = State()
    waiting_category = State()
    waiting_description = State()
    confirm = State()


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
            [InlineKeyboardButton(text="❌ انصراف", callback_data="confirm:no")],
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


def services_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 برنامه و زمان‌بندی خدمات", callback_data="info:schedule")],
            [InlineKeyboardButton(text="📰 فعالیت‌ها و پروژه‌های اخیر", callback_data="info:activities")],
        ]
    )


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
    "سلام 👋\n"
    "به ربات گزارش‌دهی شهروندی خدمات شهری ملایر خوش آمدید.\n\n"
    "با این ربات می‌توانید نقاط کثیف، زباله رهاشده یا آسیب‌دیدگی فضای سبز را "
    "به‌سرعت به شهرداری گزارش دهید.\n\n"
    "برای شروع، یک عکس از محل مورد نظر ارسال کنید.\n"
    "برای دیدن وضعیت گزارش‌های قبلی، دستور /myreports را بفرستید.\n"
    "برای اطلاع از خدمات و فعالیت‌های شهرداری، دستور /khadamat را بفرستید.\n"
    "برای لغو در هر مرحله، دستور /cancel را بفرستید."
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(WELCOME_TEXT)
    await state.set_state(ReportForm.waiting_photo)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "عملیات لغو شد. برای شروع دوباره /start را بزنید.",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(Command("myreports"))
async def cmd_myreports(message: Message) -> None:
    reports = db.get_reports_by_user(message.from_user.id, limit=5)
    if not reports:
        await message.answer("شما هنوز هیچ گزارشی ثبت نکرده‌اید. برای شروع /start را بزنید.")
        return

    lines = ["📋 آخرین گزارش‌های شما:\n"]
    for r in reports:
        entry = (
            f"کد {db.report_code(r['id'])} — {r['category']}\n"
            f"وضعیت: {r['status']}"
        )
        if r["feedback"]:
            entry += f"\nبازخورد شما: {r['feedback']}"
        lines.append(entry + "\n")
    await message.answer("\n".join(lines))


@router.message(Command("khadamat"))
async def cmd_khadamat(message: Message) -> None:
    await message.answer(
        "اطلاعات خدمات شهری را انتخاب کنید:",
        reply_markup=services_menu_keyboard(),
    )


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


@router.message(ReportForm.waiting_photo, F.photo)
async def process_photo(message: Message, state: FSMContext) -> None:
    photo_file_id = message.photo[-1].file_id
    await state.update_data(photo_file_id=photo_file_id)
    await message.answer(
        "عکس دریافت شد ✅\nحالا لطفاً موقعیت مکانی محل را با دکمه زیر ارسال کنید.",
        reply_markup=location_keyboard,
    )
    await state.set_state(ReportForm.waiting_location)


@router.message(ReportForm.waiting_photo)
async def photo_missing(message: Message) -> None:
    await message.answer("لطفاً یک عکس از محل ارسال کنید (فقط عکس پذیرفته می‌شود).")


@router.message(ReportForm.waiting_location, F.location)
async def process_location(message: Message, state: FSMContext) -> None:
    await state.update_data(
        latitude=message.location.latitude,
        longitude=message.location.longitude,
    )
    await message.answer("موقعیت مکانی دریافت شد ✅", reply_markup=ReplyKeyboardRemove())
    await message.answer("دسته‌بندی گزارش را انتخاب کنید:", reply_markup=categories_keyboard())
    await state.set_state(ReportForm.waiting_category)


@router.message(ReportForm.waiting_location)
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


@router.message(ReportForm.waiting_description)
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


@router.callback_query(ReportForm.confirm, F.data == "confirm:yes")
async def confirm_yes(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    user = callback.from_user
    is_social = data.get("is_social", False)

    report_id = db.create_report(
        user_id=user.id,
        user_name=user.full_name,
        category=data.get("category", "نامشخص"),
        description=data.get("description", "ندارد"),
        latitude=data["latitude"],
        longitude=data["longitude"],
        photo_file_id=data["photo_file_id"],
    )
    code = db.report_code(report_id)

    if is_social:
        caption = (
            f"🆘 مورد نیازمند ارجاع به کمک اجتماعی — {code}\n\n"
            f"توضیحات: {data.get('description', 'ندارد')}\n"
            f"از طرف: {user.full_name} (@{user.username or '-'})\n"
            f"وضعیت: {db.STATUS_RECEIVED}\n\n"
            "لطفاً برای پیگیری با نهاد حمایتی/بهزیستی هماهنگ شود."
        )
    else:
        caption = (
            f"🆕 گزارش جدید شهروندی — {code}\n\n"
            f"دسته‌بندی: {data.get('category', 'نامشخص')}\n"
            f"توضیحات: {data.get('description', 'ندارد')}\n"
            f"از طرف: {user.full_name} (@{user.username or '-'})\n"
            f"وضعیت: {db.STATUS_RECEIVED}"
        )

    sent_photo = await bot.send_photo(
        chat_id=config.ADMIN_GROUP_ID,
        photo=data["photo_file_id"],
        caption=caption,
        reply_markup=admin_status_keyboard(report_id),
    )
    await bot.send_location(
        chat_id=config.ADMIN_GROUP_ID,
        latitude=data["latitude"],
        longitude=data["longitude"],
    )
    db.set_admin_message(report_id, sent_photo.chat.id, sent_photo.message_id)

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
            await callback.message.edit_text(
                "گزارش شما با موفقیت ثبت و برای شهرداری ارسال شد. ✅\n"
                f"کد پیگیری گزارش شما: {code}\n"
                "می‌توانید وضعیت آن را بعداً با دستور /myreports ببینید.\n\n"
                "از مشارکت شما در پاکیزگی شهر سپاسگزاریم 🙏\n"
                "برای ثبت گزارش جدید، دستور /start را بزنید."
            )
    await state.clear()
    await callback.answer()


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
        new_caption = (
            f"🆕 گزارش جدید شهروندی — {code}\n\n"
            f"دسته‌بندی: {report['category']}\n"
            f"توضیحات: {report['description']}\n"
            f"از طرف: {report['user_name']}\n"
            f"وضعیت: {new_status}"
        )
        await callback.message.edit_caption(
            caption=new_caption,
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


@router.message()
async def fallback(message: Message) -> None:
    await message.answer(
        "برای شروع ثبت گزارش جدید، دستور /start را بزنید.\n"
        "برای دیدن وضعیت گزارش‌های قبلی، دستور /myreports را بزنید."
    )
