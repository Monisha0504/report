"""Product lines for the keyword section. Each product's keywords are the Search Console queries that ranked on its pages.
The page rules were fitted against the dashboard's own per-product keyword counts (17-23 Nov 2026, keywords with volume):
fluidPrint 54 (here 54), floTax 48 (here 52), GST Verification 251 (here 250), fluidPro 2 (here 2)."""
PRODUCTS: dict[str, dict] = {
    # non-blog product/service pages mentioning fluidprint or managed-print
    "fluidprint": {"label": "fluidPrint", "contains": ["fluidprint", "managed-print"], "exclude": [], "exclude_blogs": True},
    # the four floTax product pages
    "flotax": {"label": "floTax", "exclude": [], "exclude_blogs": False,
               "contains": ["/solutions/flotax", "e-invoicing-and-e-way-bill-automation", "automate-your-gstr-filing", "gst-reconciliation-made-simple"]},
    # every page about GST: the verification tool plus the GST blog posts
    "gst_verification": {"label": "GST Verification", "contains": ["gst"], "exclude": [], "exclude_blogs": False},
    "fluidpro": {"label": "fluidPro", "contains": ["fluidpro"], "exclude": [], "exclude_blogs": False},
}


def matches(url: str, product: dict, is_blog: bool = False) -> bool:
    u = (url or "").lower()
    if product.get("exclude_blogs") and is_blog:
        return False
    return any(t in u for t in product["contains"]) and not any(t in u for t in product["exclude"])
