from __future__ import annotations

from enrich_worker.enrich import extract_page_title, infer_requested_service


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
