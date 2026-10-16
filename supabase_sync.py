import os
from typing import Any

import aiohttp

import config


SUPABASE_URL = getattr(config, "SUPABASE_URL", "")
SUPABASE_KEY = getattr(config, "SUPABASE_SECRET_KEY", "")


def enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


async def _rpc(function_name: str, payload: dict[str, Any]) -> Any:
    if not enabled():
        return None

    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/rpc/{function_name}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }

    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, json=payload, headers=headers) as response:
            body = await response.text()
            if response.status >= 400:
                raise RuntimeError(f"Supabase RPC {function_name} failed ({response.status}): {body[:500]}")
            if not body:
                return None
            return await response.json(content_type=None)


async def ingest_report(
    *,
    external_ref: str,
    telegram_user_id: int,
    reporter_name: str,
    category: str,
    description: str,
    latitude: float,
    longitude: float,
    report_type: str,
    priority: str = "normal",
) -> dict[str, Any] | None:
    """Create/find the matching report in the municipal Supabase panel."""
    result = await _rpc(
        "ingest_telegram_report",
        {
            "p_external_ref": external_ref,
            "p_telegram_user_id": telegram_user_id,
            "p_reporter_name": reporter_name,
            "p_category": category,
            "p_description": description,
            "p_latitude": latitude,
            "p_longitude": longitude,
            "p_report_type": report_type,
            "p_priority": priority,
        },
    )
    if isinstance(result, list) and result:
        return result[0]
    return None


async def sync_status(external_ref: str | None, status_key: str, feedback: str | None = None) -> bool:
    if not external_ref:
        return False
    result = await _rpc(
        "sync_telegram_report_status",
        {
            "p_external_ref": external_ref,
            "p_status": status_key,
            "p_feedback": feedback,
        },
    )
    return bool(result)
