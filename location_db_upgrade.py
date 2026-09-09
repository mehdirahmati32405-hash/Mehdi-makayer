"""
location_db_upgrade.py
افزونه دیتابیس مکانی هوشمند برای ربات گزارش شهروندی ملایر

این فایل مستقل است و برای جلوگیری از دستکاری ناخواسته db.py طراحی شده.
بعد از کپی در ریپازیتوری، می‌توان آن را از db.py یا main.py فراخوانی کرد.

ساختار:
Zone -> Location Point -> Citizen Report -> Field Operation
"""

import json
import math
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional


DB_PATH = os.getenv("DB_PATH", "reports.db")

ZONE_CODES = {
    "M1": "شمال‌غرب",
    "M2": "شمال‌شرق",
    "M3": "جنوب‌شرق",
    "M4": "جنوب‌غرب",
}

ISSUE_TYPES = {
    "RAT": "موش",
    "DOG": "سگ بلاصاحب",
    "OTHER": "سایر",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_location_db() -> None:
    """ایجاد جداول مکانی بدون حذف یا تغییر جداول قبلی ربات."""
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS zones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                description TEXT,
                polygon_geojson TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS location_points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                zone_code TEXT NOT NULL,
                issue_type TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                address TEXT,
                first_report_at TEXT,
                last_report_at TEXT,
                report_count INTEGER NOT NULL DEFAULT 0,
                severity INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'open',
                last_visit_at TEXT,
                last_action TEXT,
                responsible_person TEXT,
                expert_note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(zone_code) REFERENCES zones(code)
            );

            CREATE INDEX IF NOT EXISTS idx_location_points_zone
            ON location_points(zone_code);

            CREATE INDEX IF NOT EXISTS idx_location_points_issue
            ON location_points(issue_type);

            CREATE INDEX IF NOT EXISTS idx_location_points_geo
            ON location_points(latitude, longitude);

            CREATE TABLE IF NOT EXISTS location_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_code TEXT NOT NULL UNIQUE,
                point_id INTEGER,
                user_id INTEGER,
                source_type TEXT NOT NULL DEFAULT 'BOT',
                source_tracking_code TEXT,
                issue_type TEXT NOT NULL,
                description TEXT,
                latitude REAL,
                longitude REAL,
                address TEXT,
                photos_json TEXT,
                status TEXT NOT NULL DEFAULT 'open',
                severity INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(point_id) REFERENCES location_points(id)
                    ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_location_reports_point
            ON location_reports(point_id);

            CREATE INDEX IF NOT EXISTS idx_location_reports_user
            ON location_reports(user_id);

            CREATE INDEX IF NOT EXISTS idx_location_reports_source
            ON location_reports(source_type);

            CREATE INDEX IF NOT EXISTS idx_location_reports_tracking
            ON location_reports(source_tracking_code);

            CREATE TABLE IF NOT EXISTS field_operations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation_code TEXT NOT NULL UNIQUE,
                point_id INTEGER NOT NULL,
                operation_type TEXT NOT NULL,
                operator TEXT,
                operation_date TEXT NOT NULL,
                result TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(point_id) REFERENCES location_points(id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_field_operations_point
            ON field_operations(point_id);

            CREATE INDEX IF NOT EXISTS idx_field_operations_date
            ON field_operations(operation_date);
            """
        )

        # چهار بخش عملیاتی اولیه؛ مرز جغرافیایی بعداً از GIS تعیین می‌شود.
        now = _now()
        for code, name in ZONE_CODES.items():
            conn.execute(
                """
                INSERT OR IGNORE INTO zones
                (code, name, description, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    code,
                    name,
                    "بخش عملیاتی پیشنهادی؛ مرز دقیق پس از تعیین GIS ثبت می‌شود.",
                    now,
                ),
            )


def haversine_distance_m(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """فاصله دو مختصات جغرافیایی بر حسب متر."""
    radius = 6_371_000.0

    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)

    a = (
        math.sin(dp / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(a))


def find_nearby_point(
    latitude: float,
    longitude: float,
    issue_type: str,
    radius_m: float = 100.0,
) -> Optional[dict[str, Any]]:
    """
    نزدیک‌ترین نقطه فعال با همان نوع مشکل را پیدا می‌کند.
    فاصله دقیق با Haversine محاسبه می‌شود.
    """
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM location_points
            WHERE issue_type = ?
              AND status != 'rejected'
              AND latitude BETWEEN ? AND ?
              AND longitude BETWEEN ? AND ?
            """,
            (
                issue_type,
                latitude - 0.002,
                latitude + 0.002,
                longitude - 0.002,
                longitude + 0.002,
            ),
        ).fetchall()

    best = None
    best_distance = float("inf")

    for row in rows:
        distance = haversine_distance_m(
            latitude,
            longitude,
            float(row["latitude"]),
            float(row["longitude"]),
        )
        if distance <= radius_m and distance < best_distance:
            best = dict(row)
            best["distance_m"] = round(distance, 1)
            best_distance = distance

    return best


def generate_point_code(zone_code: str, issue_type: str) -> str:
    """نمونه: ML-M2-RAT-001"""
    prefix = f"ML-{zone_code}-{issue_type}-"

    with _conn() as conn:
        row = conn.execute(
            """
            SELECT code
            FROM location_points
            WHERE code LIKE ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (prefix + "%",),
        ).fetchone()

    number = 1
    if row:
        try:
            number = int(row["code"].rsplit("-", 1)[1]) + 1
        except (ValueError, IndexError):
            number = 1

    return f"{prefix}{number:03d}"


def generate_report_code() -> str:
    """نمونه: RPT-1405-000123"""
    year = datetime.now().year
    prefix = f"RPT-{year}-"

    with _conn() as conn:
        row = conn.execute(
            """
            SELECT report_code
            FROM location_reports
            WHERE report_code LIKE ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (prefix + "%",),
        ).fetchone()

    number = 1
    if row:
        try:
            number = int(row["report_code"].rsplit("-", 1)[1]) + 1
        except (ValueError, IndexError):
            number = 1

    return f"{prefix}{number:06d}"


def generate_operation_code() -> str:
    """نمونه: OP-2026-000001"""
    year = datetime.now().year
    prefix = f"OP-{year}-"

    with _conn() as conn:
        row = conn.execute(
            """
            SELECT operation_code
            FROM field_operations
            WHERE operation_code LIKE ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (prefix + "%",),
        ).fetchone()

    number = 1
    if row:
        try:
            number = int(row["operation_code"].rsplit("-", 1)[1]) + 1
        except (ValueError, IndexError):
            number = 1

    return f"{prefix}{number:06d}"


def create_location_point(
    zone_code: str,
    issue_type: str,
    latitude: float,
    longitude: float,
    address: Optional[str] = None,
    severity: int = 1,
) -> int:
    """ایجاد نقطه فیزیکی جدید و برگرداندن ID آن."""
    if zone_code not in ZONE_CODES:
        raise ValueError("zone_code نامعتبر است.")
    if issue_type not in ISSUE_TYPES:
        raise ValueError("issue_type نامعتبر است.")

    now = _now()
    code = generate_point_code(zone_code, issue_type)

    with _conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO location_points (
                code, zone_code, issue_type,
                latitude, longitude, address,
                first_report_at, last_report_at,
                report_count, severity, status,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 'open', ?, ?)
            """,
            (
                code,
                zone_code,
                issue_type,
                latitude,
                longitude,
                address,
                now,
                now,
                max(1, min(5, severity)),
                now,
                now,
            ),
        )
        return int(cur.lastrowid)


def create_location_report(
    *,
    point_id: Optional[int],
    user_id: Optional[int],
    issue_type: str,
    description: str = "",
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    address: Optional[str] = None,
    photos: Optional[list[str]] = None,
    source_type: str = "BOT",
    source_tracking_code: Optional[str] = None,
    severity: int = 1,
) -> int:
    """
    ثبت گزارش شهروندی.
    اگر point_id وجود داشته باشد، شمارنده نقطه نیز به‌روزرسانی می‌شود.
    """
    if issue_type not in ISSUE_TYPES:
        raise ValueError("issue_type نامعتبر است.")

    allowed_sources = {"BOT", "137", "PHONE", "IN_PERSON", "FIELD", "OTHER"}
    if source_type not in allowed_sources:
        raise ValueError("source_type نامعتبر است.")

    now = _now()
    report_code = generate_report_code()
    photos_json = json.dumps(photos or [], ensure_ascii=False)

    with _conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO location_reports (
                report_code, point_id, user_id,
                source_type, source_tracking_code,
                issue_type, description,
                latitude, longitude, address,
                photos_json, status, severity,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)
            """,
            (
                report_code,
                point_id,
                user_id,
                source_type,
                source_tracking_code,
                issue_type,
                description,
                latitude,
                longitude,
                address,
                photos_json,
                max(1, min(5, severity)),
                now,
                now,
            ),
        )

        report_id = int(cur.lastrowid)

        if point_id is not None:
            conn.execute(
                """
                UPDATE location_points
                SET report_count = report_count + 1,
                    last_report_at = ?,
                    updated_at = ?,
                    severity = MAX(severity, ?)
                WHERE id = ?
                """,
                (now, now, max(1, min(5, severity)), point_id),
            )

        return report_id


def create_field_operation(
    *,
    point_id: int,
    operation_type: str,
    operator: Optional[str] = None,
    operation_date: Optional[str] = None,
    result: Optional[str] = None,
    notes: Optional[str] = None,
) -> int:
    """ثبت عملیات میدانی انجام‌شده روی یک نقطه."""
    now = _now()
    operation_code = generate_operation_code()
    operation_date = operation_date or now[:10]

    with _conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO field_operations (
                operation_code, point_id, operation_type,
                operator, operation_date, result, notes, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                operation_code,
                point_id,
                operation_type,
                operator,
                operation_date,
                result,
                notes,
                now,
            ),
        )

        conn.execute(
            """
            UPDATE location_points
            SET last_visit_at = ?,
                last_action = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (operation_date, operation_type, now, point_id),
        )

        return int(cur.lastrowid)


def get_point(point_id: int) -> Optional[dict[str, Any]]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM location_points WHERE id = ?",
            (point_id,),
        ).fetchone()
    return dict(row) if row else None


def get_point_by_code(code: str) -> Optional[dict[str, Any]]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM location_points WHERE code = ?",
            (code,),
        ).fetchone()
    return dict(row) if row else None


def get_zone_points(
    zone_code: str,
    issue_type: Optional[str] = None,
    status: Optional[str] = None,
) -> list[dict[str, Any]]:
    query = "SELECT * FROM location_points WHERE zone_code = ?"
    params: list[Any] = [zone_code]

    if issue_type:
        query += " AND issue_type = ?"
        params.append(issue_type)

    if status:
        query += " AND status = ?"
        params.append(status)

    query += " ORDER BY last_report_at DESC, id DESC"

    with _conn() as conn:
        rows = conn.execute(query, params).fetchall()

    return [dict(row) for row in rows]


def get_point_reports(point_id: int) -> list[dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM location_reports
            WHERE point_id = ?
            ORDER BY id DESC
            """,
            (point_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_point_operations(point_id: int) -> list[dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM field_operations
            WHERE point_id = ?
            ORDER BY operation_date DESC, id DESC
            """,
            (point_id,),
        ).fetchall()
    return [dict(row) for row in rows]


if __name__ == "__main__":
    init_location_db()
    print("Location database initialized successfully.")
