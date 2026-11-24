"""LinkedIn post classification (product + post type) and the product x post-type breakdown.

Public LinkedIn data has no per-post impressions or clicks (those are only in LinkedIn's page-admin content export), so the
breakdown reports what is public: posts, reactions, comments, shares and engagement (their sum).
The rules below are heuristics on the post text/media; edit them here if a post lands in the wrong group."""
from __future__ import annotations

import re

PRODUCT_ORDER = ["fluidPrint", "fluidPro", "floTax", "Company / brand"]
TYPE_ORDER = ["Static image", "Multi-image", "Document / carousel", "Person post", "Text / video"]

# 1) an explicit product name wins (the earliest one in the text)
_EXPLICIT = (("fluidPro", r"fluid\s?pro\b"), ("fluidPrint", r"fluid\s?print"), ("floTax", r"flo\s?tax"))
# 2) company news (events, leadership, hiring) is not a product post
_COMPANY = r"leadership|executive|networking|we[’']re hiring|join (our|us)|award|anniversary|milestone|scaling for our next phase|last week was packed"
# 3) otherwise the topic decides
_TOPIC = (("floTax", r"\bgst|e-?way|e-?invoic"),
          ("fluidPrint", r"print"),
          ("fluidPro", r"cyber|dpdp|managed it|it infrastructure|it downtime|healthcare it|digital health|ai adoption|ai is reshaping|emr\b|hospitals?"))
# A "person post": an employee/leader speaking or being quoted
_PERSON = (r"dropping wisdom|\b(head|chief|director|vp|vice president|ceo|cto|cfo|coo|founder)\b\s*[-–—,]|in my experience"
           r"|\bi (believe|learned|think|see)\b|our (executive|leadership) (team|leaders?)")


def product_of(text: str) -> str:
    t = (text or "").lower()
    hits = [(m.start(), name) for name, rx in _EXPLICIT for m in [re.search(rx, t)] if m]
    if hits:
        return min(hits)[1]
    if re.search(_COMPANY, t):
        return "Company / brand"
    for name, rx in _TOPIC:
        if re.search(rx, t):
            return name
    return "Company / brand"


def type_of(post: dict) -> str:
    if re.search(_PERSON, post.get("content") or "", re.I):
        return "Person post"
    if post.get("document"):
        return "Document / carousel"
    n = len(post.get("postImages") or [])
    if n > 1:
        return "Multi-image"
    if n == 1:
        return "Static image"
    return "Text / video"


def cover_of(post: dict) -> str | None:
    """Thumbnail: the first image, or the cover page of a document/carousel."""
    imgs = post.get("postImages") or []
    if imgs and isinstance(imgs[0], dict) and imgs[0].get("url"):
        return imgs[0]["url"]
    doc = post.get("document") or {}
    for page in doc.get("coverPages") or []:
        urls = (page or {}).get("imageUrls") or []
        if urls:
            return urls[0]
    return None


def breakdown(posts: list[dict]) -> list[dict]:
    """Rows grouped product -> post type with posts / reactions / comments / shares / engagement, plus a subtotal per product."""
    def blank():
        return {"posts": 0, "reactions": 0, "comments": 0, "shares": 0, "engagement": 0}

    groups: dict[str, dict[str, dict]] = {}
    for p in posts:
        g = groups.setdefault(p["product"], {}).setdefault(p["ptype"], blank())
        g["posts"] += 1
        g["reactions"] += p["likes"]; g["comments"] += p["comments"]; g["shares"] += p["shares"]; g["engagement"] += p["engagement"]
    out = []
    for prod in [*PRODUCT_ORDER, *[k for k in groups if k not in PRODUCT_ORDER]]:
        if prod not in groups:
            continue
        total = blank()
        types = []
        for t in [*TYPE_ORDER, *[k for k in groups[prod] if k not in TYPE_ORDER]]:
            if t in groups[prod]:
                v = groups[prod][t]
                types.append({"type": t, **v, "avg": round(v["engagement"] / v["posts"], 1)})
                for k in total:
                    total[k] += v[k]
        out.append({"product": prod, "types": types, **total, "avg": round(total["engagement"] / total["posts"], 1)})
    return out
