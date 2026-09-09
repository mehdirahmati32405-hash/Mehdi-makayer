"""
location_handlers.py
مرحله دوم اتصال GPS به ربات گزارش شهروندی ملایر

این ماژول عمداً مستقل از handlers.py فعلی نوشته شده تا در مرحله تست،
کمترین ریسک را برای روند فعلی گزارش‌دهی داشته باشد.

فعال‌سازی در main.py:
    from location_handlers import location_router
    dispatcher.include_router(location_router)

فرمان تست:
    /location_report

روند:
    /location_report
        ↓
    انتخاب نوع مشکل
        ↓
    ارسال موقعیت GPS
        ↓
    انتخاب/ایجاد نقطه نزدیک
        ↓
    ثبت شرح گزارش
        ↓
    ثبت در location_reports
"""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, KeyboardButton, Message, ReplyKeyboardMarkup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import location_db_upgrade as location_db


location_router = Router()


class LocationReportForm(StatesGroup):
    waiting_issue = State()
    waiting_location = State()
    waiting_description = State()
    waiting_point_decision = State()


ISSUE_BUTTONS = {
    "🐀 گزارش موش": "RAT",
    "🐕 گزارش سگ بلاصاحب": "DOG",
}


def issue_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🐀 گزارش موش")],
            [KeyboardButton(text="🐕 گزارش سگ بلاصاحب")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def location_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 ارسال موقعیت فعلی", request_location=True)],
            [KeyboardButton(text="❌ انصراف")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def point_decision_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ بله، همان نقطه است",
                    callback_data="locpoint:yes",
                )
            ],
            [
                InlineKeyboardButton(
                    text="➕ نقطه جدید ایجاد شود",
                    callback_data="locpoint:no",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ لغو",
                    callback_data="locpoint:cancel",
                )
            ],
        ]
    )


@location_router.message(Command("location_report"), F.chat.type == "private")
async def start_location_report(
    message: Message, state: FSMContext
) -> None:
    await state.clear()
    await state.set_state(LocationReportForm.waiting_issue)
    await message.answer(
        "📍 <b>ثبت گزارش مکانی</b>\n\n"
        "ابتدا نوع مشکل را انتخاب کنید:",
        reply_markup=issue_keyboard(),
    )


@location_router.message(LocationReportForm.waiting_issue, F.chat.type == "private")
async def receive_issue(
    message: Message, state: FSMContext
) -> None:
    text = (message.text or "").strip()

    if text == "❌ انصراف":
        await state.clear()
        await message.answer("گزارش لغو شد.")
        return

    issue_type = ISSUE_BUTTONS.get(text)
    if not issue_type:
        await message.answer(
            "لطفاً یکی از گزینه‌های موجود را انتخاب کنید.",
            reply_markup=issue_keyboard(),
        )
        return

    await state.update_data(issue_type=issue_type)
    await state.set_state(LocationReportForm.waiting_location)

    await message.answer(
        "عالی است. حالا لطفاً <b>موقعیت دقیق محل مشاهده مشکل</b> را ارسال کنید.\n\n"
        "ترجیحاً در همان محل حضور داشته باشید و روی «ارسال موقعیت فعلی» بزنید.",
        reply_markup=location_keyboard(),
    )


@location_router.message(
    LocationReportForm.waiting_location,
    F.chat.type == "private",
    F.location,
)
async def receive_location(
    message: Message, state: FSMContext
) -> None:
    location = message.location
    if location is None:
        return

    data = await state.get_data()
    issue_type = data.get("issue_type")

    if issue_type not in location_db.ISSUE_TYPES:
        await state.clear()
        await message.answer("نوع گزارش نامعتبر است. لطفاً دوباره شروع کنید.")
        return

    latitude = float(location.latitude)
    longitude = float(location.longitude)

    # فعلاً تشخیص M1-M4 به‌صورت دستی/اداری باقی می‌ماند.
    # بعد از ورود مرزهای GIS، این قسمت با zone_from_coordinates جایگزین می‌شود.
    await state.update_data(latitude=latitude, longitude=longitude)

    nearby = location_db.find_nearby_point(
        latitude=latitude,
        longitude=longitude,
        issue_type=issue_type,
        radius_m=100.0,
    )

    if nearby:
        await state.update_data(nearby_point_id=nearby["id"])
        await state.set_state(LocationReportForm.waiting_point_decision)

        distance = nearby.get("distance_m", 0)
        issue_name = location_db.ISSUE_TYPES.get(issue_type, issue_type)

        await message.answer(
            f"🔎 <b>نقطه مشابه پیدا شد</b>\n\n"
            f"کد نقطه: <code>{nearby['code']}</code>\n"
            f"نوع مشکل: {issue_name}\n"
            f"فاصله تقریبی: {distance} متر\n"
            f"آدرس ثبت‌شده: {nearby.get('address') or 'ثبت نشده'}\n\n"
            "آیا گزارش شما مربوط به همین نقطه است؟",
            reply_markup=point_decision_keyboard(),
            reply_markup_remove=False,
        )
        return

    # هنوز نقطه‌ای در شعاع 100 متر پیدا نشده است.
    # چون مرز GIS چهار بخش هنوز وارد نشده، از کاربر آدرس/شرح می‌گیریم
    # و در مرحله اتصال کامل، zone_code از مختصات تعیین خواهد شد.
    await state.set_state(LocationReportForm.waiting_description)
    await message.answer(
        "📍 موقعیت دریافت شد.\n\n"
        "برای ثبت نقطه جدید، لطفاً <b>آدرس یا نشانی محل</b> را بنویسید "
        "و اگر توضیح بیشتری درباره مشکل دارید اضافه کنید."
    )


@location_router.callback_query(
    LocationReportForm.waiting_point_decision,
    F.data == "locpoint:yes",
)
async def use_existing_point(
    callback: CallbackQuery, state: FSMContext
) -> None:
    data = await state.get_data()
    point_id = data.get("nearby_point_id")

    if not point_id:
        await callback.answer("نقطه پیدا نشد.", show_alert=True)
        await state.clear()
        return

    await state.update_data(point_id=point_id)
    await state.set_state(LocationReportForm.waiting_description)

    if callback.message:
        await callback.message.answer(
            "✅ گزارش به همان نقطه متصل می‌شود.\n\n"
            "لطفاً شرح کوتاه مشکل را بنویسید؛ مثلاً:\n"
            "«مشاهده چند موش در اطراف دریچه فاضلاب و تکرار مشاهده در شب»"
        )

    await callback.answer()


@location_router.callback_query(
    LocationReportForm.waiting_point_decision,
    F.data == "locpoint:no",
)
async def create_new_point(
    callback: CallbackQuery, state: FSMContext
) -> None:
    data = await state.get_data()
    await state.update_data(create_new_point=True)
    await state.set_state(LocationReportForm.waiting_description)

    if callback.message:
        await callback.message.answer(
            "➕ نقطه جدید ایجاد خواهد شد.\n\n"
            "لطفاً <b>آدرس دقیق یا نشانی محل</b> و توضیح مشکل را بنویسید."
        )

    await callback.answer()


@location_router.callback_query(
    LocationReportForm.waiting_point_decision,
    F.data == "locpoint:cancel",
)
async def cancel_point_decision(
    callback: CallbackQuery, state: FSMContext
) -> None:
    await state.clear()
    if callback.message:
        await callback.message.answer("❌ ثبت گزارش لغو شد.")
    await callback.answer()


@location_router.message(
    LocationReportForm.waiting_description,
    F.chat.type == "private",
    F.text,
)
async def receive_description(
    message: Message, state: FSMContext
) -> None:
    description = message.text.strip()

    if not description or description == "❌ انصراف":
        await state.clear()
        await message.answer("ثبت گزارش لغو شد.")
        return

    data = await state.get_data()
    issue_type = data.get("issue_type")
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    point_id = data.get("point_id")
    create_new = data.get("create_new_point", False)

    if issue_type not in location_db.ISSUE_TYPES:
        await state.clear()
        await message.answer("اطلاعات گزارش ناقص است. لطفاً دوباره شروع کنید.")
        return

    try:
        # تا زمان ورود مرزهای واقعی GIS، نقطه جدید به‌صورت موقت
        # در M1 قرار می‌گیرد. این مقدار عمداً در یک جای مشخص نگه داشته شده
        # تا بعداً فقط یک تابع zone resolver جایگزین شود.
        if point_id is None and create_new:
            point_id = location_db.create_location_point(
                zone_code="M1",
                issue_type=issue_type,
                latitude=float(latitude),
                longitude=float(longitude),
                address=description,
                severity=1,
            )

        report_id = location_db.create_location_report(
            point_id=point_id,
            user_id=message.from_user.id if message.from_user else None,
            issue_type=issue_type,
            description=description,
            latitude=float(latitude),
            longitude=float(longitude),
            address=description if point_id is None else None,
            photos=[],
            source_type="BOT",
            severity=1,
        )

        report_code = None
        if point_id:
            reports = location_db.get_point_reports(point_id)
            for item in reports:
                if item["id"] == report_id:
                    report_code = item["report_code"]
                    break

        await state.clear()

        point = location_db.get_point(point_id) if point_id else None
        point_code = point["code"] if point else "بدون نقطه"

        await message.answer(
            "✅ <b>گزارش مکانی با موفقیت ثبت شد.</b>\n\n"
            f"📍 کد نقطه: <code>{point_code}</code>\n"
            f"🧾 کد گزارش: <code>{report_code or report_id}</code>\n"
            f"📌 نوع مشکل: {location_db.ISSUE_TYPES.get(issue_type, issue_type)}\n"
            f"🌐 مختصات: {latitude:.6f}, {longitude:.6f}\n\n"
            "گزارش برای بررسی و اقدام اجرایی در سامانه ثبت شد."
        )

    except Exception as exc:
        # خطای داخلی را به شهروند نمایش نمی‌دهیم.
        print(f"[location_handlers] save error: {exc}")
        await state.clear()
        await message.answer(
            "متأسفانه هنگام ثبت گزارش مشکلی پیش آمد. "
            "لطفاً چند دقیقه بعد دوباره تلاش کنید."
        )
