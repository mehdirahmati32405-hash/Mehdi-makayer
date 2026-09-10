"""
پنل مدیریت گزارش‌های مکانی برای ربات گزارش شهروندی ملایر

فرمان‌ها:
/location_admin
/lpoint ML-M1-RAT-001
/lzone M1
/lhotspots
/lstats
/lstatus ML-M1-RAT-001 in_progress
/loperation ML-M1-RAT-001|طعمه‌گذاری|تیم اجرایی|انجام شد|بازدید مجدد
"""

from datetime import datetime, timezone
from typing import Optional

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

import config
import location_db_upgrade as location_db

location_admin_router = Router()

STATUS_NAMES = {
    "open": "باز",
    "in_progress": "در حال رسیدگی",
    "resolved": "رسیدگی‌شده",
    "rejected": "ردشده",
}


def _is_admin(message: Message) -> bool:
    return message.chat.id == config.ADMIN_GROUP_ID


def _arg(command: Optional[CommandObject]) -> str:
    return (command.args or "").strip() if command else ""


def _stats() -> dict:
    with location_db._conn() as conn:
        result = {
            "points": conn.execute("SELECT COUNT(*) c FROM location_points").fetchone()["c"],
            "reports": conn.execute("SELECT COUNT(*) c FROM location_reports").fetchone()["c"],
            "open": conn.execute("SELECT COUNT(*) c FROM location_reports WHERE status='open'").fetchone()["c"],
            "operations": conn.execute("SELECT COUNT(*) c FROM field_operations").fetchone()["c"],
            "rats": conn.execute("SELECT COUNT(*) c FROM location_points WHERE issue_type='RAT'").fetchone()["c"],
            "dogs": conn.execute("SELECT COUNT(*) c FROM location_points WHERE issue_type='DOG'").fetchone()["c"],
            "zones": {},
        }
        for row in conn.execute("SELECT zone_code, COUNT(*) c FROM location_points GROUP BY zone_code ORDER BY zone_code"):
            result["zones"][row["zone_code"]] = row["c"]
    return result


@location_admin_router.message(Command("location_admin"))
async def location_admin_menu(message: Message) -> None:
    if not _is_admin(message):
        return
    await message.answer(
        "🗺 <b>پنل مدیریت گزارش‌های مکانی</b>\n\n"
        "📍 <code>/lpoint CODE</code> — پرونده کامل نقطه\n"
        "🗂 <code>/lzone M1</code> — نقاط یک بخش\n"
        "🔥 <code>/lhotspots</code> — نقاط داغ باز\n"
        "📊 <code>/lstats</code> — آمار مکانی\n"
        "🔄 <code>/lstatus CODE STATUS</code> — تغییر وضعیت نقطه\n"
        "🛠 <code>/loperation CODE|نوع|مجری|نتیجه|یادداشت</code> — ثبت عملیات میدانی\n\n"
        "وضعیت‌ها: <code>open</code> / <code>in_progress</code> / <code>resolved</code> / <code>rejected</code>"
    )


@location_admin_router.message(Command("lstats"))
async def location_stats(message: Message) -> None:
    if not _is_admin(message):
        return
    s = _stats()
    zones = "\n".join(
        f"• {code} ({name}): {s['zones'].get(code, 0)} نقطه"
        for code, name in location_db.ZONE_CODES.items()
    )
    await message.answer(
        "📊 <b>آمار سامانه گزارش‌های مکانی</b>\n\n"
        f"📍 نقاط: <b>{s['points']}</b>\n"
        f"🧾 گزارش‌ها: <b>{s['reports']}</b>\n"
        f"🔴 گزارش‌های باز: <b>{s['open']}</b>\n"
        f"🛠 عملیات میدانی: <b>{s['operations']}</b>\n"
        f"🐀 نقاط موش: <b>{s['rats']}</b>\n"
        f"🐕 نقاط سگ: <b>{s['dogs']}</b>\n\n"
        "<b>چهار بخش عملیاتی:</b>\n" + zones
    )


@location_admin_router.message(Command("lpoint"))
async def location_point(message: Message, command: CommandObject) -> None:
    if not _is_admin(message):
        return
    code = _arg(command).upper()
    if not code:
        await message.answer("فرمت صحیح: <code>/lpoint ML-M1-RAT-001</code>")
        return
    point = location_db.get_point_by_code(code)
    if not point:
        await message.answer(f"❌ نقطه <code>{code}</code> پیدا نشد.")
        return

    issue = location_db.ISSUE_TYPES.get(point["issue_type"], point["issue_type"])
    status = STATUS_NAMES.get(point["status"], point["status"])
    reports = location_db.get_point_reports(point["id"])
    operations = location_db.get_point_operations(point["id"])

    text = (
        "📍 <b>پرونده نقطه مکانی</b>\n\n"
        f"🔖 کد: <code>{point['code']}</code>\n"
        f"🗺 بخش: <b>{point['zone_code']}</b> — {location_db.ZONE_CODES.get(point['zone_code'], '-') }\n"
        f"⚠️ مشکل: <b>{issue}</b>\n"
        f"📌 وضعیت: <b>{status}</b>\n"
        f"📊 شدت: {point['severity']}/5\n"
        f"🔢 تعداد گزارش: <b>{point['report_count']}</b>\n"
        f"📅 اولین گزارش: {point['first_report_at'] or '-'}\n"
        f"📅 آخرین گزارش: {point['last_report_at'] or '-'}\n"
        f"🛠 آخرین بازدید: {point['last_visit_at'] or '-'}\n"
        f"👤 مسئول: {point['responsible_person'] or '-'}\n"
        f"📝 آخرین اقدام: {point['last_action'] or '-'}\n"
        f"🏠 نشانی: {point['address'] or '-'}\n"
        f"🌐 مختصات: <code>{float(point['latitude']):.6f}, {float(point['longitude']):.6f}</code>\n"
    )
    if point["expert_note"]:
        text += f"👨‍🔬 یادداشت کارشناس: {point['expert_note']}\n"

    text += f"\n🧾 <b>گزارش‌های متصل:</b> {len(reports)}"
    for r in reports[:10]:
        text += f"\n• <code>{r['report_code']}</code> — {STATUS_NAMES.get(r['status'], r['status'])}"

    text += f"\n\n🛠 <b>عملیات:</b> {len(operations)}"
    for op in operations[:10]:
        text += f"\n• <code>{op['operation_code']}</code> — {op['operation_type']} — {op['operation_date']}"

    await message.answer(text)
    try:
        await message.bot.send_location(
            chat_id=message.chat.id,
            latitude=float(point["latitude"]),
            longitude=float(point["longitude"]),
        )
    except Exception:
        pass


@location_admin_router.message(Command("lzone"))
async def location_zone(message: Message, command: CommandObject) -> None:
    if not _is_admin(message):
        return
    zone = _arg(command).upper()
    if zone not in location_db.ZONE_CODES:
        await message.answer("فرمت صحیح: <code>/lzone M1</code> — بخش‌ها: M1, M2, M3, M4")
        return
    points = location_db.get_zone_points(zone)
    if not points:
        await message.answer(f"📭 در بخش <b>{zone}</b> هنوز نقطه‌ای ثبت نشده است.")
        return
    lines = [f"🗂 <b>نقاط بخش {zone} — {location_db.ZONE_CODES[zone]}</b>\n"]
    for i, p in enumerate(points[:30], 1):
        issue = location_db.ISSUE_TYPES.get(p["issue_type"], p["issue_type"])
        status = STATUS_NAMES.get(p["status"], p["status"])
        lines.append(f"{i}. <code>{p['code']}</code> | {issue} | گزارش: {p['report_count']} | {status}\n   📍 {p['address'] or 'نشانی ثبت نشده'}")
    if len(points) > 30:
        lines.append(f"\n... و {len(points)-30} نقطه دیگر")
    await message.answer("\n".join(lines))


@location_admin_router.message(Command("lhotspots"))
async def location_hotspots(message: Message) -> None:
    if not _is_admin(message):
        return
    with location_db._conn() as conn:
        rows = conn.execute(
            """SELECT * FROM location_points
               WHERE status IN ('open','in_progress')
               ORDER BY report_count DESC, severity DESC, last_report_at DESC
               LIMIT 15"""
        ).fetchall()
    if not rows:
        await message.answer("✅ نقطه باز یا در حال رسیدگی وجود ندارد.")
        return
    lines = ["🔥 <b>۱۵ نقطه داغ / نیازمند پیگیری</b>\n"]
    for i, p in enumerate(rows, 1):
        issue = location_db.ISSUE_TYPES.get(p["issue_type"], p["issue_type"])
        status = STATUS_NAMES.get(p["status"], p["status"])
        lines.append(
            f"{i}. <code>{p['code']}</code>\n"
            f"   🗺 {p['zone_code']} | {issue} | گزارش: <b>{p['report_count']}</b> | {status}\n"
            f"   📍 {p['address'] or 'نشانی ثبت نشده'}"
        )
    await message.answer("\n".join(lines))


@location_admin_router.message(Command("lstatus"))
async def location_status(message: Message, command: CommandObject) -> None:
    if not _is_admin(message):
        return
    args = _arg(command).split()
    if len(args) != 2 or args[1].lower() not in STATUS_NAMES:
        await message.answer("فرمت صحیح: <code>/lstatus ML-M1-RAT-001 in_progress</code>")
        return
    code, status = args[0].upper(), args[1].lower()
    point = location_db.get_point_by_code(code)
    if not point:
        await message.answer(f"❌ نقطه <code>{code}</code> پیدا نشد.")
        return
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with location_db._conn() as conn:
        conn.execute("UPDATE location_points SET status=?, updated_at=? WHERE id=?", (status, now, point["id"]))
    await message.answer(f"✅ وضعیت <code>{code}</code> به <b>{STATUS_NAMES[status]}</b> تغییر کرد.")


@location_admin_router.message(Command("loperation"))
async def location_operation(message: Message, command: CommandObject) -> None:
    if not _is_admin(message):
        return
    parts = [p.strip() for p in _arg(command).split("|")]
    if len(parts) < 2:
        await message.answer(
            "فرمت صحیح:\n<code>/loperation CODE|نوع عملیات|مجری|نتیجه|یادداشت</code>\n\n"
            "مثال:\n<code>/loperation ML-M1-RAT-001|طعمه‌گذاری|تیم اجرایی|انجام شد|بازدید مجدد</code>"
        )
        return
    code, op_type = parts[0].upper(), parts[1] or "سایر"
    operator = parts[2] if len(parts) > 2 and parts[2] else None
    result = parts[3] if len(parts) > 3 and parts[3] else None
    notes = parts[4] if len(parts) > 4 and parts[4] else None
    point = location_db.get_point_by_code(code)
    if not point:
        await message.answer(f"❌ نقطه <code>{code}</code> پیدا نشد.")
        return
    op_id = location_db.create_field_operation(
        point_id=point["id"], operation_type=op_type,
        operator=operator, result=result, notes=notes,
    )
    await message.answer(
        "✅ <b>عملیات میدانی ثبت شد.</b>\n\n"
        f"📍 نقطه: <code>{code}</code>\n"
        f"🛠 نوع: {op_type}\n"
        f"👤 مجری: {operator or '-'}\n"
        f"📋 نتیجه: {result or '-'}\n"
        f"🔢 شناسه داخلی: <code>{op_id}</code>"
    )
