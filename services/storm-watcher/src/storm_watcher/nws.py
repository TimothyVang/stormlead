"""nws cap alerts poller. free, no key, json.

api: https://api.weather.gov/alerts/active
docs: https://www.weather.gov/documentation/services-web-api

we filter to severe + tornado + hurricane + tropical-storm warnings in our 8 target states.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
from stormlead_core import Storm, StormSeverity, get_logger

log = get_logger(__name__)

TARGET_STATES = ("FL", "GA", "SC", "NC", "AL", "MS", "LA", "TX")

# events worth triggering on (case-sensitive per nws)
SEVERE_EVENTS = {
    "Hurricane Warning",
    "Hurricane Watch",
    "Tropical Storm Warning",
    "Tropical Storm Watch",
    "Severe Thunderstorm Warning",
    "Tornado Warning",
    "High Wind Warning",
}


async def fetch_active_alerts() -> list[dict[str, Any]]:
    """returns the raw 'features' list from nws alerts endpoint."""
    headers = {
        "User-Agent": os.environ["NWS_USER_AGENT"],
        "Accept": "application/geo+json",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        params = {
            "status": "actual",
            "message_type": "alert",
            "area": ",".join(TARGET_STATES),
        }
        r = await client.get(
            "https://api.weather.gov/alerts/active", params=params, headers=headers
        )
        r.raise_for_status()
        return r.json().get("features", [])


def normalize_alert(feature: dict[str, Any]) -> Storm | None:
    """convert one nws alert feature into a normalized Storm event.

    return None if it's not an event we care about.
    """
    props = feature.get("properties", {})
    event = props.get("event", "")
    if event not in SEVERE_EVENTS:
        return None

    geom = feature.get("geometry") or {}
    bbox_wkt = None
    if geom.get("type") == "Polygon":
        # build a simple wkt bbox; full geom is stored in raw for postgis later
        coords = geom.get("coordinates", [[]])[0]
        if coords:
            xs = [c[0] for c in coords]
            ys = [c[1] for c in coords]
            bbox_wkt = (
                f"POLYGON(({min(xs)} {min(ys)}, {max(xs)} {min(ys)}, "
                f"{max(xs)} {max(ys)}, {min(xs)} {max(ys)}, {min(xs)} {min(ys)}))"
            )

    severity_map = {
        "Watch": StormSeverity.WATCH,
        "Warning": StormSeverity.WARNING,
    }
    severity = StormSeverity.WARNING
    for k, v in severity_map.items():
        if k in event:
            severity = v
            break

    affected_states: list[str] = []
    for s in TARGET_STATES:
        if s in (props.get("areaDesc") or ""):
            affected_states.append(s)

    sent = props.get("sent")
    detected_at = datetime.fromisoformat(sent.replace("Z", "+00:00")) if sent else datetime.now(UTC)

    return Storm(
        id=uuid4(),
        external_id=props.get("id", str(uuid4())),
        name=event + " - " + (props.get("headline") or "")[:64],
        source="nws",
        severity=severity,
        affected_states=affected_states,
        bbox_wkt=bbox_wkt,
        detected_at=detected_at,
        raw=feature,
    )
