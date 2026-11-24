"""Monthly search volume per keyword from Google Keyword Planner (India, English) via the Google Ads API.
Volumes change slowly, so they are cached on disk (data/volumes.json) and a keyword is only re-queried after 30 days.
The dashboard counts only keywords ranking 1-100 that HAVE volume, so this lookup defines "with volume" vs "no volume"."""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path

import requests

log = logging.getLogger("tracker.volumes")
from . import config
SEED = Path(__file__).resolve().parent.parent / "data" / "volumes.json"   # shipped with the code
CACHE = config.DATA_DIR / "volumes.json"
MAX_AGE = 30 * 86400
VERSIONS = ("v24", "v23", "v22")
INDIA, ENGLISH = "geoTargetConstants/2356", "languageConstants/1000"
_tok = {"v": "", "exp": 0.0}
_cache: dict | None = None


def _env(k: str) -> str:
    return os.getenv(k, "")


def available() -> bool:
    return all(_env(k) for k in ("GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET", "GOOGLE_ADS_REFRESH_TOKEN",
                                 "GOOGLE_ADS_DEVELOPER_TOKEN", "GOOGLE_ADS_LOGIN_CUSTOMER_ID"))


def _token() -> str:
    if _tok["v"] and time.time() < _tok["exp"] - 60:
        return _tok["v"]
    r = requests.post("https://oauth2.googleapis.com/token", timeout=30, data={
        "client_id": _env("GOOGLE_ADS_CLIENT_ID"), "client_secret": _env("GOOGLE_ADS_CLIENT_SECRET"),
        "refresh_token": _env("GOOGLE_ADS_REFRESH_TOKEN"), "grant_type": "refresh_token"})
    r.raise_for_status()
    _tok.update(v=r.json()["access_token"], exp=time.time() + int(r.json().get("expires_in", 3000)))
    return _tok["v"]


def _load() -> dict:
    global _cache
    if _cache is None:
        _cache = {}
        for p in (SEED, CACHE):
            try:
                _cache.update(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                pass
    return _cache


def _save() -> None:
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(_cache), encoding="utf-8")
    except OSError as e:   # read-only disk: keep working from memory
        log.warning("could not save volume cache: %s", e)


def _valid(k: str) -> bool:
    """Keyword Planner rejects very long / multi-word / symbol-heavy phrases."""
    return 0 < len(k) <= 80 and len(k.split()) <= 10 and not re.search(r"[^\w\s\-&'.+]", k, re.UNICODE)


def _call(batch: list[str]) -> dict[str, int]:
    cid = _env("GOOGLE_ADS_LOGIN_CUSTOMER_ID")
    H = {"Authorization": f"Bearer {_token()}", "developer-token": _env("GOOGLE_ADS_DEVELOPER_TOKEN"), "login-customer-id": cid}
    body = {"keywords": batch, "geoTargetConstants": [INDIA], "language": ENGLISH, "keywordPlanNetwork": "GOOGLE_SEARCH"}
    last = None
    for ver in VERSIONS:
        r = requests.post(f"https://googleads.googleapis.com/{ver}/customers/{cid}:generateKeywordHistoricalMetrics", headers=H, json=body, timeout=120)
        if r.status_code == 404:
            continue
        if r.status_code == 200:
            out = {}
            for res in r.json().get("results", []):
                v = (res.get("keywordMetrics") or {}).get("avgMonthlySearches")
                out[res["text"].lower()] = int(v) if v else 0
            return out
        last = r
        break
    if last is not None and last.status_code == 400 and len(batch) > 1:   # a bad keyword poisons the batch: split to isolate it
        mid = len(batch) // 2
        return {**_call(batch[:mid]), **_call(batch[mid:])}
    if last is not None and last.status_code == 400:
        return {}
    raise RuntimeError(f"Keyword Planner error: HTTP {last.status_code if last is not None else 404} {last.text[:200] if last is not None else ''}")


def get_volumes(keywords: list[str]) -> dict[str, int]:
    """keyword (lowercase) -> average monthly searches in India (0 = no volume / not found)."""
    cache, now = _load(), time.time()
    want = sorted({k.lower() for k in keywords})
    todo = [k for k in want if k not in cache or now - cache[k][1] > MAX_AGE]
    valid = [k for k in todo if _valid(k)]
    for k in todo:
        if k not in valid:
            cache[k] = [0, now]
    for i in range(0, len(valid), 700):
        chunk = valid[i:i + 700]
        got = _call(chunk)
        for k in chunk:
            cache[k] = [got.get(k, 0), now]
    if todo:
        _save()
    return {k: cache[k][0] for k in want}
