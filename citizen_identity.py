"""هویت و کدگذاری استاندارد شهروندان و گزارش‌های ربات."""
from datetime import datetime, timezone

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

import db

router = Router()


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
        row = conn.execute("SELECT citizen_number FROM citizen_codes WHERE user_id = ?", (user_id,)).fetchone()
        if row:
            number = int(row["citizen_number"])
        else:
            row = conn.execute("SELECT COALESCE(MAX(citizen_number), 0) + 1 AS next_number FROM citizen_codes").fetchone()
            number = int(row["next_number"])
            conn.execute(
                "INSERT INTO citizen_codes (user_id, citizen_number, created_at) VALUES (?, ?, ?)",
                (user_id, number, datetime.now(timezone.utc).isoformat()),
            )
    return f"کد شهروندی-{number:05d}"


def report_code(report_id: int) -> str:
    """Return a report code independent from the citizen identity."""
    return f"کد گزارش-{datetime.now().year}-{report_id:05d}"


@router.message(Command("myid"))
async def cmd_my_citizen_code(message: Message) -> None:
    if message.chat.type != "private":
        return
    code = citizen_code(message.from_user.id)
    await message.answer(
        f"👤 <b>شناسه شهروندی شما</b>\n\n{code}\n\n"
        "این کد برای پیگیری سوابق گزارش‌های شما استفاده می‌شود."
    )


# handlers.py calls db.report_code(...), so replacing the formatter here applies
# the new public report-code format without changing stored report IDs.
db.report_code = report_code
