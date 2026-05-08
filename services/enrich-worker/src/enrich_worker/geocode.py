from __future__ import annotations

import os
from dataclasses import dataclass

import httpx
from stormlead_core import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class GeoPoint:
    lat: float
    lon: float
    display_name: str | None = None


async def geocode_address(
    address_line1: str, city: str, state: str, zip_: str
) -> GeoPoint | None:
    parts = [address_line1.strip(), city.strip(), state.strip(), zip_.strip()]
    query = ", ".join(part for part in parts if part)
    if not query:
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search"),
                params={"q": query, "format": "json", "limit": 1},
                headers={
                    "User-Agent": os.getenv(
                        "NOMINATIM_USER_AGENT",
                        "stormlead-enrich/1.0 (newbieone56@gmail.com)",
                    )
                },
            )
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        log.warning("geocode.failed", error=str(exc))
        return None

    if not isinstance(payload, list) or not payload:
        return None
    first = payload[0]
    try:
        return GeoPoint(
            lat=float(first["lat"]),
            lon=float(first["lon"]),
            display_name=first.get("display_name"),
        )
    except (KeyError, TypeError, ValueError):
        return None
