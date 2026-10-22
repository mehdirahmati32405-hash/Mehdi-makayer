"""تشخیص محدوده واقعی گزارش بر اساس Polygon ذخیره‌شده در جدول zones.

مرزهای M1 تا M4 از GeoJSON داخل ستون polygon_geojson خوانده می‌شوند.
تا زمانی که Polygon واقعی وارد دیتابیس نشده باشد، تابع None برمی‌گرداند و
هیچ محدوده‌ای را به‌صورت حدسی تخصیص نمی‌دهد.
"""

import json
import math
import sqlite3
from typing import Any, Optional

import location_db_upgrade as location_db


def _point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = float(ring[i][0]), float(ring[i][1])
        xj, yj = float(ring[j][0]), float(ring[j][1])
        intersects = ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-15) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def _point_in_polygon(lon: float, lat: float, polygon: list[list[list[float]]]) -> bool:
    if not polygon or not _point_in_ring(lon, lat, polygon[0]):
        return False
    for hole in polygon[1:]:
        if _point_in_ring(lon, lat, hole):
            return False
    return True


def _geometry_contains(geometry: dict[str, Any], lon: float, lat: float) -> bool:
    gtype = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if gtype == "Polygon":
        return _point_in_polygon(lon, lat, coordinates)
    if gtype == "MultiPolygon":
        return any(_point_in_polygon(lon, lat, polygon) for polygon in coordinates)
    return False


def _geojson_contains(value: str, lon: float, lat: float) -> bool:
    try:
        obj = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return False

    if obj.get("type") == "Feature":
        return _geometry_contains(obj.get("geometry") or {}, lon, lat)
    if obj.get("type") == "FeatureCollection":
        return any(
            _geometry_contains(feature.get("geometry") or {}, lon, lat)
            for feature in obj.get("features", [])
        )
    return _geometry_contains(obj, lon, lat)


def zone_from_coordinates(latitude: float, longitude: float) -> Optional[dict[str, str]]:
    """برگرداندن کد و نام محدوده برای مختصات GPS؛ بدون حدس زدن."""
    with location_db._conn() as conn:
        rows = conn.execute(
            "SELECT code, name, polygon_geojson FROM zones ORDER BY code"
        ).fetchall()

    for row in rows:
        geometry = row["polygon_geojson"]
        if geometry and _geojson_contains(geometry, float(longitude), float(latitude)):
            return {"code": row["code"], "name": row["name"]}
    return None


def all_zones_have_boundaries() -> bool:
    with location_db._conn() as conn:
        rows = conn.execute(
            "SELECT code, polygon_geojson FROM zones WHERE code IN ('M1','M2','M3','M4')"
        ).fetchall()
    return len(rows) == 4 and all(row["polygon_geojson"] for row in rows)
