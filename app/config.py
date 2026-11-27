"""Settings, read from environment / .env. Nothing secret is hard-coded."""
from __future__ import annotations

import os
from datetime import date

try:
    from pathlib import Path
    from dotenv import load_dotenv
    _root = Path(__file__).resolve().parent.parent
    load_dotenv(_root / ".env")                # this folder's .env: API keys + IDs + report settings
except ImportError:  # python-dotenv is optional
    pass

# --- Google (GA4 + Search Console) -------------------------------------------
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")  # optional: service-account JSON path
# OAuth refresh-token login (already in the shared .env); has analytics + webmasters (Search Console) scopes
GA4_CLIENT_ID = os.getenv("GA4_CLIENT_ID", "")
GA4_CLIENT_SECRET = os.getenv("GA4_CLIENT_SECRET", "")
GA4_REFRESH_TOKEN = os.getenv("GA4_REFRESH_TOKEN", "")
GA4_PROPERTY_ID = os.getenv("GA4_PROPERTY_ID", "")
GSC_SITE_URL = os.getenv("GSC_SITE_URL", "")          # e.g. "sc-domain:wepsol.com"
WP_BASE = os.getenv("WP_BASE", "https://wepsol.com")  # blog list comes from the WordPress REST API

HAS_GOOGLE_AUTH = bool(GOOGLE_CREDENTIALS or (GA4_CLIENT_ID and GA4_CLIENT_SECRET and GA4_REFRESH_TOKEN))
LIVE = bool(HAS_GOOGLE_AUTH and GA4_PROPERTY_ID and GSC_SITE_URL)

# --- Report definition ---------------------------------------------------------
INDIA_COUNTRY = os.getenv("INDIA_COUNTRY", "India")    # GA4 `country` value
GSC_LAG_DAYS = int(os.getenv("GSC_LAG_DAYS", "3"))     # newest GSC date is ~today-3
MIN_IMPRESSIONS = int(os.getenv("MIN_IMPRESSIONS", "1"))  # a query must have this many impressions to count

# Traffic rules (verified: India + no job pages reproduces the dashboard's 539 users / 465 new users for 17-23 Nov)
EXCLUDE_JOB_PAGES = os.getenv("EXCLUDE_JOB_PAGES", "true").lower() == "true"
JOB_PAGE_TERMS = [t for t in os.getenv("JOB_PAGE_TERMS", "career,/job").split(",") if t]   # landing page contains any
# Looker filters applied to the Overall column (the India column is already India-only):
#   "Bot Traffic": City Singapore, Lanzhou; Country China, United States
#   "London": City London, Singapore, Boardman
#   "Amsterdam": City Amsterdam, Lanzhou; Country China, United States, Germany, France, South Korea
EXCLUDE_COUNTRIES = [c.strip() for c in os.getenv("EXCLUDE_COUNTRIES", "China,United States,Germany,France,South Korea").split(",") if c.strip()]
EXCLUDE_CITIES = [c.strip() for c in os.getenv("EXCLUDE_CITIES", "Singapore,Lanzhou,London,Boardman,Amsterdam").split(",") if c.strip()]
GSC_COUNTRY = os.getenv("GSC_COUNTRY", "ind")   # ISO-3 code for Search Console; "ind" matches the dashboard (995 vs 1,004 keywords); empty = worldwide

# Weeks repeat every 7 days from this anchor (17 Nov 2026 -> 23 Nov, then 24 Nov -> 30 Nov ...)
WEEK_ANCHOR = date.fromisoformat(os.getenv("WEEK_ANCHOR", "2026-11-17"))

# Targets from the sheet (editable)
TARGETS = {
    "monthly_traffic": int(os.getenv("TARGET_MONTHLY_TRAFFIC", "3000")),
    "weekly_traffic": int(os.getenv("TARGET_WEEKLY_TRAFFIC", "650")),
    "avg_session_duration_sec": int(os.getenv("TARGET_AVG_SESSION_SEC", "200")),
}

# GA4 default channel group -> sheet row. Paid Social, AI Assistant, Unassigned etc. have no row in the sheet (they are in the totals only).
CHANNEL_MAP = {
    "Direct": "Direct",
    "Organic Search": "Organic",
    "Referral": "Referral",
    "Organic Social": "Social",
    "Paid Search": "Paid+Display",
    "Display": "Paid+Display",
    "Cross-network": "Paid+Display",
    "Paid Other": "Paid+Display",
}
CHANNEL_ORDER = ["Direct", "Organic", "Referral", "Social", "Paid+Display"]

# Branded = Wepsol, WeP Digital or a product name. Fitted to the dashboard's count (49 here vs 48 there for 17-23 Nov).
BRAND_REGEX = os.getenv("BRAND_REGEX", r"\bwep\b|wepsol|fluidprint|fluid print|fluidpro|fluid pro|flotax|flo tax|flow tax|fluidworks|fluid works")
KEYWORD_BUCKETS = ["1-5", "6-10", "11-20", "21-50", "51-100"]

# --- Social ---------------------------------------------------------------------
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
META_PAGE_ID = os.getenv("META_PAGE_ID", "")
IG_USER_ID = os.getenv("IG_USER_ID", "")
META_GRAPH_VERSION = os.getenv("META_GRAPH_VERSION", "v21.0")
APIFY_TOKENS = [t for t in (os.getenv("APIFY_TOKEN", ""), os.getenv("APIFY_TOKEN_FALLBACK", ""), os.getenv("APIFY_TOKEN_FALLBACK2", "")) if t]
LINKEDIN_URL = os.getenv("LINKEDIN_URL", "https://www.linkedin.com/company/wep-sol/")
SOCIAL_LIVE = bool(META_ACCESS_TOKEN and META_PAGE_ID and IG_USER_ID)

# --- Hosting -------------------------------------------------------------------
from pathlib import Path as _Path
IS_VERCEL = bool(os.getenv("VERCEL"))
# Writable cache folder. On Vercel only /tmp is writable (and is wiped between cold starts); locally it is ./data
DATA_DIR = _Path(os.getenv("DATA_DIR") or ("/tmp" if IS_VERCEL else _Path(__file__).resolve().parent.parent / "data"))
