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
import hashlib
import threading
_DATA = Path(__file__).resolve().parent.parent / "data"
LOCAL_SEED = _DATA / "volumes.json"           # plain cache from earlier local runs (not committed)
HASH_SEED = _DATA / "volumes_seed.json"       # committed: sha1(keyword)[:16] -> volume, so no readable keyword list is published
CACHE = config.DATA_DIR / "volumes.json"
_lock = threading.Lock()                      # one lookup at a time: parallel requests must not repeat the same Google calls
_seed: dict | None = None
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
        for p in (LOCAL_SEED, CACHE):
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


def _hkey(k: str) -> str:
    return hashlib.sha1(k.lower().encode("utf-8")).hexdigest()[:16]


def _load_seed() -> dict:
    global _seed
    if _seed is None:
        try:
            _seed = json.loads(HASH_SEED.read_text(encoding="utf-8"))
        except Exception:
            _seed = {}
    return _seed


def get_volumes_ex(keywords: list[str]) -> tuple[dict[str, int], str | None]:
    """(keyword -> monthly searches in India, warning). Order of preference per keyword: fresh cache, shipped seed, Google
    (Keyword Planner). If Google refuses (quota, outage) the keywords it could not check are left out - the caller then treats
    them as 'no volume' - and a warning is returned instead of failing the whole report."""
    with _lock:
        cache, seed, now = _load(), _load_seed(), time.time()
        want = sorted({k.lower() for k in keywords})
        out: dict[str, int] = {}
        todo: list[str] = []
        for k in want:
            hit = cache.get(k)
            if hit and now - hit[1] <= MAX_AGE:
                out[k] = hit[0]
            elif _hkey(k) in seed:
                out[k] = seed[_hkey(k)]
            else:
                todo.append(k)
                if hit:                      # stale value: better than nothing if Google refuses
                    out[k] = hit[0]
        valid = [k for k in todo if _valid(k)]
        for k in todo:
            if k not in valid:
                cache[k] = [0, now]
                out[k] = 0
        warning = None
        for i in range(0, len(valid), 700):
            chunk = valid[i:i + 700]
            try:
                got = _call(chunk)
            except Exception as e:
                left = len(valid) - i
                log.warning("Keyword Planner lookup failed (%d keywords unchecked): %s", left, e)
                warning = f"Google Keyword Planner could not be reached right now ({str(e)[:90]}), so {left} new keyword(s) are counted as 'no volume'. Try again later."
                break
            for k in chunk:
                cache[k] = [got.get(k, 0), now]
                out[k] = cache[k][0]
        if todo:
            _save()
        return out, warning


def get_volumes(keywords: list[str]) -> dict[str, int]:
    return get_volumes_ex(keywords)[0]
