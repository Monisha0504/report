"""Deterministic sample data (shaped like the sheet) used until Google credentials are configured."""
from __future__ import annotations

import random
from datetime import date

from . import config


def _rng(start: date, end: date, salt: str) -> random.Random:
    return random.Random(f"{start}{end}{salt}")


def ga4_period(start: date, end: date) -> dict:
    r = _rng(start, end, "ga4")
    users = r.randint(480, 720)
    india_users = int(users * r.uniform(0.6, 0.75))

    def summary(u: int) -> dict:
        return {"total_users": u, "new_users": int(u * r.uniform(0.82, 0.95)), "sessions": int(u * r.uniform(1.1, 1.3)),
                "engagement_rate": r.uniform(0.4, 0.62), "avg_session_duration_sec": r.uniform(30, 90)}

    def channels(u: int) -> dict:
        w = [0.5, 0.33, 0.08, 0.01, 0.01]
        return {c: int(u * x) for c, x in zip(config.CHANNEL_ORDER, w)}

    return {"overall": summary(users), "india": summary(india_users),
            "channels_overall": channels(users), "channels_india": channels(india_users)}


def ga4_total_users(start: date, end: date) -> int:
    return ga4_period(start, end)["overall"]["total_users"] * 4  # rough month-to-date


def gsc_buckets(start: date, end: date) -> dict:
    r = _rng(start, end, "gsc")
    def mk(scale: float) -> dict:
        d = {"1-5": int(r.randint(150, 230) * scale), "6-10": int(r.randint(90, 140) * scale), "11-20": int(r.randint(100, 160) * scale),
             "21-50": int(r.randint(240, 360) * scale), "51-100": int(r.randint(70, 110) * scale)}
        d["total"] = sum(d.values()); d["branded"] = int(d["total"] * 0.05); d["non_branded"] = d["total"] - d["branded"]
        return d
    from . import products as prod
    prods = {k: {"label": v["label"], **mk(sc)} for (k, v), sc in zip(prod.PRODUCTS.items(), (0.12, 0.1, 0.3, 0.01))}
    return {"all": mk(1.0), "no_blogs": mk(0.55), "products": prods}


def gsc_totals(start: date, end: date) -> dict:
    r = _rng(start, end, "gt")
    imp = r.randint(8000, 10000); clicks = r.randint(250, 340)
    return {"clicks": clicks, "impressions": imp, "ctr": clicks / imp, "position": r.uniform(11, 14)}
