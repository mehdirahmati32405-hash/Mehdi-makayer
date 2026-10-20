"""Operational analytics context for the citizen-facing AI assistant."""

import db


def build_analytics_context(days: int = 30) -> str:
    data = db.get_ai_analytics(days=days)
    lines = [
        f"داده‌های واقعی سامانه برای {days} روز اخیر:",
        f"- تعداد گزارش‌ها: {data['total']}",
        f"- گزارش‌های دارای موقعیت مکانی: {data['with_location']}",
    ]

    if data["by_category"]:
        lines.append("- پرتکرارترین دسته‌ها:")
        for item in data["by_category"]:
            lines.append(f"  • {item['category']}: {item['count']}")

    if data["by_status"]:
        lines.append("- وضعیت گزارش‌ها:")
        for item in data["by_status"]:
            lines.append(f"  • {item['status']}: {item['count']}")

    if data["recent"]:
        lines.append("- چند گزارش اخیر برای درک روند فعلی:")
        for item in data["recent"]:
            lines.append(
                f"  • گزارش {item['id']}: {item['category']} / {item['status']} / {item['created_at']}"
            )

    lines.append(
        "قانون تحلیل: این داده‌ها فقط برای تحلیل استفاده شوند. "
        "اگر کاربر درباره علت، پیش‌بینی یا راهکار سؤال کرد، تحلیل را از داده‌ها جدا کن "
        "و هیچ علت یا روندی را قطعی اعلام نکن مگر داده کافی داشته باشی."
    )
    return "\n".join(lines)
