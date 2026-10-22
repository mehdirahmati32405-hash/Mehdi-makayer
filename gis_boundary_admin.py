"""مدیریت مرزهای GIS واقعی M1 تا M4 از طریق فایل GeoJSON در گروه مدیران.

فایل ورودی باید FeatureCollection در WGS84 (EPSG:4326) باشد.
هر Feature باید properties.code یکی از M1/M2/M3/M4 و geometry از نوع
Polygon یا MultiPolygon داشته باشد. تمام چهار مرز پیش از هر تغییری اعتبارسنجی می‌شوند.
"""
import json
from io import BytesIO

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

import config
import location_db_upgrade as location_db
import zone_resolver

gis_admin_router = Router()
ZONE_NAMES = {
    "M1": "محدوده منطقه ۱ شهری ملایر",
    "M2": "محدوده منطقه ۲ شهری ملایر",
    "M3": "محدوده منطقه ۳ شهری ملایر",
    "M4": "محدوده منطقه ۴ شهری ملایر",
}
REQUIRED_CODES = set(ZONE_NAMES)
MAX_GEOJSON_BYTES = 5 * 1024 * 1024


def _is_admin(message: Message) -> bool:
    return message.chat.id == config.ADMIN_GROUP_ID


def _valid_ring(ring) -> bool:
    if not isinstance(ring, list) or len(ring) < 4:
        return False
    for point in ring:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            return False
        try:
            lon, lat = float(point[0]), float(point[1])
        except (TypeError, ValueError):
            return False
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            return False
    return ring[0][0] == ring[-1][0] and ring[0][1] == ring[-1][1]


def _valid_geometry(geometry) -> bool:
    if not isinstance(geometry, dict):
        return False
    kind = geometry.get("type")
    coords = geometry.get("coordinates")
    if kind == "Polygon":
        return (
            isinstance(coords, list) and len(coords) > 0
            and all(_valid_ring(ring) for ring in coords)
        )
    if kind == "MultiPolygon":
        return (
            isinstance(coords, list) and len(coords) > 0
            and all(
                isinstance(poly, list) and len(poly) > 0
                and all(_valid_ring(ring) for ring in poly)
                for poly in coords
            )
        )
    return False


@gis_admin_router.message(Command("gis_status"))
async def gis_status(message: Message) -> None:
    if not _is_admin(message):
        return
    with location_db._conn() as conn:
        rows = conn.execute(
            "SELECT code, name, polygon_geojson FROM zones WHERE code IN ('M1','M2','M3','M4') ORDER BY code"
        ).fetchall()
    by_code = {row["code"]: row for row in rows}
    lines = ["🗺 <b>وضعیت مرزهای GIS ربات</b>", ""]
    for code in ("M1", "M2", "M3", "M4"):
        row = by_code.get(code)
        if row and row["polygon_geojson"]:
            lines.append(f"✅ <b>{code}</b> — هندسه ثبت شده")
        else:
            lines.append(f"⚠️ <b>{code}</b> — مرز واقعی هنوز وارد نشده")
    if zone_resolver.all_zones_have_boundaries():
        lines += ["", "✅ هر چهار مرز در دیتابیس وجود دارد. اکنون باید با نقاط آزمایشی صحت‌سنجی شوند."]
    else:
        lines += [
            "",
            "برای واردکردن مرزها، فایل GeoJSON واقعی را در همین گروه با کپشن /gis_import ارسال کنید.",
            "فایل باید شامل چهار Feature با properties.code برابر M1، M2، M3 و M4 و مختصات WGS84 (طول، عرض) باشد.",
            "فایل DXF یا تصویر نقشه مستقیماً قابل واردکردن نیست؛ ابتدا باید از GIS به GeoJSON با CRS برابر EPSG:4326 صادر شود.",
        ]
    await message.answer("\n".join(lines))


@gis_admin_router.message(Command("gis_import"), F.text)
async def gis_import_help(message: Message) -> None:
    if not _is_admin(message):
        return
    await message.answer(
        "📥 <b>واردکردن مرزهای واقعی GIS</b>\n\n"
        "فایل GeoJSON را به‌صورت Document در همین گروه ارسال کن و در قسمت کپشن دقیقاً بنویس:\n"
        "<code>/gis_import</code>\n\n"
        "الزامات: FeatureCollection، چهار Feature با properties.code برابر M1 تا M4، "
        "هندسه Polygon/MultiPolygon و مختصات WGS84 (EPSG:4326).\n"
        "هر چهار محدوده قبل از ذخیره بررسی می‌شوند؛ اگر حتی یکی ناقص باشد، هیچ تغییری انجام نمی‌شود."
    )


@gis_admin_router.message(F.document, F.caption)
async def receive_geojson(message: Message) -> None:
    if not _is_admin(message) or not message.caption:
        return
    if not message.caption.strip().split()[0].split("@")[0] == "/gis_import":
        return
    doc = message.document
    if not doc:
        return
    filename = (doc.file_name or "").lower()
    if not filename.endswith((".geojson", ".json")):
        await message.answer("❌ فایل باید پسوند .geojson یا .json داشته باشد.")
        return
    if doc.file_size and doc.file_size > MAX_GEOJSON_BYTES:
        await message.answer("❌ حجم فایل بیشتر از ۵ مگابایت است.")
        return
    try:
        file_info = await message.bot.get_file(doc.file_id)
        stream = BytesIO()
        await message.bot.download_file(file_info.file_path, destination=stream)
        raw = stream.getvalue()
        if len(raw) > MAX_GEOJSON_BYTES:
            raise ValueError("حجم فایل بیشتر از ۵ مگابایت است.")
        payload = json.loads(raw.decode("utf-8-sig"))
    except Exception as exc:
        await message.answer(f"❌ خواندن فایل ناموفق بود: {str(exc)[:250]}")
        return

    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        await message.answer("❌ فایل باید GeoJSON از نوع FeatureCollection باشد.")
        return
    features = payload.get("features")
    if not isinstance(features, list):
        await message.answer("❌ فهرست features در فایل پیدا نشد.")
        return

    selected = {}
    for feature in features:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            continue
        props = feature.get("properties") or {}
        code = str(props.get("code") or props.get("zone_code") or "").strip().upper()
        if code not in REQUIRED_CODES:
            continue
        if code in selected:
            await message.answer(f"❌ کد محدوده {code} بیش از یک بار در فایل آمده است.")
            return
        if not _valid_geometry(feature.get("geometry")):
            await message.answer(f"❌ هندسه محدوده {code} معتبر نیست یا مختصات آن خارج از قالب WGS84 است.")
            return
        selected[code] = feature

    missing = sorted(REQUIRED_CODES - set(selected))
    if missing:
        await message.answer("❌ این محدوده‌ها در فایل پیدا نشدند: " + "، ".join(missing) + "\nهیچ تغییری ذخیره نشد.")
        return

    try:
        with location_db._conn() as conn:
            for code in ("M1", "M2", "M3", "M4"):
                feature = selected[code]
                geometry_json = json.dumps(feature, ensure_ascii=False, separators=(",", ":"))
                conn.execute(
                    "UPDATE zones SET name=?, polygon_geojson=? WHERE code=?",
                    (ZONE_NAMES[code], geometry_json, code),
                )
                if conn.execute("SELECT changes()").fetchone()[0] != 1:
                    raise ValueError(f"رکورد {code} در جدول zones پیدا نشد.")
    except Exception as exc:
        await message.answer(f"❌ ذخیره مرزها کامل نشد: {str(exc)[:250]}")
        return

    await message.answer(
        "✅ <b>مرزهای GIS وارد شدند.</b>\n\n"
        + "\n".join(f"• {code}: {ZONE_NAMES[code]}" for code in ("M1", "M2", "M3", "M4"))
        + "\n\nاکنون /gis_status را اجرا کن. سپس باید چهار نقطه آزمایشیِ تأییدشده را بررسی کنیم؛ "
        "تا قبل از تست میدانی، دقت طبقه‌بندی را قطعی فرض نمی‌کنیم."
    )
