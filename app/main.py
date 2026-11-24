"""Wepsol Tracker API. Run:  uvicorn app.main:app --reload   (from the tracker/ folder)."""
from __future__ import annotations

import base64
import logging
import os
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config, social, weeks

if config.LIVE:
    from . import google_clients as src
else:
    from . import sample as src

log = logging.getLogger("tracker")
app = FastAPI(title="Wepsol Tracker")

_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "")
if _PASSWORD:   # HTTP Basic auth on every page and API call; any username, the password must match
    @app.middleware("http")
    async def _basic_auth(request: Request, call_next):
        ok = False
        header = request.headers.get("authorization", "")
        if header.lower().startswith("basic "):
            try:
                ok = secrets.compare_digest(base64.b64decode(header[6:]).decode().partition(":")[2], _PASSWORD)
            except Exception:
                ok = False
        if not ok:
            return Response("Sign in required", status_code=401, headers={"WWW-Authenticate": 'Basic realm="Wepsol weekly tracker"'})
        return await call_next(request)
STATIC = Path(__file__).resolve().parent.parent / "static"

_cache: dict[tuple, tuple[float, object]] = {}


def cached(key: tuple, ttl: int, fn):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    val = fn()
    _cache[key] = (time.time(), val)
    return val


def _ttl(end: date) -> int:
    """Finished periods barely change (1h); a period that includes recent days refreshes every 10 min."""
    return 3600 if end < date.today() - timedelta(days=config.GSC_LAG_DAYS + 1) else 600


@app.get("/api/config")
def get_config():
    s, e = weeks.default_range()
    return {"mode": "live" if config.LIVE else "sample", "default_start": s.isoformat(), "default_end": e.isoformat(),
            "targets": config.TARGETS, "channels": config.CHANNEL_ORDER,
            "latest_date": (date.today() - timedelta(days=1)).isoformat(),
            "gsc_latest_date": (date.today() - timedelta(days=config.GSC_LAG_DAYS)).isoformat(),
            "social": config.SOCIAL_LIVE}


@app.get("/api/tracker")
def tracker(start: str | None = None, end: str | None = None):
    try:
        if start:
            s = date.fromisoformat(start)
            e = date.fromisoformat(end) if end else s + timedelta(days=6)
        else:
            s, e = weeks.default_range()
    except ValueError:
        raise HTTPException(400, "start/end must be YYYY-MM-DD")
    if e < s:
        raise HTTPException(400, "end is before start")

    periods = weeks.trend_periods(s, e, 3)          # oldest -> selected
    prev = periods[1]
    month_start = e.replace(day=1)

    try:
        with ThreadPoolExecutor(8) as ex:
            ga = {p: ex.submit(cached, ("ga4", *p), _ttl(p[1]), lambda p=p: src.ga4_period(*p)) for p in periods}
            kw_cur = ex.submit(cached, ("gsc", s, e), _ttl(e), lambda: src.gsc_buckets(s, e))
            kw_prev = ex.submit(cached, ("gsc", *prev), _ttl(prev[1]), lambda: src.gsc_buckets(*prev))
            st_cur = ex.submit(cached, ("gst", s, e), _ttl(e), lambda: src.gsc_totals(s, e))
            st_prev = ex.submit(cached, ("gst", *prev), _ttl(prev[1]), lambda: src.gsc_totals(*prev))
            mtd = ex.submit(cached, ("mtd", month_start, e), _ttl(e), lambda: src.ga4_total_users(month_start, e))
            ga = {p: f.result() for p, f in ga.items()}
            keywords = {"current": kw_cur.result(), "previous": kw_prev.result()}
            mtd = mtd.result()
            search = {"current": st_cur.result(), "previous": st_prev.result()}
    except Exception as exc:  # surface Google errors to the UI instead of a blank page
        log.exception("tracker failed")
        raise HTTPException(502, f"Data source error: {exc}")

    cur, prv = ga[periods[2]], ga[periods[1]]
    return {
        "mode": "live" if config.LIVE else "sample",
        "period": {"start": s.isoformat(), "end": e.isoformat(), "label": weeks.label(s, e)},
        "previous": {"start": prev[0].isoformat(), "end": prev[1].isoformat(), "label": weeks.label(*prev)},
        "traffic": {"current": cur, "previous": prv},
        "trend": [{"label": weeks.label(*p), "start": p[0].isoformat(), "end": p[1].isoformat(),
                   "total_users": ga[p]["overall"]["total_users"], "new_users": ga[p]["overall"]["new_users"],
                   "sessions": ga[p]["overall"]["sessions"]} for p in periods],
        "keywords": keywords,
        "search": search,
        "targets": config.TARGETS,
        "achieved": {"month_to_date_users": mtd, "month_start": month_start.isoformat()},
        "notes": {"gsc_latest_date": (date.today() - timedelta(days=config.GSC_LAG_DAYS)).isoformat()},
    }


def _parse_range(start: str | None, end: str | None) -> tuple[date, date]:
    try:
        if start:
            s = date.fromisoformat(start)
            e = date.fromisoformat(end) if end else s + timedelta(days=6)
        else:
            s, e = weeks.default_range()
    except ValueError:
        raise HTTPException(400, "start/end must be YYYY-MM-DD")
    if e < s:
        raise HTTPException(400, "end is before start")
    return s, e


@app.get("/api/social")
def social_api(start: str | None = None, end: str | None = None):
    """Facebook / Instagram (Meta Graph API) + LinkedIn (Apify). Separate from /api/tracker because LinkedIn takes ~20s."""
    if not config.SOCIAL_LIVE:
        return {"enabled": False}
    s, e = _parse_range(start, end)
    prev = weeks.shift(s, e, 1)
    try:
        data = cached(("social", s, e), 1800, lambda: social.social_report(s, e, prev))
    except Exception as exc:
        log.exception("social failed")
        raise HTTPException(502, f"Social data error: {exc}")
    return {"enabled": True, "period": {"start": s.isoformat(), "end": e.isoformat(), "label": weeks.label(s, e)},
            "previous": {"label": weeks.label(*prev)}, **data}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/", StaticFiles(directory=STATIC), name="static")
