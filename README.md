# Portfolio Monitor (v2)

A simple Streamlit app to track a watchlist of US-listed stocks, with portfolio P&L, upcoming earnings dates, recent SEC filings, and per-ticker notes. Data persists across sessions via Supabase.

## What's new in v2

- **Persistent storage** — watchlist + notes + holdings auto-save to Supabase. No more CSV download/upload.
- **Notes per ticker** — record your thesis or tracking reason for each name. Visible in the watchlist view.
- **Setup tab** — first-time configuration walkthrough is built into the app itself.

## Cost: $0

- Free hosting on Streamlit Community Cloud
- Free database via Supabase (free tier: 500MB DB, 2GB egress/month — way more than this app needs)
- Free data via Yahoo Finance and SEC EDGAR
- No API keys required for the data sources

## Deployment guide

### Already on v1?

Replace your existing `app.py` with the new one and update `requirements.txt` if needed. Then follow the **Supabase setup** section below to enable persistence. Without Supabase configured, the app falls back to session-only storage (works exactly like v1).

### Fresh install?

You'll need three things deployed: GitHub repo, Streamlit Cloud app, Supabase project. All can be set up from a browser only.

#### Step 1: GitHub repo

1. Sign in at https://github.com (create account if needed)
2. Click **+** → **New repository**
3. Name it (e.g. `portfolio-monitor`), make it **Public**, check "Add a README"
4. Click **Create repository**
5. For each file in this folder (`app.py`, `requirements.txt`, `README.md`), click **Add file** → **Create new file**, paste the contents, scroll down, click **Commit new file**

#### Step 2: Streamlit Community Cloud

1. Go to https://share.streamlit.io
2. Sign in with GitHub
3. Click **New app**
4. Select your repo, branch `main`, main file `app.py`
5. Click **Deploy**
6. Wait 2-3 minutes for first deploy. You'll get a URL like `https://yourusername-portfolio-monitor.streamlit.app/`

The app should now load. It'll show "● Session-only (no Supabase)" in the sidebar — that's expected. Continue to step 3 to enable persistence.

#### Step 3: Supabase setup

Open your deployed app. Click the **⚙️ Setup** tab. The app contains step-by-step instructions for:
- Creating a free Supabase account
- Creating a project
- Running the SQL to create tables
- Getting your API credentials
- Adding them as secrets in Streamlit Cloud

Total time: ~10 minutes.

When done, the sidebar will show "● Supabase connected" and your data persists across sessions.

## Privacy

- **Code** is in your public GitHub repo. No sensitive data lives in code.
- **Watchlist + holdings + notes** live in your Supabase project (private).
- **Supabase credentials** are in Streamlit Cloud secrets (not in your repo).
- **Anyone with your Streamlit URL** can see the app — but they need your Supabase credentials to read/write your data.

If you want to lock the app itself behind a password, add `streamlit-authenticator` to `requirements.txt` and we can add login on a future iteration.

## Limitations of v2

- Yahoo Finance data is delayed 15 min and occasionally has gaps.
- Earnings dates from yfinance can be stale (returns last announced instead of next). Always verify before acting.
- SEC EDGAR rate-limited at ~10 req/sec. Fine for watchlists under 50 names.
- US-listed stocks only. ADRs work; pure foreign-listed equities won't.
- Crypto not supported.

## Troubleshooting

**App loads but Supabase shows error.**
Check Streamlit Cloud → Settings → Secrets. Make sure `SUPABASE_URL` and `SUPABASE_ANON_KEY` are present and there are no extra spaces or quotes wrong.

**Can't add holdings — they don't save.**
Check the Setup tab. If Supabase isn't connected, the app falls back to session-only mode (data lost on browser close).

**Tables don't exist error.**
Re-run the SQL from the Setup tab in Supabase's SQL Editor.

**Earnings date wrong.**
Cross-check with company IR page. yfinance is unreliable for this.

**SEC filings empty for a ticker.**
Some tickers don't map to SEC CIK (foreign listings, micro caps). The app skips silently.

## Possible v3 features

In rough order of usefulness:
- Crypto support (Binance/Coinbase APIs)
- Decision journal (capture buy/sell rationale + post-mortem reviews)
- Price history charts (1Y, 5Y per ticker)
- Earnings call transcript links
- Alerts when earnings approach or filings drop
- Multiple watchlists / tags
- Authentication (login required to view)

Tell me which one(s) matter most after you've used v2 for a few weeks.
