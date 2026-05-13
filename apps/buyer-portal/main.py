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
READINESS_REQUIREMENT_COPY = {
    "api_key_ready": (
        "API key active",
        "Rotate or request a buyer API key, then sign portal/API requests with it.",
    ),
    "budget_ready": (
        "Monthly budget configured",
        "Set a monthly lead budget before routing paid-pilot leads.",
    ),
    "caps_ready": ("Daily cap configured", "Set a daily lead cap that matches your team capacity."),
    "price_ready": ("Bid prices configured", "Set valid prices for lead and call products."),
    "service_ready": (
        "Service coverage configured",
        "Choose at least one service category this buyer can fulfill.",
    ),
    "terms_accepted": (
        "Terms accepted",
        "Complete buyer terms, return policy, and paid-pilot operating notes.",
    ),
    "webhook_ready": (
        "Webhook configured",
        "Set a local-safe or approved buyer delivery webhook and secret.",
    ),
    "wallet_ready": ("Wallet funded", "Refill the wallet above the low-balance threshold."),
    "zip_ready": ("ZIP coverage configured", "Add target or exclusive ZIP coverage."),
}


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


def _has_portal_auth(request: Request) -> bool:
    buyer_id, api_key = _auth(request)
    return bool(buyer_id and api_key)


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


def _readiness_view(buyer: Any, report: Any, reconciliation: Any) -> dict[str, Any]:
    buyer_data = buyer if isinstance(buyer, dict) else {}
    report_data = report if isinstance(report, dict) else {}
    reconciliation_data = reconciliation if isinstance(reconciliation, dict) else {}
    onboarding = buyer_data.get("onboarding_readiness") or {}
    buyer_wallet = report_data.get("buyer") or buyer_data
    wallet = report_data.get("wallet") or {}
    ledger = reconciliation_data.get("ledger") or {}
    payment = reconciliation_data.get("payment_readiness") or {}
    missing = onboarding.get("missing_requirements") or []
    delta_cents = int(ledger.get("delta_cents") or 0)
    threshold_cents = int(
        buyer_data.get("low_balance_threshold_cents")
        or buyer_data.get("crm_low_balance_threshold_cents")
        or wallet.get("low_balance_threshold_cents")
        or 0
    )
    missing_items = [
        {
            "key": item,
            "label": READINESS_REQUIREMENT_COPY.get(item, (item.replace("_", " ").title(), ""))[0],
            "action": READINESS_REQUIREMENT_COPY.get(item, ("", "Complete this buyer setup item."))[
                1
            ],
        }
        for item in missing
    ]
    return {
        "autopilot_ready": bool(onboarding.get("autopilot_ready")),
        "status_label": "Ready" if onboarding.get("autopilot_ready") else "Needs setup",
        "missing_requirements": missing,
        "missing_items": missing_items,
        "coverage_zips": onboarding.get("coverage_zips") or [],
        "balance": _money(buyer_wallet.get("deposit_balance_cents")),
        "low_balance_threshold": _money(threshold_cents),
        "wallet_below_threshold": bool(wallet.get("below_threshold")),
        "recommended_refill": _money(wallet.get("recommended_refill_cents")),
        "ledger_reconciled": bool(ledger.get("reconciled")),
        "ledger_delta": _money(abs(delta_cents)),
        "payment_local_ready": bool(payment.get("local_refills_ready")),
        "live_payments_approved": bool(payment.get("live_payments_approved")),
    }


def _redirect_wallet(**params: str) -> RedirectResponse:
    query = urlencode({key: value for key, value in params.items() if value})
    suffix = f"?{query}" if query else ""
    return RedirectResponse(f"/buyer-portal/wallet{suffix}", status_code=303)


async def _wallet_context(
    request: Request,
    *,
    buyer_id: str,
    api_key: str | None,
    rotated_api_key: str | None = None,
) -> dict[str, Any]:
    wallet_data = await _ping_post(f"/v1/buyers/{buyer_id}/wallet", api_key)
    report = await _ping_post(f"/v1/buyers/{buyer_id}/daily-report", api_key)
    buyer_profile = await _ping_post(f"/v1/buyers/{buyer_id}", api_key)
    reconciliation = await _ping_post(f"/v1/buyers/{buyer_id}/wallet/reconciliation", api_key)
    return {
        "active_page": "wallet",
        "buyer_id": buyer_id,
        "wallet": wallet_data,
        "wallet_view": _wallet_view(wallet_data),
        "report": report,
        "buyer": buyer_profile,
        "reconciliation": reconciliation,
        "readiness_view": _readiness_view(buyer_profile, report, reconciliation),
        "local_demo_enabled": _local_demo_enabled(),
        "deposit_status": request.query_params.get("deposit_status"),
        "deposit_message": request.query_params.get("deposit_message"),
        "key_status": request.query_params.get("key_status"),
        "key_message": request.query_params.get("key_message"),
        "rotated_api_key": rotated_api_key,
    }


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if not _has_portal_auth(request):
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
    response.set_cookie(
        "buyer_api_key", buyer_api_key, httponly=True, samesite="lax", secure=secure
    )
    return response


@app.get("/buyer-portal/wallet", response_class=HTMLResponse)
async def wallet(request: Request):
    buyer_id, api_key = _auth(request)
    if not buyer_id or not api_key:
        return _login_redirect()
    return templates.TemplateResponse(
        request,
        "wallet.html",
        await _wallet_context(request, buyer_id=buyer_id, api_key=api_key),
    )


@app.post("/buyer-portal/api-key/rotate", response_class=HTMLResponse)
async def rotate_api_key(request: Request):
    buyer_id, api_key = _auth(request)
    if not buyer_id or not api_key:
        return _login_redirect()

    result = await _ping_post(
        f"/v1/buyers/{buyer_id}/api-key/rotate",
        api_key,
        method="POST",
    )
    if not isinstance(result, dict) or result.get("error") or not result.get("api_key"):
        message = str(result.get("error") if isinstance(result, dict) else "rotation failed")[:300]
        return _redirect_wallet(key_status="error", key_message=message)

    new_api_key = str(result["api_key"])
    response = templates.TemplateResponse(
        request,
        "wallet.html",
        await _wallet_context(
            request, buyer_id=buyer_id, api_key=new_api_key, rotated_api_key=new_api_key
        ),
    )
    response.set_cookie(
        "buyer_api_key",
        new_api_key,
        httponly=True,
        samesite="lax",
        secure=_secure_cookies(),
    )
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    return response


if _local_demo_enabled():

    @app.post("/buyer-portal/wallet/deposit")
    async def deposit(
        request: Request,
        amount_cents: str = Form(...),
        external_reference: str = Form(default=""),
    ) -> RedirectResponse:
        buyer_id, api_key = _auth(request)
        if not buyer_id or not api_key:
            return _login_redirect()

        normalized_amount = amount_cents.strip()
        if not normalized_amount.isdecimal():
            return _redirect_wallet(
                deposit_status="error",
                deposit_message="Amount must be a positive integer in cents.",
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
    if not buyer_id or not api_key:
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
    buyer_id, api_key = _auth(request)
    if not buyer_id or not api_key:
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
    if not buyer_id or not api_key:
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
