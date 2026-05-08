from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
from geoalchemy2 import WKTElement
from hatchet_sdk import Context, Hatchet
from stormlead_core import LeadStatus, PipelineState, bind_correlation_id, emit_event, emit_metric
from stormlead_db import LeadRow, get_session, record_transition

from enrich_worker.geocode import geocode_address
from enrich_worker.photo import classify_photo


@dataclass(frozen=True)
class EnrichmentEvidence:
    page_url: str
    fetched: bool
    status_code: int | None
    title: str | None
    requested_service: str | None
    error: str | None = None


_SERVICE_PATTERNS = {
    "tree_removal": re.compile(r"\b(tree|limb|branch|arborist|stump)\b", re.I),
    "roof_tarp": re.compile(r"\b(roof|tarp|shingle|leak)\b", re.I),
    "water_mitigation": re.compile(r"\b(water|flood|mitigation|drywall)\b", re.I),
}


def extract_page_title(html: str) -> str | None:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if not match:
        return None
    return re.sub(r"\s+", " ", match.group(1)).strip()[:200] or None


def infer_requested_service(*, description: str | None, page_text: str) -> str | None:
    haystack = f"{description or ''}\n{page_text}"
    for service, pattern in _SERVICE_PATTERNS.items():
        if pattern.search(haystack):
            return service
    return None


async def fetch_enrichment_evidence(
    page_url: str, damage_description: str | None
) -> EnrichmentEvidence:
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
            response = await client.get(page_url)
        text = response.text[:20_000]
        return EnrichmentEvidence(
            page_url=page_url,
            fetched=True,
            status_code=response.status_code,
            title=extract_page_title(text),
            requested_service=infer_requested_service(
                description=damage_description,
                page_text=text,
            ),
        )
    except Exception as exc:
        return EnrichmentEvidence(
            page_url=page_url,
            fetched=False,
            status_code=None,
            title=None,
            requested_service=infer_requested_service(description=damage_description, page_text=""),
            error=f"{type(exc).__name__}: {exc}",
        )


async def fetch_from_s3(s3_key: str) -> bytes | None:
    """Best-effort photo byte fetcher; tests can patch this for private S3."""
    if s3_key.startswith(("http://", "https://")):
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(s3_key)
                response.raise_for_status()
                return response.content
        except Exception:
            return None
    path = Path(s3_key)
    if path.is_file():
        return path.read_bytes()
    return None


async def _classify_lead_photos(photo_s3_keys: list[str]) -> list[dict[str, Any]]:
    classifications: list[dict[str, Any]] = []
    for key in photo_s3_keys[:3]:
        image_bytes = await fetch_from_s3(key)
        if image_bytes is None:
            continue
        classification = await classify_photo(image_bytes)
        if classification is not None:
            classifications.append({"s3_key": key, **classification})
    return classifications


async def enrich_lead(context: Context) -> dict[str, Any]:
    workflow_input = context.workflow_input
    payload = workflow_input() if callable(workflow_input) else workflow_input
    lead_id = UUID(payload["lead_id"])
    bind_correlation_id(payload.get("correlation_id") or str(lead_id))
    run_id = str(payload.get("run_id") or uuid4())

    async with get_session() as s:
        row = await s.get(LeadRow, lead_id)
        if row is None:
            raise ValueError(f"lead {lead_id} not found")
        page_url = row.page_url
        damage_description = row.damage_description
        address = (row.address_line1, row.city, row.state, row.zip)
        photo_s3_keys = list(row.photo_s3_keys or [])

    evidence = await fetch_enrichment_evidence(page_url, damage_description)
    geo_point = await geocode_address(*address)
    photo_classifications = await _classify_lead_photos(photo_s3_keys)

    async with get_session() as s:
        row = await s.get(LeadRow, lead_id)
        if row is None:
            raise ValueError(f"lead {lead_id} not found")
        if evidence.requested_service and not row.requested_service:
            row.requested_service = evidence.requested_service
        if geo_point is not None:
            row.geom = WKTElement(f"POINT({geo_point.lon} {geo_point.lat})", srid=4326)
        if photo_classifications:
            row.damage_tier = str(photo_classifications[0].get("damage_tier"))
        row.status = LeadStatus.ENRICHED.value
        payload = {
            **evidence.__dict__,
            "geocode": geo_point.__dict__ if geo_point is not None else None,
            "photo_classifications": photo_classifications,
        }
        await record_transition(
            s,
            lead_id=lead_id,
            from_state=PipelineState.CAPTURED,
            to_state=PipelineState.ENRICHED,
            event_type="lead.enriched",
            task_name="enrich_worker.enrich_lead",
            workflow_run_id=run_id,
            payload=payload,
        )

    Hatchet(debug=False).event.push(
        "lead.enriched",
        {"lead_id": str(lead_id), "run_id": run_id, "correlation_id": str(lead_id)},
    )
    emit_event("enriched", lead_id=str(lead_id), service="enrich-worker")
    emit_metric("funnel.enriched", lead_id=str(lead_id), service="enrich-worker")
    return {"lead_id": str(lead_id), "evidence": payload}
