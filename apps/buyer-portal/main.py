from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

app = FastAPI(title="stormlead buyer portal")
templates = Jinja2Templates(directory="templates")

PING_POST_BASE_URL = os.getenv("PING_POST_BASE_URL", "http://localhost:8003").rstrip("/")


def _local_demo_enabled() -> bool:
    return os.getenv("STORMLEAD_LOCAL_DEMO_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _secure_cookies() -> bool:
    return os.getenv("STORMLEAD_SECURE_COOKIES", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


def _auth(request: Request) -> tuple[str | None, str | None]:
    return request.cookies.get("buyer_id"), request.cookies.get("buyer_api_key")


async def _ping_post(path: str, api_key: str | None, **kwargs: Any) -> Any:
    headers = kwargs.pop("headers", {})
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.request(
            kwargs.pop("method", "GET"), f"{PING_POST_BASE_URL}{path}", headers=headers, **kwargs
        )
    if response.status_code >= 400:
        return {"error": response.text, "status_code": response.status_code}
    return response.json() if response.content else {}


def _login_redirect() -> RedirectResponse:
    return RedirectResponse("/login", status_code=303)


def _money(cents: Any) -> str:
    try:
        amount_cents = int(cents or 0)
    except (TypeError, ValueError):
        amount_cents = 0
    return f"${amount_cents / 100:,.2f}"


def _wallet_view(wallet: Any) -> dict[str, str]:
    data = wallet if isinstance(wallet, dict) else {}
    return {
        "balance": _money(data.get("deposit_balance_cents")),
        "lifetime_spend": _money(data.get("lifetime_spend_cents")),
        "monthly_budget": _money(data.get("monthly_budget_cents")),
        "daily_cap": str(data.get("daily_cap") or "not set"),
    }


def _redirect_wallet(**params: str) -> RedirectResponse:
    query = urlencode({key: value for key, value in params.items() if value})
    suffix = f"?{query}" if query else ""
    return RedirectResponse(f"/buyer-portal/wallet{suffix}", status_code=303)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    buyer_id, _api_key = _auth(request)
    if not buyer_id:
        return _login_redirect()
    return RedirectResponse("/buyer-portal/wallet", status_code=303)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"active_page": "login"})


@app.post("/login")
async def login(request: Request, buyer_id: str = Form(...), buyer_api_key: str = Form(...)):
    wallet = await _ping_post(f"/v1/buyers/{buyer_id}/wallet", buyer_api_key)
    if isinstance(wallet, dict) and wallet.get("error"):
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "active_page": "login",
                "error": "Buyer ID or API key was rejected by StormLead.",
            },
            status_code=401,
        )
    response = RedirectResponse("/buyer-portal/wallet", status_code=303)
    secure = _secure_cookies()
    response.set_cookie("buyer_id", buyer_id, httponly=True, samesite="lax", secure=secure)
    response.set_cookie("buyer_api_key", buyer_api_key, httponly=True, samesite="lax", secure=secure)
    return response


@app.get("/buyer-portal/wallet", response_class=HTMLResponse)
async def wallet(request: Request):
    buyer_id, api_key = _auth(request)
    if not buyer_id:
        return _login_redirect()
    wallet_data = await _ping_post(f"/v1/buyers/{buyer_id}/wallet", api_key)
    report = await _ping_post(f"/v1/buyers/{buyer_id}/daily-report", api_key)
    return templates.TemplateResponse(
        request,
        "wallet.html",
        {
            "active_page": "wallet",
            "buyer_id": buyer_id,
            "wallet": wallet_data,
            "wallet_view": _wallet_view(wallet_data),
            "report": report,
            "local_demo_enabled": _local_demo_enabled(),
            "deposit_status": request.query_params.get("deposit_status"),
            "deposit_message": request.query_params.get("deposit_message"),
        },
    )


if _local_demo_enabled():

    @app.post("/buyer-portal/wallet/deposit")
    async def deposit(
        request: Request,
        amount_cents: str = Form(...),
        external_reference: str = Form(default=""),
    ) -> RedirectResponse:
        buyer_id, api_key = _auth(request)
        if not buyer_id:
            return _login_redirect()

        normalized_amount = amount_cents.strip()
        if not normalized_amount.isdecimal():
            return _redirect_wallet(
                deposit_status="error", deposit_message="Amount must be a positive integer in cents."
            )

        amount = int(normalized_amount)
        if amount <= 0 or amount > 10_000_000:
            return _redirect_wallet(
                deposit_status="error",
                deposit_message="Amount must be a positive integer between 1 and 10000000 cents.",
            )

        reference = external_reference.strip()[:255] or "buyer-portal-local-synthetic-refill"
        result = await _ping_post(
            f"/v1/buyers/{buyer_id}/deposits",
            api_key,
            method="POST",
            json={"amount_cents": amount, "external_reference": reference},
        )
        if isinstance(result, dict) and result.get("error"):
            return _redirect_wallet(
                deposit_status="error", deposit_message=str(result.get("error"))[:300]
            )

        return _redirect_wallet(
            deposit_status="ok",
            deposit_message=f"Synthetic wallet credit recorded. New balance: {_money(result.get('deposit_balance_cents') if isinstance(result, dict) else 0)}.",
        )


@app.get("/buyer-portal/leads", response_class=HTMLResponse)
async def leads(request: Request):
    buyer_id, api_key = _auth(request)
    if not buyer_id:
        return _login_redirect()
    report = await _ping_post(f"/v1/buyers/{buyer_id}/daily-report", api_key)
    return templates.TemplateResponse(
        request,
        "leads.html",
        {
            "active_page": "leads",
            "buyer_id": buyer_id,
            "report": report,
            "leads": report.get("delivered_leads", []),
        },
    )


@app.get("/buyer-portal/review", response_class=HTMLResponse)
async def review_page(request: Request):
    buyer_id, _api_key = _auth(request)
    if not buyer_id:
        return _login_redirect()
    return templates.TemplateResponse(
        request,
        "review.html",
        {"active_page": "review", "buyer_id": buyer_id, "result": None},
    )


@app.post("/buyer-portal/review", response_class=HTMLResponse)
async def submit_review(
    request: Request,
    lead_id: str = Form(...),
    reason: str = Form(...),
    notes: str = Form(default=""),
):
    buyer_id, api_key = _auth(request)
    if not buyer_id:
        return _login_redirect()
    result = await _ping_post(
        f"/v1/leads/{lead_id}/return",
        api_key,
        method="POST",
        json={"reason": reason, "notes": notes, "requested_by": buyer_id, "evidence": {}},
    )
    return templates.TemplateResponse(
        request,
        "review.html",
        {"active_page": "review", "buyer_id": buyer_id, "result": result},
    )
