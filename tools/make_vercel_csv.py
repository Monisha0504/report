"""Turn the full LinkedIn Analytics CSV export into the small text you paste into the Vercel variable LINKEDIN_CSV_DATA.

Usage (from the tracker folder):
    python tools/make_vercel_csv.py "C:\\path\\to\\Wepsol_DM_Reporting_Source_FY25 - LinkedIn Analytics.csv"
If no path is given it uses data/linkedin_analytics.csv. It writes data/linkedin_for_vercel.csv - open it, copy everything,
paste it as the value of LINKEDIN_CSV_DATA in Vercel (Settings -> Environment Variables), save and redeploy.
Only the columns the dashboard uses and the last 200 days are kept, so it stays small.
"""
import csv
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "data", "linkedin_analytics.csv")
NEED = ["Date", "Impressions (organic)", "Impressions (total)", "Clicks (organic)", "Reactions (organic)", "Comments (organic)",
        "Reposts (organic)", "Total page views (total)", "Total unique visitors (total)", "Total followers gained", "Total Page Followers "]

rows = list(csv.reader(open(src, encoding="utf-8-sig", newline="")))
head = rows[0]
missing = [c for c in NEED if c not in head]
if missing:
    sys.exit(f"These columns are missing from the CSV: {missing}")
idx = [head.index(c) for c in NEED]
body = [r for r in rows[1:] if len(r) > max(idx) and r[0].strip()][-200:]

out = io.StringIO()
w = csv.writer(out, lineterminator="\n")
w.writerow([c.strip() for c in NEED])
for r in body:
    w.writerow([r[i] for i in idx])
dest = os.path.join(ROOT, "data", "linkedin_for_vercel.csv")
open(dest, "w", encoding="utf-8", newline="").write(out.getvalue())
print(f"{len(body)} days ({body[0][0]} -> {body[-1][0]}), {len(out.getvalue())} bytes written to {dest}")
