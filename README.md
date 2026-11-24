# Wepsol weekly report tracker

Weekly dashboard: website traffic (GA4), search & keywords (Search Console + Keyword Planner volume), and social
(Facebook / Instagram via Meta Graph API, LinkedIn via the LinkedIn Analytics sheet + Apify).

## Run
Double-click `run.bat` (or: `pip install -r requirements.txt` then `python -m uvicorn app.main:app --port 8000`)
and open http://localhost:8000 . It opens on the latest finished 7-day week; a link like
`http://localhost:8000/?start=2026-11-10&end=2026-11-16` opens a chosen week.

## Folder
- `app/`      backend (FastAPI): `main.py` API, `google_clients.py` GA4 + Search Console, `social.py` Meta/LinkedIn,
              `linkedin_posts.py` product + post-type rules, `products.py` product page rules, `volumes.py` Keyword Planner, `config.py` settings
- `static/`   the page (`index.html`, `app.js`, `css/`)
- `data/`     `linkedin_analytics.csv` (LinkedIn page analytics export), `volumes.json` and `followers.json` (caches)
- `.env`      API keys, IDs and report settings. Keep it private - never commit or share it.

## Weekly routine
LinkedIn admin metrics (impressions, clicks, page views, visitors, followers gained) come from the LinkedIn Analytics tab.
Download that tab as CSV and replace `data/linkedin_analytics.csv` (or enable the Google Sheets API / a service account and it reads the sheet directly).

## Report rules (see `app/config.py`)
- India column: country = India, job/career pages excluded. Overall column: Looker "Bot Traffic" + "London and Amsterdam" filters
  plus South Korea and Germany (inferred), job pages kept.
- Keywords: India, positions 1-100 with Keyword Planner volume; products defined in `app/products.py`.

## Export
The **Export** button (top right) offers **PDF** (print-ready, one page per section - in the print dialog choose "Save as PDF")
and **CSV** (every table as data, opens in Excel). For the PDF, wait until the social section has loaded (it waits for you automatically).

## Deploy on Vercel
1. Put this folder in a Git repo (GitHub). `.gitignore` already keeps `.env` out - never commit it.
2. vercel.com -> Add New -> Project -> import the repo. Framework preset: Other. Root directory: this folder.
3. Project Settings -> Environment Variables: add every variable from `.env` (same names), plus `DASHBOARD_PASSWORD` (the site asks for it; any username).
4. Deploy. `vercel.json` routes everything to `api/index.py` and allows 60 seconds per request.
5. LinkedIn admin data: `data/linkedin_analytics.csv` is deliberately NOT in this public repo (it is Wepsol's real page analytics).
   Either make the repo private and remove the `data/*` lines from `.gitignore` so the CSV can be committed each week,
   or enable the Google Sheets API / a service account so the dashboard reads the sheet directly and no file is needed.
Notes: Vercel's disk is read-only (caches use /tmp and are lost on cold starts); the slow LinkedIn/Apify call can exceed the time limit on the free plan.

## What is (and is not) in Git
Pushed: `app/`, `static/`, `api/`, `vercel.json`, `requirements.txt`, `run.bat`, `.env.example`, this README.
Never pushed (see `.gitignore`): `.env` (all API keys), everything in `data/` (LinkedIn export, keyword-volume and follower caches), `__pycache__/`.

## LinkedIn admin data without a file (service account)
1. console.cloud.google.com -> create a project you own -> APIs & Services -> enable **Google Sheets API**.
2. IAM & Admin -> Service Accounts -> create one -> Keys -> Add key -> JSON (downloads a file).
3. Open the reporting Google Sheet -> Share -> add the service account's e-mail (it ends in `.iam.gserviceaccount.com`) as **Viewer**.
4. Locally set `GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE=path\to\key.json`; on Vercel add `GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON` with the file's whole text, then redeploy.
