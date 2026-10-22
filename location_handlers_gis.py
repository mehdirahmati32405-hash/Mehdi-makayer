"""نسخه GIS محور ثبت گزارش مکانی، مستقل از هندلر قدیمی برای استقرار کم‌ریسک."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, KeyboardButton, Message, ReplyKeyboardMarkup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import location_db_upgrade as location_db
import location_intelligence as intelligence
import zone_resolver

router = Router()

class GISReportForm(StatesGroup):
    waiting_issue = State()
    waiting_location = State()
    waiting_description = State()
    waiting_point_decision = State()

ISSUE_BUTTONS = {"🐀 گزارش موش": "RAT", "🐕 گزارش سگ بلاصاحب": "DOG"}

def issue_keyboard():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🐀 گزارش موش")], [KeyboardButton(text="🐕 گزارش سگ بلاصاحب")]], resize_keyboard=True, one_time_keyboard=True)

def location_keyboard():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📍 ارسال موقعیت فعلی", request_location=True)], [KeyboardButton(text="❌ انصراف")]], resize_keyboard=True, one_time_keyboard=True)

def point_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ بله، همان نقطه است", callback_data="gispoint:yes")],
        [InlineKeyboardButton(text="➕ نقطه جدید ایجاد شود", callback_data="gispoint:no")],
        [InlineKeyboardButton(text="❌ لغو", callback_data="gispoint:cancel")],
    ])

# تست GIS با فرمان جداگانه فعال است تا روند فعلی /location_report بدون ریسک باقی بماند.
@router.message(Command("location_report_gis"), F.chat.type == "private")
async def start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(GISReportForm.waiting_issue)
    await message.answer("📍 <b>ثبت گزارش مکانی GIS</b>\n\nابتدا نوع مشکل را انتخاب کنید:", reply_markup=issue_keyboard())

@router.message(GISReportForm.waiting_issue, F.chat.type == "private")
async def issue(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if text == "❌ انصراف":
        await state.clear(); await message.answer("گزارش لغو شد."); return
    kind = ISSUE_BUTTONS.get(text)
    if not kind:
        await message.answer("لطفاً یکی از گزینه‌های موجود را انتخاب کنید.", reply_markup=issue_keyboard()); return
    await state.update_data(issue_type=kind)
    await state.set_state(GISReportForm.waiting_location)
    await message.answer("عالی است. حالا لطفاً <b>موقعیت دقیق محل مشاهده مشکل</b> را ارسال کنید.", reply_markup=location_keyboard())

@router.message(GISReportForm.waiting_location, F.chat.type == "private", F.location)
async def gps(message: Message, state: FSMContext):
    loc = message.location
    data = await state.get_data()
    kind = data.get("issue_type")
    if loc is None or kind not in location_db.ISSUE_TYPES:
        await state.clear(); await message.answer("اطلاعات موقعیت ناقص است. لطفاً دوباره شروع کنید."); return
    lat, lon = float(loc.latitude), float(loc.longitude)
    zone = zone_resolver.zone_from_coordinates(lat, lon)
    if not zone:
        await state.clear()
        await message.answer("📍 موقعیت دریافت شد، اما هنوز محدوده واقعی GIS این نقطه در ربات تعریف نشده است.\n\nبرای جلوگیری از ثبت اشتباه، ربات آن را به M1 نسبت نمی‌دهد.")
        return
    await state.update_data(latitude=lat, longitude=lon, zone_code=zone["code"], zone_name=zone["name"])
    candidates = intelligence.find_duplicate_candidates(latitude=lat, longitude=lon, issue_type=kind, radius_m=150.0, limit=5)
    if candidates:
        p = candidates[0]
        await state.update_data(nearby_point_id=p["id"])
        await state.set_state(GISReportForm.waiting_point_decision)
        distance = p.get("distance_m", 0)
        confidence = intelligence.classify_duplicate_distance(distance)
        confidence_text = {"high":"🟢 اطمینان بالا", "medium":"🟡 اطمینان متوسط", "low":"🟠 نیازمند بررسی"}[confidence]
        await message.answer(f"🔎 <b>احتمال گزارش تکراری</b>\n\n📍 محدوده: <b>{zone['code']}</b>، {zone['name']}\nکد پرونده: <code>{p['code']}</code>\nفاصله: {distance} متر\nتشخیص: <b>{confidence_text}</b>\nگزارش‌های قبلی: <b>{int(p.get('report_count', 0))}</b>\n\nآیا همان نقطه است؟", reply_markup=point_keyboard())
        return
    await state.set_state(GISReportForm.waiting_description)
    await message.answer(f"📍 موقعیت دریافت شد.\n\n<b>محدوده: {zone['code']}، {zone['name']}</b>\n\nلطفاً آدرس یا نشانی و شرح مشکل را بنویسید.")

@router.callback_query(GISReportForm.waiting_point_decision, F.data == "gispoint:yes")
async def existing(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data(); pid = data.get("nearby_point_id")
    if not pid:
        await callback.answer("نقطه پیدا نشد.", show_alert=True); await state.clear(); return
    await state.update_data(point_id=pid); await state.set_state(GISReportForm.waiting_description)
    if callback.message: await callback.message.answer("✅ به همان نقطه متصل می‌شود.\n\nشرح کوتاه مشکل را بنویسید.")
    await callback.answer()

@router.callback_query(GISReportForm.waiting_point_decision, F.data == "gispoint:no")
async def new_point(callback: CallbackQuery, state: FSMContext):
    await state.update_data(create_new_point=True); await state.set_state(GISReportForm.waiting_description)
    if callback.message: await callback.message.answer("➕ نقطه جدید ایجاد می‌شود.\n\nآدرس یا نشانی و شرح مشکل را بنویسید.")
    await callback.answer()

@router.callback_query(GISReportForm.waiting_point_decision, F.data == "gispoint:cancel")
async def cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if callback.message: await callback.message.answer("❌ ثبت گزارش لغو شد.")
    await callback.answer()

@router.message(GISReportForm.waiting_description, F.chat.type == "private", F.text)
async def save(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text or text == "❌ انصراف":
        await state.clear(); await message.answer("ثبت گزارش لغو شد."); return
    data = await state.get_data()
    kind, lat, lon = data.get("issue_type"), data.get("latitude"), data.get("longitude")
    zone_code, zone_name = data.get("zone_code"), data.get("zone_name")
    pid = data.get("point_id")
    if kind not in location_db.ISSUE_TYPES or not zone_code:
        await state.clear(); await message.answer("اطلاعات مکانی ناقص است. لطفاً دوباره شروع کنید."); return
    try:
        if pid is None and data.get("create_new_point"):
            pid = location_db.create_location_point(zone_code=zone_code, issue_type=kind, latitude=float(lat), longitude=float(lon), address=text, severity=1)
        rid = location_db.create_location_report(point_id=pid, user_id=message.from_user.id if message.from_user else None, issue_type=kind, description=text, latitude=float(lat), longitude=float(lon), address=text if pid is None else None, photos=[], source_type="BOT", severity=1)
        code = None
        if pid:
            for row in location_db.get_point_reports(pid):
                if row["id"] == rid: code = row["report_code"]; break
        point = location_db.get_point(pid) if pid else None
        await state.clear()
        await message.answer("✅ <b>گزارش مکانی با موفقیت ثبت شد.</b>\n\n" + f"📍 محدوده: <b>{zone_code}</b>، {zone_name}\n" + f"📌 کد نقطه: <code>{point['code'] if point else 'بدون نقطه'}</code>\n" + f"🧾 کد گزارش: <code>{code or rid}</code>\n" + f"📌 نوع مشکل: {location_db.ISSUE_TYPES.get(kind, kind)}\n" + f"🌐 مختصات: {lat:.6f}, {lon:.6f}\n\nگزارش برای بررسی و اقدام اجرایی ثبت شد.")
    except Exception as exc:
        print(f"[location_handlers_gis] save error: {exc}")
        await state.clear(); await message.answer("متأسفانه هنگام ثبت گزارش مشکلی پیش آمد. لطفاً چند دقیقه بعد دوباره تلاش کنید.")
