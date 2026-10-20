"""Operational analytics context for the citizen-facing AI assistant."""

from datetime import datetime, timedelta, timezone

import db


def build_analytics_context(days: int = 30) -> str:
    """Read aggregate, non-sensitive report patterns and trend signals."""
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=days)).isoformat()
    previous_since = (now - timedelta(days=days * 2)).isoformat()

    with db.get_conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS c FROM reports WHERE created_at >= ?", (since,)
        ).fetchone()["c"]
        previous_total = conn.execute(
            "SELECT COUNT(*) AS c FROM reports WHERE created_at >= ? AND created_at < ?",
            (previous_since, since),
        ).fetchone()["c"]
        located = conn.execute(
            "SELECT COUNT(*) AS c FROM reports WHERE created_at >= ? "
            "AND latitude IS NOT NULL AND longitude IS NOT NULL", (since,)
        ).fetchone()["c"]
        categories = conn.execute(
            "SELECT category, COUNT(*) AS c FROM reports WHERE created_at >= ? "
            "GROUP BY category ORDER BY c DESC LIMIT 8", (since,)
        ).fetchall()
        previous_categories = conn.execute(
            "SELECT category, COUNT(*) AS c FROM reports "
            "WHERE created_at >= ? AND created_at < ? GROUP BY category",
            (previous_since, since),
        ).fetchall()
        statuses = conn.execute(
            "SELECT status, COUNT(*) AS c FROM reports WHERE created_at >= ? "
            "GROUP BY status ORDER BY c DESC", (since,)
        ).fetchall()

    previous_map = {r["category"]: r["c"] for r in previous_categories}
    category_lines = []
    for row in categories:
        old = previous_map.get(row["category"], 0)
        if old > 0:
            change = round(((row["c"] - old) / old) * 100, 1)
            trend = f"؛ تغییر نسبت به بازه قبلی: {change:+}%"
        elif row["c"] > 0:
            trend = "؛ در بازه قبلی داده‌ای برای این دسته وجود نداشت"
        else:
            trend = ""
        category_lines.append(f"  • {row['category']}: {row['c']}{trend}")

    if previous_total > 0:
        total_change = round(((total - previous_total) / previous_total) * 100, 1)
        total_trend = f"{total_change:+}%"
    else:
        total_trend = "قابل محاسبه نیست"

    lines = [
        f"داده‌های واقعی سامانه برای {days} روز اخیر:",
        f"- تعداد گزارش‌ها: {total}",
        f"- تعداد گزارش‌ها در بازه قبلی مشابه: {previous_total}",
        f"- تغییر حجم گزارش‌ها نسبت به بازه قبلی: {total_trend}",
        f"- گزارش‌های دارای موقعیت مکانی: {located}",
    ]
    if categories:
        lines.append("- پرتکرارترین دسته‌ها و روند آنها:")
        lines.extend(category_lines)
    if statuses:
        lines.append("- وضعیت گزارش‌ها:")
        lines.extend(f"  • {r['status']}: {r['c']}" for r in statuses)

    lines.append(
        "قانون تحلیل: اعداد واقعی را از تفسیر AI جدا کن. افزایش یک دسته به‌تنهایی "
        "به معنی علت قطعی یا بحران نیست. اگر داده کافی برای نتیجه‌گیری وجود ندارد، "
        "شفاف اعلام کن. اولویت پیشنهادی را به‌عنوان پیشنهاد مدیریتی، نه واقعیت قطعی، بیان کن. "
        "از اطلاعات هویتی و حدس درباره افراد استفاده نکن."
    )
    return "\n".join(lines)
