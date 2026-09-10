"""
location_intelligence.py
لایه هوشمند تشخیص گزارش تکراری و پرونده‌سازی نقاط مکانی
برای ربات گزارش شهروندی ملایر.

این فایل به location_db_upgrade.py وابسته است و جدول‌های فعلی را حذف نمی‌کند.
"""
from typing import Any, Optional
import location_db_upgrade as location_db


def find_duplicate_candidates(
    latitude: float,
    longitude: float,
    issue_type: str,
    radius_m: float = 150.0,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """چند نقطه نزدیکِ هم‌نوع را برای بررسی تکراری بودن برمی‌گرداند."""
    with location_db._conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM location_points
            WHERE issue_type = ?
              AND status != 'rejected'
              AND latitude BETWEEN ? AND ?
              AND longitude BETWEEN ? AND ?
            """,
            (
                issue_type,
                latitude - 0.003,
                latitude + 0.003,
                longitude - 0.003,
                longitude + 0.003,
            ),
        ).fetchall()

    candidates: list[dict[str, Any]] = []
    for row in rows:
        distance = location_db.haversine_distance_m(
            latitude,
            longitude,
            float(row["latitude"]),
            float(row["longitude"]),
        )
        if distance <= radius_m:
            item = dict(row)
            item["distance_m"] = round(distance, 1)
            candidates.append(item)

    candidates.sort(key=lambda x: (x["distance_m"], -int(x["report_count"])))
    return candidates[:limit]


def classify_duplicate_distance(distance_m: float) -> str:
    """سطح اطمینان برای اتصال گزارش به نقطه موجود."""
    if distance_m <= 50:
        return "high"
    if distance_m <= 100:
        return "medium"
    return "low"


def point_case_summary(point_id: int) -> Optional[dict[str, Any]]:
    """خلاصه پرونده یک نقطه: گزارش‌ها، عملیات و آخرین وضعیت."""
    point = location_db.get_point(point_id)
    if not point:
        return None

    reports = location_db.get_point_reports(point_id)
    operations = location_db.get_point_operations(point_id)

    open_reports = sum(1 for r in reports if r.get("status") == "open")
    resolved_reports = sum(1 for r in reports if r.get("status") == "resolved")

    return {
        "point": point,
        "reports": reports,
        "operations": operations,
        "open_reports": open_reports,
        "resolved_reports": resolved_reports,
        "total_reports": len(reports),
        "total_operations": len(operations),
    }


def set_point_status(point_id: int, status: str) -> bool:
    """تغییر وضعیت پرونده نقطه."""
    allowed = {"open", "in_progress", "resolved", "rejected"}
    if status not in allowed:
        raise ValueError("وضعیت نامعتبر است.")

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with location_db._conn() as conn:
        cur = conn.execute(
            "UPDATE location_points SET status=?, updated_at=? WHERE id=?",
            (status, now, point_id),
        )
        return cur.rowcount > 0
