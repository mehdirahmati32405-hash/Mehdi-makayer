"""Operational analytics context for the citizen-facing AI assistant."""

from datetime import datetime, timedelta, timezone

import db


def build_analytics_context(days: int = 30) -> str:
    """Read aggregate, non-sensitive report patterns directly from the bot DB."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with db.get_conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS c FROM reports WHERE created_at >= ?", (since,)
        ).fetchone()["c"]
        located = conn.execute(
            "SELECT COUNT(*) AS c FROM reports WHERE created_at >= ? "
            "AND latitude IS NOT NULL AND longitude IS NOT NULL", (since,)
        ).fetchone()["c"]
        categories = conn.execute(
            "SELECT category, COUNT(*) AS c FROM reports WHERE created_at >= ? "
            "GROUP BY category ORDER BY c DESC LIMIT 8", (since,)
        ).fetchall()
        statuses = conn.execute(
            "SELECT status, COUNT(*) AS c FROM reports WHERE created_at >= ? "
            "GROUP BY status ORDER BY c DESC", (since,)
        ).fetchall()

    lines = [
        f"داده‌های واقعی سامانه برای {days} روز اخیر:",
        f"- تعداد گزارش‌ها: {total}",
        f"- گزارش‌های دارای موقعیت مکانی: {located}",
    ]
    if categories:
        lines.append("- پرتکرارترین دسته‌ها:")
        lines.extend(f"  • {r['category']}: {r['c']}" for r in categories)
    if statuses:
        lines.append("- وضعیت گزارش‌ها:")
        lines.extend(f"  • {r['status']}: {r['c']}" for r in statuses)
    lines.append(
        "قانون تحلیل: این اعداد فقط برای تحلیل روند هستند. علت، پیش‌بینی یا اولویت‌بندی "
        "را قطعی اعلام نکن مگر داده کافی وجود داشته باشد."
    )
    return "\n".join(lines)
