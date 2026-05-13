from __future__ import annotations

import pytest
from enrich_worker.enrich import (
    extract_page_title,
    fetch_enrichment_evidence,
    fetch_from_s3,
    infer_requested_service,
)


def test_extract_page_title_normalizes_whitespace() -> None:
    assert extract_page_title("<html><title> Storm  Lead </title></html>") == "Storm Lead"


def test_infer_requested_service_from_description() -> None:
    assert (
        infer_requested_service(description="Large tree limb on garage", page_text="")
        == "tree_removal"
    )


def test_infer_requested_service_from_page_text() -> None:
    assert (
        infer_requested_service(description=None, page_text="Emergency roof tarp help")
        == "roof_tarp"
    )


@pytest.mark.asyncio
async def test_fetch_from_s3_reads_local_object_storage_key(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STORMLEAD_OBJECT_STORAGE_LOCAL_ROOT", str(tmp_path))
    path = tmp_path / "local-demo" / "run" / "damage-1.jpg"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"photo-bytes")

    assert await fetch_from_s3("local-demo/run/damage-1.jpg") == b"photo-bytes"


@pytest.mark.asyncio
async def test_fetch_from_s3_rejects_urls_and_raw_paths(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STORMLEAD_OBJECT_STORAGE_LOCAL_ROOT", str(tmp_path))
    raw_path = tmp_path / "outside.jpg"
    raw_path.write_bytes(b"outside")

    assert await fetch_from_s3("http://169.254.169.254/latest/meta-data") is None
    assert await fetch_from_s3(str(raw_path)) is None
    assert await fetch_from_s3("../outside.jpg") is None


@pytest.mark.asyncio
async def test_fetch_enrichment_evidence_blocks_unapproved_external_page() -> None:
    evidence = await fetch_enrichment_evidence(
        "http://169.254.169.254/latest/meta-data",
        "large tree on driveway",
    )

    assert not evidence.fetched
    assert evidence.error == "page_url is not locally safe or approved"
    assert evidence.requested_service == "tree_removal"
