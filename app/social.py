"""Facebook + Instagram (Meta Graph API) and LinkedIn (Apify, public data) for any date range.

LinkedIn's impressions / clicks / page views / unique visitors are admin-only analytics that no public scraper can see,
so they are reported as unavailable rather than invented. Followers, posts published and post engagement are real.
"""
from __future__ import annotations

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from urllib.parse import quote

from . import config, linkedin_posts

log = logging.getLogger("tracker.social")
GRAPH = f"https://graph.facebook.com/{config.META_GRAPH_VERSION}"
IST = timezone(timedelta(hours=5, minutes=30))
SNAP = config.DATA_DIR / "followers.json"


def _day(iso_ts: str) -> date:
    return datetime.fromisoformat(iso_ts.replace("Z", "+00:00").replace("+0000", "+00:00")).astimezone(IST).date()


def _get(path: str, token: str, **params) -> dict:
    r = requests.get(f"{GRAPH}/{path}", params={**params, "access_token": token}, timeout=40)
    j = r.json()
    if "error" in j:
        raise RuntimeError(j["error"].get("message", "Meta API error"))
    return j


# ------------------------------------------------------------------ follower snapshots (for LinkedIn gained)
def _record_followers(platform: str, count: int | None) -> None:
    if count is None:
        return
    try:
        data = json.loads(SNAP.read_text()) if SNAP.exists() else {}
        data.setdefault(platform, {})[date.today().isoformat()] = count
        SNAP.parent.mkdir(exist_ok=True)
        SNAP.write_text(json.dumps(data))
    except Exception:
        log.exception("snapshot write failed")


def _followers_gained_from_snapshots(platform: str, start: date, end: date) -> int | None:
    try:
        snaps = {date.fromisoformat(k): v for k, v in json.loads(SNAP.read_text()).get(platform, {}).items()}
    except Exception:
        return None
    before = [d for d in snaps if d <= start]
    after = [d for d in snaps if d >= end]
    if not before or not after:
        return None
    return snaps[min(after)] - snaps[max(before)]


# ------------------------------------------------------------------ Facebook
_ptok = {"v": "", "ts": 0.0}


def _page_token() -> str:
    if _ptok["v"] and time.time() - _ptok["ts"] < 3000:
        return _ptok["v"]
    j = _get(config.META_PAGE_ID, config.META_ACCESS_TOKEN, fields="access_token")
    _ptok.update(v=j.get("access_token", config.META_ACCESS_TOKEN), ts=time.time())
    return _ptok["v"]


def _fb_metric(metric: str, start: date, end: date, tok: str):
    """One metric per call. Meta intermittently answers with a generic error or an EMPTY result; both are retried
    (up to 4 tries) so a flaky response is never shown as a real 0. Returns None if it never succeeds."""
    for attempt in range(4):
        try:
            j = _get(f"{config.META_PAGE_ID}/insights", tok, metric=metric, period="day",
                     since=start.isoformat(), until=(end + timedelta(days=1)).isoformat())
            vals = (j.get("data") or [{}])[0].get("values") or []
            if vals:
                return sum(v.get("value") or 0 for v in vals if isinstance(v.get("value"), (int, float)))
            log.warning("fb metric %s attempt %d: empty result", metric, attempt + 1)
        except Exception as e:
            log.warning("fb metric %s attempt %d: %s", metric, attempt + 1, e)
        time.sleep(1.5)
    return None


FB_METRICS = ("page_media_view", "page_post_engagements", "page_daily_follows_unique", "page_views_total")


def _fb_insights(start: date, end: date, tok: str) -> dict:
    return {m: _fb_metric(m, start, end, tok) for m in FB_METRICS}   # serial: parallel calls intermittently return empty data


def _fb_posts(start: date, end: date, tok: str) -> list[dict]:
    out, url = [], f"{GRAPH}/{config.META_PAGE_ID}/posts"
    params = {"fields": "message,created_time,permalink_url,full_picture,reactions.summary(true).limit(0),comments.summary(true).limit(0),shares",
              "since": (start - timedelta(days=1)).isoformat(), "until": (end + timedelta(days=2)).isoformat(), "limit": 100, "access_token": tok}
    while url:
        j = requests.get(url, params=params, timeout=40).json()
        if "error" in j:
            raise RuntimeError(j["error"].get("message", "Facebook posts error"))
        for p in j.get("data", []):
            d = _day(p["created_time"])
            if start <= d <= end:
                likes = p.get("reactions", {}).get("summary", {}).get("total_count", 0)
                com = p.get("comments", {}).get("summary", {}).get("total_count", 0)
                sh = (p.get("shares") or {}).get("count", 0)
                out.append({"id": p["id"], "platform": "Facebook", "date": d.isoformat(), "text": (p.get("message") or "")[:140], "url": p.get("permalink_url"),
                            "image": p.get("full_picture"), "likes": likes, "comments": com, "shares": sh, "engagement": likes + com + sh})
        url, params = (j.get("paging") or {}).get("next"), {}
    return out


def _fb_post_metric(pid: str, metric: str, tok: str):
    """Lifetime value of one post metric (reach etc.). Retried like the page metrics; None if it never succeeds."""
    for attempt in range(3):
        try:
            j = _get(f"{pid}/insights", tok, metric=metric)
            vals = (j.get("data") or [{}])[0].get("values") or []
            if vals and isinstance(vals[0].get("value"), (int, float)):
                return vals[0]["value"]
        except Exception as e:
            log.warning("fb post %s %s attempt %d: %s", pid, metric, attempt + 1, e)
        time.sleep(1.2)
    return None


def _fb_followers_at(end: date, tok: str):
    """Total page followers at the end of `end` (page_follows is a running total, one value per day)."""
    for attempt in range(3):
        try:
            j = _get(f"{config.META_PAGE_ID}/insights", tok, metric="page_follows", period="day",
                     since=end.isoformat(), until=(end + timedelta(days=1)).isoformat())
            vals = (j.get("data") or [{}])[0].get("values") or []
            if vals:
                return vals[-1]["value"]
        except Exception as e:
            log.warning("fb followers_at attempt %d: %s", attempt + 1, e)
        time.sleep(1.2)
    return None


def facebook(start: date, end: date) -> dict:
    tok = _page_token()
    followers_now = _get(config.META_PAGE_ID, tok, fields="followers_count").get("followers_count")
    _record_followers("facebook", followers_now)
    posts = _fb_posts(start, end, tok)
    for p in posts:                      # reach / views of the posts published in this period (not the whole page)
        p["reach"] = _fb_post_metric(p["id"], "post_total_media_view_unique", tok)
        p["views"] = _fb_post_metric(p["id"], "post_media_view", tok)
    ins = _fb_insights(start, end, tok)  # page-level activity in the period (followers gained, page views)
    reach = sum(p["reach"] or 0 for p in posts)
    eng = sum(p["engagement"] for p in posts)
    return {"followers": _fb_followers_at(end, tok) or followers_now, "insights": ins, "posts": posts,
            "n": {"views": sum(p["views"] or 0 for p in posts), "engagement": eng,
                  "gained": ins.get("page_daily_follows_unique"), "posts": len(posts), "reach": reach}}


# ------------------------------------------------------------------ Instagram
def _ig_total(metric: str, start: date, end: date) -> int:
    total, a = 0, start
    while a <= end:                     # insights window is limited to 30 days per call
        b = min(end, a + timedelta(days=29))
        j = _get(f"{config.IG_USER_ID}/insights", config.META_ACCESS_TOKEN, metric=metric, metric_type="total_value", period="day",
                 since=a.isoformat(), until=(b + timedelta(days=1)).isoformat())
        total += (j["data"][0].get("total_value") or {}).get("value", 0)
        a = b + timedelta(days=1)
    return total


def _ig_gained(start: date, end: date) -> int:
    total, a = 0, start
    while a <= end:
        b = min(end, a + timedelta(days=29))
        j = _get(f"{config.IG_USER_ID}/insights", config.META_ACCESS_TOKEN, metric="follower_count", period="day",
                 since=a.isoformat(), until=(b + timedelta(days=1)).isoformat())
        total += sum(v.get("value", 0) for v in j["data"][0]["values"])
        a = b + timedelta(days=1)
    return total


def _ig_media(start: date, end: date) -> list[dict]:
    out, url = [], f"{GRAPH}/{config.IG_USER_ID}/media"
    params = {"fields": "caption,timestamp,media_type,permalink,like_count,comments_count,thumbnail_url,media_url", "limit": 50,
              "access_token": config.META_ACCESS_TOKEN}
    while url:
        j = requests.get(url, params=params, timeout=40).json()
        if "error" in j:
            raise RuntimeError(j["error"].get("message", "Instagram media error"))
        stop = False
        for m in j.get("data", []):
            d = _day(m["timestamp"])
            if d < start:
                stop = True
                continue
            if d <= end:
                likes, com = m.get("like_count", 0), m.get("comments_count", 0)
                out.append({"id": m["id"], "platform": "Instagram", "date": d.isoformat(), "text": (m.get("caption") or "")[:140], "url": m.get("permalink"),
                            "image": m.get("thumbnail_url") or m.get("media_url"), "likes": likes, "comments": com, "shares": 0,
                            "engagement": likes + com})
        url, params = (None if stop else (j.get("paging") or {}).get("next")), {}
    return out


def _ig_media_insights(mid: str) -> dict:
    """Lifetime reach / views / saves / shares of one post."""
    for attempt in range(3):
        try:
            j = _get(f"{mid}/insights", config.META_ACCESS_TOKEN, metric="reach,views,saved,shares")
            return {d["name"]: (d.get("values") or [{}])[0].get("value", 0) for d in j.get("data", [])}
        except Exception as e:
            log.warning("ig media %s attempt %d: %s", mid, attempt + 1, e)
            time.sleep(1.2)
    return {}


def _ig_followers_at(end: date, now_count):
    """Followers at the end of `end` = followers now minus net new followers since (follower_count is a daily net change)."""
    today = date.today()
    if now_count is None or end >= today:
        return now_count
    if (today - end).days > 29:
        return None
    try:
        j = _get(f"{config.IG_USER_ID}/insights", config.META_ACCESS_TOKEN, metric="follower_count", period="day",
                 since=(end + timedelta(days=1)).isoformat(), until=(today + timedelta(days=1)).isoformat())
        return now_count - sum(v.get("value", 0) for v in j["data"][0]["values"])
    except Exception:
        log.exception("ig followers_at failed")
        return None


def instagram(start: date, end: date) -> dict:
    now_count = _get(config.IG_USER_ID, config.META_ACCESS_TOKEN, fields="followers_count").get("followers_count")
    _record_followers("instagram", now_count)
    with ThreadPoolExecutor(8) as ex:
        m = {k: ex.submit(_ig_total, k, start, end) for k in ("profile_views", "website_clicks")}
        gained, media = ex.submit(_ig_gained, start, end), ex.submit(_ig_media, start, end)
        posts = media.result()
        ins_f = [ex.submit(_ig_media_insights, p["id"]) for p in posts]
        for p, f in zip(posts, ins_f):          # reach / engagement of the posts published in this period (not the whole account)
            mi = f.result()
            p["reach"], p["views"] = mi.get("reach"), mi.get("views")
            p["shares"], p["saved"] = mi.get("shares", 0), mi.get("saved", 0)
            p["engagement"] = p["likes"] + p["comments"] + p["shares"] + p["saved"]
        ins, g_ = {k: f.result() for k, f in m.items()}, gained.result()
    return {"followers": _ig_followers_at(end, now_count), "insights": ins, "gained": g_, "posts": posts,
            "n": {"views": sum(p["views"] or 0 for p in posts), "engagement": sum(p["engagement"] for p in posts), "gained": g_,
                  "posts": len(posts), "reach": sum(p["reach"] or 0 for p in posts)}}


# ------------------------------------------------------------------ LinkedIn admin analytics (reporting Google Sheet)
SHEET_ID = os.getenv("REPORTS_SOURCE_SPREADSHEET_ID", "14U43fz5NBSiXO2B7yAVp6Zi-KNzDaajRVxql6zueUwk")
SHEET_TAB = os.getenv("LINKEDIN_SHEET_TAB", "LinkedIn Analytics")
# sheet column (lower-case, trimmed) -> metric key
LI_COLS = {"impressions (organic)": "impressions", "clicks (organic)": "clicks", "total followers gained": "gained",
           "total page views (total)": "page_views", "total unique visitors (total)": "visitors", "impressions (total)": "impressions_total", "total page followers": "followers"}
_DATE_FORMATS = ("%m/%d/%Y", "%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y", "%b %d, %Y")
_sheet = {"ts": 0.0, "rows": None}


def _num(v):
    try:
        return float(str(v).replace(",", "").replace("%", "").strip())
    except ValueError:
        return None


def _rows_from_values(values: list[list]) -> list[dict]:
    if not values:
        raise RuntimeError("the LinkedIn Analytics data is empty")
    head = [str(h).strip().lower() for h in values[0]]
    return [{head[i]: (row[i] if i < len(row) else "") for i in range(len(head))} for row in values[1:]]


def _rows_from_api() -> list[dict]:
    """Live read of the Google Sheet tab. Uses a service account if GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE is set (the sheet must be
    shared with its e-mail as Viewer), otherwise the OAuth token in GOOGLE_SHEETS_TOKEN_JSON."""
    sa_file = os.getenv("GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE", "")
    sa_json = os.getenv("GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON", "")   # the key file's text, for hosts without files (Vercel)
    if sa_file or sa_json:
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account
        scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
        creds = (service_account.Credentials.from_service_account_info(json.loads(sa_json), scopes=scopes) if sa_json
                 else service_account.Credentials.from_service_account_file(sa_file, scopes=scopes))
        creds.refresh(Request())
        token = creds.token
    else:
        raw = os.getenv("GOOGLE_SHEETS_TOKEN_JSON", "")
        if not raw:
            raise RuntimeError("no Google Sheets credentials configured")
        tj = json.loads(raw)
        t = requests.post("https://oauth2.googleapis.com/token", timeout=30, data={
            "client_id": tj["client_id"], "client_secret": tj["client_secret"],
            "refresh_token": tj["refresh_token"], "grant_type": "refresh_token"})
        t.raise_for_status()
        token = t.json()["access_token"]
    r = requests.get(f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/{quote(SHEET_TAB)}",
                     headers={"Authorization": f"Bearer {token}"}, timeout=60)
    if r.status_code != 200:
        msg = (r.json().get("error") or {}).get("message", r.text[:200]) if r.headers.get("content-type", "").startswith("application/json") else r.text[:200]
        raise RuntimeError(msg)
    return _rows_from_values(r.json().get("values", []))


def _rows_from_csv() -> list[dict] | None:
    """Fallback: a CSV export of the LinkedIn Analytics tab (File > Download > CSV), saved as data/linkedin_analytics.csv."""
    import csv
    import io
    text = os.getenv("LINKEDIN_CSV_DATA", "")      # CSV text pasted into a hosting variable (Vercel)
    if text.strip():
        return _rows_from_values(list(csv.reader(io.StringIO(text.lstrip("\ufeff")))))
    path = Path(os.getenv("LINKEDIN_CSV") or (Path(__file__).resolve().parent.parent / "data" / "linkedin_analytics.csv"))
    if not path.exists():
        return None
    with path.open(encoding="utf-8-sig", newline="") as f:
        return _rows_from_values(list(csv.reader(f)))


def _sheet_rows() -> list[dict]:
    if _sheet["rows"] is not None and time.time() - _sheet["ts"] < 600:
        return _sheet["rows"]
    try:
        rows = _rows_from_api()
    except Exception as api_error:
        rows = _rows_from_csv()
        if rows is None:
            raise api_error
        log.info("LinkedIn analytics read from the local CSV export (sheet API: %s)", str(api_error)[:80])
    _sheet.update(ts=time.time(), rows=rows)
    return rows


def _sheet_date(raw):
    s_ = str(raw or "").strip()
    for f in _DATE_FORMATS:
        try:
            return datetime.strptime(s_, f).date()
        except ValueError:
            continue
    return None


def linkedin_admin(start: date, end: date) -> dict | None:
    """Impressions / clicks / page views / unique visitors / followers gained for [start, end], summed over the sheet's daily rows
    (the same way the original dashboard does). None when the sheet has no rows for that period yet."""
    sums = {k: 0.0 for k in LI_COLS.values() if k != "followers"}
    seen, followers, last, engagement = False, None, None, 0.0
    for row in _sheet_rows():
        d = _sheet_date(row.get("date"))
        if d is None:
            continue
        if d <= end and (last is None or d > last):
            f = _num(row.get("total page followers"))
            if f is not None:
                followers, last = int(f), d
        if start <= d <= end:
            seen = True
            # "Engagement (organic)" as in the Looker table = organic clicks + reactions + comments + reposts
            engagement += sum((_num(row.get(c)) or 0) for c in ("clicks (organic)", "reactions (organic)", "comments (organic)", "reposts (organic)"))
            for col, key in LI_COLS.items():
                if key == "followers":
                    continue
                v = _num(row.get(col))
                if v is not None:
                    sums[key] += v
    if not seen:
        return None
    return {**{k: int(v) for k, v in sums.items()}, "engagement": int(engagement), "followers": followers}


# ------------------------------------------------------------------ LinkedIn (Apify)
_li_cache: dict[tuple, tuple[float, object]] = {}


def _apify(actor: str, payload: dict):
    last = "no Apify token configured"
    for tok in config.APIFY_TOKENS:
        r = requests.post(f"https://api.apify.com/v2/acts/{actor.replace('/', '~')}/run-sync-get-dataset-items",
                          params={"token": tok, "timeout": 150}, json=payload, timeout=180)
        if r.status_code in (200, 201):
            return r.json()
        last = f"HTTP {r.status_code}"
    raise RuntimeError(f"Apify failed ({last})")


def _li_cached(key: tuple, fn):
    hit = _li_cache.get(key)
    if hit and time.time() - hit[0] < 6 * 3600:
        return hit[1]
    val = fn()
    _li_cache[key] = (time.time(), val)
    return val


def linkedin(start: date, end: date) -> dict:
    lookback = (date.today() - start).days
    limit = "week" if lookback <= 7 else "month" if lookback <= 30 else "3months" if lookback <= 90 else "6months" if lookback <= 180 else "year"
    company = _li_cached(("company",), lambda: _apify("harvestapi/linkedin-company", {"companies": [config.LINKEDIN_URL]}))
    followers = company[0].get("followerCount") if company else None
    _record_followers("linkedin", followers)
    raw = _li_cached(("posts", limit), lambda: _apify("harvestapi/linkedin-company-posts",
                     {"targetUrls": [config.LINKEDIN_URL], "maxPosts": 200, "postedLimit": limit}))
    posts = []
    for p in raw or []:
        ts = (p.get("postedAt") or {}).get("date")
        if not ts:
            continue
        d = _day(ts)
        if start <= d <= end:
            e = p.get("engagement") or {}
            likes, com, sh = e.get("likes", 0), e.get("comments", 0), e.get("shares", 0)
            posts.append({"platform": "LinkedIn", "date": d.isoformat(), "text": (p.get("content") or "")[:220], "url": p.get("linkedinUrl"),
                          "image": linkedin_posts.cover_of(p), "likes": likes, "comments": com, "shares": sh, "engagement": likes + com + sh,
                          "product": linkedin_posts.product_of(p.get("content") or ""), "ptype": linkedin_posts.type_of(p)})
    admin, admin_error = None, None
    try:
        admin = linkedin_admin(start, end)
        if admin is None:
            admin_error = "the LinkedIn Analytics sheet has no rows for this period yet"
    except Exception as e:
        detail = str(e).split(". Enable it by visiting")[0][:220]
        admin_error = ("LinkedIn admin numbers (impressions, clicks, page views, visitors) are not connected on this site yet. "
                       "Connect the LinkedIn Analytics sheet or paste the LinkedIn export into LINKEDIN_CSV_DATA - see the README."
                       if "Sheets API" in detail or "no credentials" in detail or "not configured" in detail else detail)
        log.warning("linkedin admin analytics unavailable: %s", e)
    gained = admin["gained"] if admin else _followers_gained_from_snapshots("linkedin", start, end)
    return {"followers": (admin or {}).get("followers") or followers, "posts": posts, "admin": admin, "admin_error": admin_error,
            "n": {"views": (admin or {}).get("impressions"), "reach": None, "engagement": sum(p["engagement"] for p in posts),
                  "gained": gained, "posts": len(posts)}}


# ------------------------------------------------------------------ assemble
def _pair(cur, prev):
    return {"cur": cur, "prev": prev}


def _safe(fn, *a):
    try:
        return fn(*a), None
    except Exception as e:  # one failing platform must not blank the section
        log.exception("%s failed", fn.__name__)
        return None, str(e)[:200]


def social_report(start: date, end: date, prev: tuple[date, date]) -> dict:
    ps, pe = prev
    with ThreadPoolExecutor(6) as ex:
        fb_both = ex.submit(lambda: (_safe(facebook, start, end), _safe(facebook, ps, pe)))   # Meta page API: keep serial
        jobs = {("ig", "cur"): ex.submit(_safe, instagram, start, end), ("ig", "prev"): ex.submit(_safe, instagram, ps, pe),
                ("li", "cur"): ex.submit(_safe, linkedin, start, end), ("li", "prev"): ex.submit(_safe, linkedin, ps, pe)}
        r = {k: f.result() for k, f in jobs.items()}
        r[("fb", "cur")], r[("fb", "prev")] = fb_both.result()

    def g(p, w):  # data of platform p for window w
        return r[(p, w)][0]

    out: dict = {"platforms": {}, "errors": {}}
    # Facebook / Instagram: Reach and Engagement are summed over the POSTS PUBLISHED in the period (like the sheet);
    # followers are as at the end of the period.
    nv = lambda d, k: d["n"][k] if d else None
    fc, fp = g("fb", "cur"), g("fb", "prev")
    if fc:
        i, ip = fc["insights"], (fp or {}).get("insights", {})
        out["platforms"]["facebook"] = {"followers": fc["followers"], "followers_asof": True, "metrics": [
            ["Total posts", _pair(nv(fc, "posts"), nv(fp, "posts"))],
            ["Total reach (posts)", _pair(nv(fc, "reach"), nv(fp, "reach"))],
            ["Total impressions (posts)", _pair(nv(fc, "views"), nv(fp, "views"))],
            ["Engagement (posts)", _pair(nv(fc, "engagement"), nv(fp, "engagement"))],
            ["Followers gained", _pair(i.get("page_daily_follows_unique"), ip.get("page_daily_follows_unique"))],
            ["Page views", _pair(i.get("page_views_total"), ip.get("page_views_total"))]]}
    else:
        out["errors"]["facebook"] = r[("fb", "cur")][1]
    ic, ipv = g("ig", "cur"), g("ig", "prev")
    if ic:
        i, ip = ic["insights"], (ipv or {}).get("insights", {})
        out["platforms"]["instagram"] = {"followers": ic["followers"], "followers_asof": True, "metrics": [
            ["Total posts", _pair(nv(ic, "posts"), nv(ipv, "posts"))],
            ["Total reach (posts)", _pair(nv(ic, "reach"), nv(ipv, "reach"))],
            ["Total impressions (posts)", _pair(nv(ic, "views"), nv(ipv, "views"))],
            ["Engagement (posts)", _pair(nv(ic, "engagement"), nv(ipv, "engagement"))],
            ["Followers gained", _pair(ic["gained"], (ipv or {}).get("gained"))],
            ["Profile views", _pair(i["profile_views"], ip.get("profile_views"))],
            ["Website clicks", _pair(i["website_clicks"], ip.get("website_clicks"))]]}
    else:
        out["errors"]["instagram"] = r[("ig", "cur")][1]
    # LinkedIn
    lc, lp = g("li", "cur"), g("li", "prev")
    if lc:
        eng = lambda d: sum(p["engagement"] for p in d["posts"]) if d else None
        ad, adp = lc.get("admin"), (lp or {}).get("admin")
        pv = lambda k: _pair(ad[k] if ad else None, adp[k] if adp else None)
        metrics = [["Total posts", _pair(len(lc["posts"]), len(lp["posts"]) if lp else None)]]
        if ad:   # LinkedIn admin analytics for the selected period (same figures as the original dashboard)
            metrics += [["Impressions (total)", pv("impressions_total")], ["Impressions (organic)", pv("impressions")],
                        ["Clicks (organic)", pv("clicks")], ["Engagement (organic)", pv("engagement")],
                        ["Total followers gained", pv("gained")], ["Total page views", pv("page_views")],
                        ["Total unique visitors", pv("visitors")]]
        else:
            metrics += [["Engagement (posts)", _pair(eng(lc), eng(lp))],
                        ["Followers gained", _pair(_followers_gained_from_snapshots("linkedin", start, end),
                                                   _followers_gained_from_snapshots("linkedin", ps, pe))]]
        out["platforms"]["linkedin"] = {"followers": lc["followers"], "followers_asof": bool(ad), "metrics": metrics,
                                        "unavailable": [] if ad else ["Impressions", "Clicks", "Page views", "Unique visitors"],
                                        "admin_error": lc.get("admin_error")}
    else:
        out["errors"]["linkedin"] = r[("li", "cur")][1]

    # Totals + posts (a platform that failed or has no value for a metric is simply left out of the sum)
    def tot(key):
        def add(ds):
            vals = [d["n"][key] for d in ds if d and d["n"].get(key) is not None]
            return sum(vals) if vals else None
        return _pair(add((fc, ic, lc)), add((fp, ipv, lp)))
    out["totals"] = {k: tot(k) for k in ("views", "engagement", "posts", "gained")}
    li_posts = sorted(lc["posts"], key=lambda p: (p["date"], p["engagement"]), reverse=True) if lc else []
    out["li_posts"] = li_posts
    out["li_breakdown"] = linkedin_posts.breakdown(li_posts)
    out["posts"] = []   # the mixed-platform list was replaced by the LinkedIn-only section
    out["notes"] = ["LinkedIn impressions, clicks, page views, unique visitors and followers gained are admin-only analytics, so they come from the LinkedIn Analytics tab of the reporting Google Sheet (as in the original dashboard), summed per day over the selected period. Followers, posts and post reactions come from public data (Apify).",
                    "Reach, impressions and engagement are summed over the posts published in the selected period (Facebook: unique people reached, and reactions + comments + shares; Instagram: reach, and likes + comments + shares + saves), not the whole account. A post's reach keeps growing for a few days after it is published. Followers are as at the end of the period for Facebook and Instagram."]
    return out
