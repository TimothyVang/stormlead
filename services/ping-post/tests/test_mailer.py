from __future__ import annotations

import csv
from io import StringIO
from types import SimpleNamespace
from uuid import UUID

import httpx
import ping_post.api as api_module
import pytest
from ping_post import mailer


class FakeMailerSession:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows
        self.executed = False

    async def __aenter__(self) -> FakeMailerSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def execute(self, _statement: object) -> FakeMailerExecuteResult:
        self.executed = True
        return FakeMailerExecuteResult(self.rows)


class FakeMailerExecuteResult:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def scalars(self) -> FakeMailerScalarResult:
        return FakeMailerScalarResult(self.rows)


class FakeMailerScalarResult:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def all(self) -> list[object]:
        return list(self.rows)


@pytest.fixture
async def client():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api_module.app), base_url="http://test"
    ) as test_client:
        yield test_client


async def test_export_mailer_csv_sanitizes_spreadsheet_formula_cells(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lead = SimpleNamespace(
        id=UUID("12345678-1234-5678-1234-567812345678"),
        name="=HYPERLINK('https://example.invalid')",
        address_line1="+100 Private St",
        city="-Orlando",
        state="FL",
        zip="@32801",
        requested_service="tree_removal",
        damage_description="=cmd|' /C calc'!A0" + "x" * 250,
    )
    fake_session = FakeMailerSession([lead])
    monkeypatch.setattr(mailer, "get_session", lambda: fake_session)

    csv_body = await mailer.export_mailer_csv(state="fl", service=" Tree_Removal ", status="unsold")

    rows = list(csv.reader(StringIO(csv_body)))
    assert fake_session.executed is True
    assert rows[0] == mailer.HEADER
    assert rows[1][0] == "TRACK-12345678"
    assert rows[1][1] == "'=HYPERLINK('https://example.invalid')"
    assert rows[1][2] == "'+100 Private St"
    assert rows[1][3] == "'-Orlando"
    assert rows[1][4] == "FL"
    assert rows[1][5] == "'@32801"
    assert rows[1][6] == "tree_removal"
    assert rows[1][7].startswith("'=cmd|")
    assert len(rows[1][7]) == 201


async def test_admin_mailer_csv_response_is_attachment(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_export_mailer_csv(
        state: str | None = None, service: str | None = None, status: str = "unsold"
    ) -> str:
        assert state == "FL"
        assert service == "tree_removal"
        assert status == "qualified"
        return "tracking_code,name\nTRACK-1,Example\n"

    monkeypatch.setattr(api_module, "export_mailer_csv", fake_export_mailer_csv)

    response = await client.get(
        "/v1/admin/export/mailer-csv",
        params={"state": "FL", "service": "tree_removal", "status": "qualified"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == (
        'attachment; filename="stormlead-mailer.csv"'
    )
    assert response.text == "tracking_code,name\nTRACK-1,Example\n"
