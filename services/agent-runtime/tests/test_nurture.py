from __future__ import annotations

from uuid import uuid4

from agent_runtime.nurture import nurture_lead


class _Context:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def workflow_input(self) -> dict:
        return self._payload


def test_nurture_accepts_unsold_payload_shape() -> None:
    lead_id = uuid4()
    context = _Context({"lead_id": str(lead_id), "source_event": "lead.unsold"})
    assert callable(nurture_lead)
    assert context.workflow_input()["lead_id"] == str(lead_id)
    assert context.workflow_input()["source_event"] == "lead.unsold"
