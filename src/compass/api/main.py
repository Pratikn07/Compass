"""Compass API.

  uv run uvicorn compass.api.main:app --port 8420

Every GET serves rows the nightly job persisted — what you see is what was
computed once, auditable. Writes are limited to the governance surface:
overrides (reason required), acknowledgments, and rule-change proposals that
start a 48-hour cooling-off clock enforced by both this layer and the DB.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ..store import make_client

COOLING_OFF_HOURS = 48

# Routes that stay open: health (no data leak; lets Railway probe) and docs.
_OPEN_PATHS = {"/v1/health", "/docs", "/openapi.json"}


def get_client():
    return make_client()


app = FastAPI(title="compass", version="0.1.0")

_cors_origins = ["http://localhost:3000"]
if os.environ.get("COMPASS_WEB_ORIGIN"):
    _cors_origins.append(os.environ["COMPASS_WEB_ORIGIN"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Compass-Key"],
)


@app.middleware("http")
async def require_api_key(request: Request, call_next):
    """Single-user bearer key. If COMPASS_API_KEY is unset (local dev), auth
    is disabled. CORS preflights pass through untouched."""
    expected = os.environ.get("COMPASS_API_KEY")
    if (
        expected
        and request.method != "OPTIONS"
        and request.url.path not in _OPEN_PATHS
        and request.headers.get("X-Compass-Key") != expected
    ):
        from fastapi.responses import JSONResponse

        return JSONResponse({"detail": "missing or invalid X-Compass-Key"}, status_code=401)
    return await call_next(request)


# ---------- read endpoints ----------

@app.get("/v1/health")
def health(client=Depends(get_client)) -> dict[str, Any]:
    runs = (
        client.table("compass_ingest_runs").select("started_at,source,records,status,error")
        .like("source", "nightly%").order("started_at", desc=True).limit(12).execute()
    ).data
    alerts = [r for r in runs if r["status"] == "alert"]
    spy = (
        client.table("compass_price_bars").select("d").eq("ticker", "SPY")
        .order("d", desc=True).limit(1).execute()
    ).data
    state = (
        client.table("compass_theme_state_daily").select("d")
        .order("d", desc=True).limit(1).execute()
    ).data
    return {
        "latest_price_date": spy[0]["d"] if spy else None,
        "latest_state_date": state[0]["d"] if state else None,
        "recent_alerts": alerts,
        "recent_runs": runs,
    }


@app.get("/v1/themes")
def themes(client=Depends(get_client)) -> list[dict[str, Any]]:
    meta = client.table("compass_themes").select("*").execute().data
    latest = (
        client.table("compass_theme_state_daily").select("d")
        .order("d", desc=True).limit(1).execute()
    ).data
    if not latest:
        return [{**m, "state": None} for m in meta]
    states = (
        client.table("compass_theme_state_daily").select("*")
        .eq("d", latest[0]["d"]).execute()
    ).data
    by_slug = {s["theme_slug"]: s for s in states}
    return [{**m, "state": by_slug.get(m["slug"])} for m in meta]


@app.get("/v1/themes/{slug}")
def theme_detail(slug: str, days: int = 400, client=Depends(get_client)) -> dict[str, Any]:
    meta = client.table("compass_themes").select("*").eq("slug", slug).execute().data
    if not meta:
        raise HTTPException(404, f"unknown theme {slug!r}")
    members = (
        client.table("compass_theme_memberships").select("*")
        .eq("theme_slug", slug).execute()
    ).data
    history = (
        client.table("compass_theme_state_daily").select("*").eq("theme_slug", slug)
        .order("d", desc=True).limit(days).execute()
    ).data
    return {**meta[0], "members": members, "state_history": list(reversed(history))}


@app.get("/v1/recommendations/today")
def recommendations_today(client=Depends(get_client)) -> dict[str, Any]:
    latest = (
        client.table("compass_recommendations").select("d")
        .order("d", desc=True).limit(1).execute()
    ).data
    if not latest:
        return {"d": None, "recommendations": []}
    rows = (
        client.table("compass_recommendations").select("*")
        .eq("d", latest[0]["d"]).order("instrument").execute()
    ).data
    return {"d": latest[0]["d"], "recommendations": rows}


@app.get("/v1/journal")
def journal(days: int = 90, client=Depends(get_client)) -> dict[str, Any]:
    since = (datetime.now(tz=UTC) - timedelta(days=days)).date().isoformat()
    recs = (
        client.table("compass_recommendations").select("*")
        .gte("d", since).order("d", desc=True).execute()
    ).data
    overrides = (
        client.table("compass_overrides").select("*")
        .gte("ts", since).order("ts", desc=True).execute()
    ).data
    return {"since": since, "recommendations": recs, "overrides": overrides}


@app.get("/v1/rule-changes")
def rule_changes(client=Depends(get_client)) -> list[dict[str, Any]]:
    rows = (
        client.table("compass_rule_changes").select("*")
        .order("proposed_at", desc=True).execute()
    ).data
    now = datetime.now(tz=UTC)
    for r in rows:
        effective = datetime.fromisoformat(r["effective_at"])
        r["active"] = bool(r["approved"]) and now >= effective
    return rows


# ---------- governance writes ----------

class OverrideIn(BaseModel):
    what: str = Field(min_length=1)
    reason: str = Field(min_length=3, description="required — the journal prices it later")


@app.post("/v1/overrides", status_code=201)
def create_override(body: OverrideIn, client=Depends(get_client)) -> dict[str, Any]:
    if not body.reason.strip():
        raise HTTPException(422, "override reason must not be blank")
    res = client.table("compass_overrides").insert(
        [{"what": body.what, "reason": body.reason.strip()}]
    ).execute()
    return res.data[0]


@app.post("/v1/recommendations/{rec_id}/ack")
def acknowledge(rec_id: int, client=Depends(get_client)) -> dict[str, Any]:
    rows = (
        client.table("compass_recommendations").select("id,acknowledged_at")
        .eq("id", rec_id).execute()
    ).data
    if not rows:
        raise HTTPException(404, f"no recommendation {rec_id}")
    if rows[0]["acknowledged_at"] is not None:
        return rows[0]
    res = client.table("compass_recommendations").update(
        {"acknowledged_at": datetime.now(tz=UTC).isoformat()}
    ).eq("id", rec_id).execute()
    return res.data[0]


class RuleChangeIn(BaseModel):
    change: dict[str, Any] = Field(description="the proposed rule change, as data")


@app.post("/v1/rule-changes", status_code=201)
def propose_rule_change(body: RuleChangeIn, client=Depends(get_client)) -> dict[str, Any]:
    """Starts the 48-hour cooling-off clock. `effective_at` is computed
    server-side — a client cannot shorten it (and the DB CHECK backstops)."""
    now = datetime.now(tz=UTC)
    res = client.table("compass_rule_changes").insert([{
        "proposed_at": now.isoformat(),
        "change": body.change,
        "effective_at": (now + timedelta(hours=COOLING_OFF_HOURS)).isoformat(),
        "approved": False,
    }]).execute()
    row = res.data[0]
    row["note"] = f"cooling off until {row['effective_at']} — nothing applies before then"
    return row
