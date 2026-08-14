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
from categories import CATEGORIES

router = Router()


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


location_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="📍 ارسال موقعیت مکانی", request_location=True)]],
    resize_keyboard=True,
    one_time_keyboard=True,
)


WELCOME_TEXT = (
    "سلام 👋\n"
    "به ربات گزارش‌دهی شهروندی خدمات شهری ملایر خوش آمدید.\n\n"
    "با این ربات می‌توانید نقاط کثیف، زباله رهاشده یا آسیب‌دیدگی فضای سبز را "
    "به‌سرعت به شهرداری گزارش دهید.\n\n"
    "برای شروع، یک عکس از محل مورد نظر ارسال کنید.\n"
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
    await message.answer(
        "موقعیت مکانی دریافت شد ✅",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer("دسته‌بندی گزارش را انتخاب کنید:", reply_markup=categories_keyboard())
    await state.set_state(ReportForm.waiting_category)


@router.message(ReportForm.waiting_location)
async def location_missing(message: Message) -> None:
    await message.answer("لطفاً از دکمه «ارسال موقعیت مکانی» استفاده کنید.")


@router.callback_query(ReportForm.waiting_category, F.data.startswith("cat:"))
async def process_category(callback: CallbackQuery, state: FSMContext) -> None:
    key = callback.data.split(":", 1)[1]
    label = CATEGORIES.get(key, "سایر")
    await state.update_data(category=label)
    if callback.message is not None:
        await callback.message.answer(
            "در صورت تمایل توضیح کوتاهی درباره محل بنویسید، یا بنویسید «ندارد»."
        )
    await state.set_state(ReportForm.waiting_description)
    await callback.answer()


@router.message(ReportForm.waiting_description)
async def process_description(message: Message, state: FSMContext) -> None:
    await state.update_data(description=message.text or "ندارد")
    data = await state.get_data()
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

    caption = (
        "🆕 گزارش جدید شهروندی\n\n"
        f"دسته‌بندی: {data.get('category', 'نامشخص')}\n"
        f"توضیحات: {data.get('description', 'ندارد')}\n"
        f"از طرف: {user.full_name} (@{user.username or '-'})\n"
        f"شناسه کاربر: {user.id}"
    )

    await bot.send_photo(
        chat_id=config.ADMIN_GROUP_ID,
        photo=data["photo_file_id"],
        caption=caption,
    )
    await bot.send_location(
        chat_id=config.ADMIN_GROUP_ID,
        latitude=data["latitude"],
        longitude=data["longitude"],
    )

    if callback.message is not None:
        await callback.message.edit_text(
            "گزارش شما با موفقیت ثبت و برای شهرداری ارسال شد. ✅\n"
            "از مشارکت شما در پاکیزگی شهر سپاسگزاریم 🙏\n\n"
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


@router.message()
async def fallback(message: Message) -> None:
    await message.answer(
        "برای شروع ثبت گزارش جدید، دستور /start را بزنید."
    )
