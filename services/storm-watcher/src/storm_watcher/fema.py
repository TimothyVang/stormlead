"""fema openfema disaster declarations poller.

api: https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries
no key required.

we filter to incidentType in [Hurricane, Severe Storm, Severe Storm(s), Coastal Storm,
Tornado] and state in TARGET_STATES, then emit a Storm event with severity=DECLARED.

declared status unlocks higher buyer bids ("post-disaster premium").
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
from stormlead_core import Storm, StormSeverity, get_logger

log = get_logger(__name__)

TARGET_STATES = ("FL", "GA", "SC", "NC", "AL", "MS", "LA", "TX")
INCIDENT_TYPES = (
    "Hurricane",
    "Severe Storm",
    "Severe Storm(s)",
    "Coastal Storm",
    "Tornado",
)


async def fetch_recent_declarations(days_back: int = 90) -> list[dict[str, Any]]:
    base = os.getenv("FEMA_API_BASE", "https://www.fema.gov/api/open/v2")
    since = (datetime.now(UTC) - timedelta(days=days_back)).isoformat()
    states_filter = " or ".join(f"state eq '{s}'" for s in TARGET_STATES)
    types_filter = " or ".join(f"incidentType eq '{t}'" for t in INCIDENT_TYPES)
    flt = f"declarationDate gt '{since}' and ({states_filter}) and ({types_filter})"

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{base}/DisasterDeclarationsSummaries",
            params={"$filter": flt, "$top": 1000, "$orderby": "declarationDate desc"},
        )
        r.raise_for_status()
        return r.json().get("DisasterDeclarationsSummaries", [])


def normalize_declaration(d: dict[str, Any]) -> Storm:
    declared = d.get("declarationDate")
    declared_at = (
        datetime.fromisoformat(declared.replace("Z", "+00:00")) if declared else datetime.now(UTC)
    )
    return Storm(
        id=uuid4(),
        external_id=f"DR-{d.get('disasterNumber')}-{d.get('state')}",
        name=d.get("declarationTitle") or d.get("incidentType") or "FEMA Disaster",
        source="fema",
        severity=StormSeverity.DECLARED,
        affected_states=[d.get("state", "")],
        affected_counties=[d.get("placeCode", "")] if d.get("placeCode") else [],
        detected_at=declared_at,
        declared_at=declared_at,
        raw=d,
    )
