# Portfolio Monitor

A simple Streamlit app to track a watchlist of US-listed stocks, with portfolio P&L, upcoming earnings dates, and recent SEC filings.

## Features (v1)

- **Dynamic watchlist** — add/remove tickers through the UI
- **Live prices** — current price + daily change for each ticker
- **Portfolio P&L** — manual entry of holdings (ticker, shares, cost basis), unrealized P&L calculation
- **Upcoming earnings** — next earnings date for each tracked ticker
- **SEC filings** — recent 10-K, 10-Q, 8-K, DEF 14A and other relevant filings (last 30 days, configurable)
- **Save / restore** — download watchlist and holdings as CSV, upload to restore between sessions

## Cost: $0

- Free hosting on Streamlit Community Cloud
- Free data via Yahoo Finance (yfinance) and SEC EDGAR
- No API keys required

## Deployment guide (zero local install required)

You can do all of this from a browser only — useful if your work laptop doesn't allow installs.

### Step 1: Create a free GitHub account (if you don't have one)

Go to https://github.com → Sign up.

### Step 2: Create a new public repository

1. Click the "+" icon top right → "New repository"
2. Name it something like `portfolio-monitor`
3. Set it to **Public** (required for Streamlit Community Cloud free tier)
4. Check "Add a README file"
5. Click "Create repository"

### Step 3: Add the app files via GitHub web editor

For each of the three files in this folder (`app.py`, `requirements.txt`, `README.md`):

1. In your new repo, click "Add file" → "Create new file"
2. Type the filename (e.g. `app.py`)
3. Paste the file contents
4. Scroll down, click "Commit new file"

Repeat for `requirements.txt` and `README.md`.

### Step 4: Deploy on Streamlit Community Cloud

1. Go to https://share.streamlit.io
2. Click "Sign in with GitHub" — authorize Streamlit
3. Click "New app"
4. Select your repository (`portfolio-monitor`)
5. Branch: `main`
6. Main file path: `app.py`
7. Click "Deploy"

Wait 2-3 minutes for the first deployment. Streamlit will install dependencies from `requirements.txt` and start the app. You'll get a URL like `https://yourusername-portfolio-monitor.streamlit.app/`.

That URL is your app. Bookmark it. Open it from any browser, including your work laptop.

### Updating the app later

Edit any file in your GitHub repo (via web editor), commit changes, and Streamlit Cloud auto-redeploys within a minute.

## Privacy note

The app's **code** is in a public GitHub repo. That's just generic stock-tracking code — nothing sensitive.

Your **watchlist and holdings** are stored only in your browser session. They're never sent to GitHub or stored anywhere persistent. To save between sessions, use the "Download CSV" buttons in the sidebar and re-upload next time.

## Limitations of v1

- Holdings persistence is manual (CSV download/upload). v2 could add a free cloud database.
- Yahoo Finance data is delayed up to 15 min and occasionally has gaps.
- Earnings dates are sometimes wrong (yfinance returns last announced date instead of next). Verify before acting.
- SEC EDGAR rate-limited at ~10 req/sec. Fine for watchlists under 50 names.
- US-listed stocks only. ADRs work; pure foreign-listed equities won't.
- Crypto not supported in v1.

## Troubleshooting

**App fails to load on first deployment.**
Usually a `requirements.txt` issue. Check Streamlit Cloud logs. If yfinance fails, try pinning version: `yfinance==0.2.51`.

**Prices show as `—` for some tickers.**
Yahoo Finance data gap — try refreshing in 5 min, or check if ticker is correct.

**Earnings date looks wrong.**
yfinance sometimes returns past dates. Cross-check with company IR page.

**SEC filings empty for a ticker.**
Some tickers don't map cleanly to SEC CIK. Check the ticker is US-listed and reports to SEC.

## Future versions

Possible v2 additions:
- Persistent database (Supabase free tier) so holdings save automatically
- News aggregation per ticker
- Decision journal (capture buy/sell rationale + post-mortem)
- Crypto tracking
- Charts (price history, technicals)
- Alerts when earnings approach or filings drop
