"""GA4 Data API + Search Console fetchers (service-account auth, plain REST)."""
from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from urllib.parse import quote, urlsplit

import requests

from . import config

log = logging.getLogger("tracker.google")

GA4_URL = "https://analyticsdata.googleapis.com/v1beta/properties/{pid}:runReport"
GSC_URL = "https://www.googleapis.com/webmasters/v3/sites/{site}/searchAnalytics/query"
SCOPES = [
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/webmasters.readonly",
]

_token = {"value": "", "exp": 0.0}


def _access_token() -> str:
    if _token["value"] and time.time() < _token["exp"] - 60:
        return _token["value"]
    if config.GA4_REFRESH_TOKEN:
        r = requests.post("https://oauth2.googleapis.com/token", timeout=30, data={
            "client_id": config.GA4_CLIENT_ID, "client_secret": config.GA4_CLIENT_SECRET,
            "refresh_token": config.GA4_REFRESH_TOKEN, "grant_type": "refresh_token"})
        r.raise_for_status()
        _token.update(value=r.json()["access_token"], exp=time.time() + int(r.json().get("expires_in", 3000)))
        return _token["value"]
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_file(config.GOOGLE_CREDENTIALS, scopes=SCOPES)
    creds.refresh(Request())
    _token.update(value=creds.token, exp=creds.expiry.timestamp() if creds.expiry else time.time() + 3000)
    return _token["value"]


def _headers() -> dict:
    return {"Authorization": f"Bearer {_access_token()}", "Content-Type": "application/json"}


# --------------------------------------------------------------------------- GA4
def _flt(field: str, value: str, match: str = "EXACT") -> dict:
    return {"filter": {"fieldName": field, "stringFilter": {"matchType": match, "value": value, "caseSensitive": False}}}


def _ga4_filter(india_only: bool) -> dict | None:
    """Rules shared by every GA4 number: drop career/job landing pages, drop configured bot countries, optionally India only."""
    ex: list[dict] = []
    if india_only:
        ex.append(_flt("country", config.INDIA_COUNTRY))
    # Job/career pages are excluded from the India column (dashboard + sheet convention); the Overall column mirrors the
    # Looker table, which keeps them and only applies the Bot Traffic filter.
    if config.EXCLUDE_JOB_PAGES and india_only:
        ex += [{"notExpression": _flt("landingPage", t, "CONTAINS")} for t in config.JOB_PAGE_TERMS]
    if not india_only:   # bot filter only matters for the all-countries column
        ex += [{"notExpression": _flt("country", c)} for c in config.EXCLUDE_COUNTRIES]
        ex += [{"notExpression": _flt("city", c)} for c in config.EXCLUDE_CITIES]
    return None if not ex else ex[0] if len(ex) == 1 else {"andGroup": {"expressions": ex}}


def _ga4(start: date, end: date, dims: list[str], metrics: list[str], india_only: bool = False) -> list[dict]:
    body: dict = {
        "dateRanges": [{"startDate": start.isoformat(), "endDate": end.isoformat()}],
        "dimensions": [{"name": d} for d in dims],
        "metrics": [{"name": m} for m in metrics],
        "limit": 1000,
    }
    flt = _ga4_filter(india_only)
    if flt:
        body["dimensionFilter"] = flt
    r = requests.post(GA4_URL.format(pid=config.GA4_PROPERTY_ID), headers=_headers(), json=body, timeout=60)
    r.raise_for_status()
    out = []
    for row in r.json().get("rows", []):
        item = {d: v.get("value", "") for d, v in zip(dims, row.get("dimensionValues", []))}
        item.update({m: float(v.get("value") or 0) for m, v in zip(metrics, row.get("metricValues", []))})
        out.append(item)
    return out


METRICS = ["totalUsers", "newUsers", "sessions", "engagementRate", "averageSessionDuration"]


def _summary(start: date, end: date, india: bool) -> dict:
    rows = _ga4(start, end, [], METRICS, india)
    r = rows[0] if rows else {}
    return {
        "total_users": int(r.get("totalUsers", 0)),
        "new_users": int(r.get("newUsers", 0)),
        "sessions": int(r.get("sessions", 0)),
        "engagement_rate": r.get("engagementRate", 0.0),          # 0..1
        "avg_session_duration_sec": r.get("averageSessionDuration", 0.0),
    }


def _channels(start: date, end: date, india: bool) -> dict:
    out = {c: 0 for c in config.CHANNEL_ORDER}
    for r in _ga4(start, end, ["sessionDefaultChannelGroup"], ["totalUsers"], india):
        row = config.CHANNEL_MAP.get(r["sessionDefaultChannelGroup"])
        if row:
            out[row] += int(r["totalUsers"])
    return out


def ga4_period(start: date, end: date) -> dict:
    """Overall + India summary and channel split for one period (4 GA4 calls, run in parallel).
    Users/engagement are unique/ratio metrics, so each period is queried directly, never summed from days."""
    with ThreadPoolExecutor(4) as ex:
        f = {
            "overall": ex.submit(_summary, start, end, False),
            "india": ex.submit(_summary, start, end, True),
            "channels_overall": ex.submit(_channels, start, end, False),
            "channels_india": ex.submit(_channels, start, end, True),
        }
        return {k: v.result() for k, v in f.items()}


def ga4_total_users(start: date, end: date) -> int:
    return _summary(start, end, False)["total_users"]


# --------------------------------------------------------------------------- blogs
_blog_cache = {"urls": set(), "ts": 0.0}


def _norm(url: str) -> str:
    p = urlsplit(url)
    return (p.netloc.lower().removeprefix("www.") + p.path.rstrip("/")).lower()


def blog_urls() -> set[str]:
    """Normalised URLs of every WordPress post (blogs have no shared path, so we use the post list)."""
    if _blog_cache["urls"] and time.time() - _blog_cache["ts"] < 6 * 3600:
        return _blog_cache["urls"]
    urls: set[str] = set()
    for page in range(1, 21):
        r = requests.get(f"{config.WP_BASE}/wp-json/wp/v2/posts", timeout=20,
                         params={"per_page": 100, "page": page, "_fields": "link"})
        if r.status_code != 200 or not r.json():
            break
        urls.update(_norm(p["link"]) for p in r.json())
        if len(r.json()) < 100:
            break
    if urls:
        _blog_cache.update(urls=urls, ts=time.time())
    return urls or _blog_cache["urls"]


# --------------------------------------------------------------------------- GSC
def _gsc_rows(start: date, end: date) -> list[dict]:
    url = GSC_URL.format(site=quote(config.GSC_SITE_URL, safe=""))
    rows, offset = [], 0
    while offset < 100_000:
        body = {"startDate": start.isoformat(), "endDate": end.isoformat(), "dimensions": ["query", "page"],
                "type": "web", "rowLimit": 25000, "startRow": offset, "dataState": "all"}
        if config.GSC_COUNTRY:
            body["dimensionFilterGroups"] = [{"filters": [{"dimension": "country", "operator": "equals",
                                                            "expression": config.GSC_COUNTRY}]}]
        r = requests.post(url, headers=_headers(), json=body, timeout=90)
        r.raise_for_status()
        batch = r.json().get("rows", [])
        rows.extend(batch)
        if len(batch) < 25000:
            break
        offset += 25000
    return rows


def _bucket(pos: float) -> str | None:
    p = round(pos)
    for name, hi in (("1-5", 5), ("6-10", 10), ("11-20", 20), ("21-50", 50), ("51-100", 100)):
        if 1 <= p <= hi:
            return name
    return None


def _branded(q: str) -> bool:
    return re.search(config.BRAND_REGEX, q.lower()) is not None


def gsc_buckets(start: date, end: date) -> dict:
    """Keywords ranking 1-100 per position bucket for: every page ('all'), blogs removed ('no_blogs'), and each product line.
    A keyword's position = impression-weighted average over the pages it ranked on (same as the dashboard)."""
    from . import products as prod, volumes
    blogs = blog_urls()
    names = ["all", "no_blogs", *prod.PRODUCTS]
    stores: dict[str, dict[str, list[float]]] = {n: {} for n in names}   # group -> query -> [impressions, position*impressions]
    for row in _gsc_rows(start, end):
        q, page = row["keys"]
        imp, pos = row.get("impressions", 0), row.get("position", 0)
        is_blog = _norm(page) in blogs
        member = ["all"]
        if not is_blog:
            member.append("no_blogs")
        member += [k for k, v in prod.PRODUCTS.items() if prod.matches(page, v, is_blog)]
        for n in member:
            a = stores[n].setdefault(q, [0.0, 0.0])
            a[0] += imp
            a[1] += pos * imp

    # Keyword Planner volume decides "with volume" (counted) vs "no volume", exactly like the dashboard
    vols: dict[str, int] = {}
    if volumes.available():
        ranked = {q for q, (imp, w) in stores["all"].items() if imp >= config.MIN_IMPRESSIONS and imp > 0 and _bucket(w / imp)}
        vols = volumes.get_volumes(list(ranked))

    def count(store: dict) -> dict:
        out = {b: 0 for b in config.KEYWORD_BUCKETS}
        branded = no_vol = 0
        wsum = isum = 0.0
        for q, (imp, weighted) in store.items():
            if imp < config.MIN_IMPRESSIONS or imp <= 0:
                continue
            b = _bucket(weighted / imp)
            if not b:
                continue
            if vols and not vols.get(q.lower(), 0):
                no_vol += 1
                continue
            out[b] += 1
            branded += _branded(q)
            wsum += weighted; isum += imp
        out["total"] = sum(out.values())                      # keywords WITH volume (dashboard's counted set)
        out["no_volume"] = no_vol
        out["total_ranked"] = out["total"] + no_vol           # every keyword ranking 1-100
        out["branded"], out["non_branded"] = branded, out["total"] - branded
        out["avg_position"] = round(wsum / isum, 1) if isum else 0.0
        return out

    res = {n: count(stores[n]) for n in names}
    return {"all": res["all"], "no_blogs": res["no_blogs"], "volume_applied": bool(vols),
            "products": {k: {"label": v["label"], **res[k]} for k, v in prod.PRODUCTS.items()}}


def gsc_totals(start: date, end: date) -> dict:
    body = {"startDate": start.isoformat(), "endDate": end.isoformat(), "dimensions": [], "type": "web", "dataState": "all"}
    if config.GSC_COUNTRY:
        body["dimensionFilterGroups"] = [{"filters": [{"dimension": "country", "operator": "equals", "expression": config.GSC_COUNTRY}]}]
    r = requests.post(GSC_URL.format(site=quote(config.GSC_SITE_URL, safe="")), headers=_headers(), json=body, timeout=60)
    r.raise_for_status()
    row = (r.json().get("rows") or [{}])[0]
    return {"clicks": int(row.get("clicks", 0)), "impressions": int(row.get("impressions", 0)),
            "ctr": row.get("ctr", 0.0), "position": row.get("position", 0.0)}
