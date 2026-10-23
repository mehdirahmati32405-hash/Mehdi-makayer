"""هویت و کدگذاری استاندارد شهروندان و گزارش‌های ربات.

کد شهروندی پایدار است و به شناسه تلگرام وابسته به‌صورت مستقیم نمایش داده نمی‌شود.
کد گزارش نیز مستقل از کد شهروندی و مناسب پیگیری شهروند است.
"""
from datetime import datetime
import db


def _ensure_table() -> None:
    with db.get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS citizen_codes (
                user_id INTEGER PRIMARY KEY,
                citizen_number INTEGER UNIQUE NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


def citizen_code(user_id: int) -> str:
    """Return a stable public-facing citizen code such as «کد شهروندی-00001»."""
    _ensure_table()
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT citizen_number FROM citizen_codes WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row:
            number = int(row["citizen_number"])
        else:
            row = conn.execute(
                "SELECT COALESCE(MAX(citizen_number), 0) + 1 AS next_number FROM citizen_codes"
            ).fetchone()
            number = int(row["next_number"])
            conn.execute(
                "INSERT INTO citizen_codes (user_id, citizen_number, created_at) VALUES (?, ?, ?)",
                (user_id, number, datetime.utcnow().isoformat()),
            )
    return f"کد شهروندی-{number:05d}"


def report_code(report_id: int) -> str:
    """Return a report code independent from the citizen identity."""
    year = datetime.now().year
    return f"کد گزارش-{year}-{report_id:05d}"


# Keep all existing handlers unchanged while upgrading the public code format.
# handlers.py calls db.report_code(...), so replacing the formatter here applies
# the new format consistently without changing stored report IDs.
db.report_code = report_code
