"""
Portfolio Monitor v1
- Dynamic watchlist (add/remove tickers)
- Live prices with daily change
- Upcoming earnings dates
- Recent SEC filings (last 30 days)
- Portfolio P&L tracking
- CSV download/upload for persistence

Built for Streamlit Community Cloud (free hosting).
"""

import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from datetime import datetime, timedelta, timezone
import io
import time

# ------------------------------------------------------------------
# Page configuration
# ------------------------------------------------------------------
st.set_page_config(
    page_title="Portfolio Monitor",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ------------------------------------------------------------------
# Styling — restrained, dense, financial-terminal feel
# ------------------------------------------------------------------
st.markdown(
    """
    <style>
        .block-container { padding-top: 1.5rem; padding-bottom: 2rem; max-width: 1400px; }
        h1 { font-size: 1.6rem !important; font-weight: 600 !important; letter-spacing: -0.02em; }
        h2 { font-size: 1.15rem !important; font-weight: 600 !important; margin-top: 1.5rem !important; }
        h3 { font-size: 0.95rem !important; font-weight: 600 !important; }
        [data-testid="stMetricValue"] { font-size: 1.1rem !important; font-weight: 600; }
        [data-testid="stMetricLabel"] { font-size: 0.75rem !important; text-transform: uppercase; letter-spacing: 0.05em; opacity: 0.7; }
        .pos { color: #15803d; font-weight: 600; }
        .neg { color: #b91c1c; font-weight: 600; }
        .neutral { color: #6b7280; }
        .small { font-size: 0.8rem; opacity: 0.7; }
        .stDataFrame { font-size: 0.85rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------
# Session state initialization
# ------------------------------------------------------------------
if "watchlist" not in st.session_state:
    # Default watchlist = the 8 names from your deep-dive work
    st.session_state.watchlist = ["HALO", "DLO", "KVYO", "BRZE", "MNTN", "TMDX", "ZETA", "CELH"]

if "holdings" not in st.session_state:
    # holdings = list of dicts: {ticker, shares, cost_basis}
    st.session_state.holdings = []

if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = None


# ------------------------------------------------------------------
# Data fetching — cached to avoid hammering APIs
# ------------------------------------------------------------------
@st.cache_data(ttl=300)  # 5 minute cache
def get_price_data(ticker: str) -> dict:
    """Fetch current price and daily change for a ticker via yfinance."""
    try:
        t = yf.Ticker(ticker)
        info = t.info
        # Try fast_info first (more reliable), fallback to info
        try:
            fast = t.fast_info
            current = fast.get("last_price") or fast.get("lastPrice")
            prev_close = fast.get("previous_close") or fast.get("previousClose")
        except Exception:
            current = info.get("currentPrice") or info.get("regularMarketPrice")
            prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")

        if current is None or prev_close is None:
            return {"ticker": ticker, "price": None, "change_pct": None, "name": ticker, "error": "No price data"}

        change_pct = ((current - prev_close) / prev_close) * 100 if prev_close else 0
        return {
            "ticker": ticker,
            "price": float(current),
            "prev_close": float(prev_close),
            "change_pct": float(change_pct),
            "name": info.get("shortName") or info.get("longName") or ticker,
            "market_cap": info.get("marketCap"),
            "sector": info.get("sector"),
            "error": None,
        }
    except Exception as e:
        return {"ticker": ticker, "price": None, "change_pct": None, "name": ticker, "error": str(e)[:80]}


@st.cache_data(ttl=3600)  # 1 hour cache (earnings dates don't change often)
def get_earnings_date(ticker: str) -> dict:
    """Fetch next earnings date for a ticker."""
    try:
        t = yf.Ticker(ticker)
        cal = t.calendar
        if cal is None:
            return {"ticker": ticker, "next_earnings": None, "days_until": None}

        # yfinance returns calendar as dict in newer versions
        earnings_date = None
        if isinstance(cal, dict):
            ed = cal.get("Earnings Date")
            if ed and isinstance(ed, list) and len(ed) > 0:
                earnings_date = ed[0]
            elif ed:
                earnings_date = ed
        elif hasattr(cal, "loc"):
            try:
                ed = cal.loc["Earnings Date"]
                if hasattr(ed, "iloc"):
                    earnings_date = ed.iloc[0]
                else:
                    earnings_date = ed
            except Exception:
                pass

        if earnings_date is None:
            return {"ticker": ticker, "next_earnings": None, "days_until": None}

        # Convert to date
        if isinstance(earnings_date, str):
            earnings_date = pd.to_datetime(earnings_date).date()
        elif hasattr(earnings_date, "date"):
            earnings_date = earnings_date.date()

        days_until = (earnings_date - datetime.now().date()).days
        return {"ticker": ticker, "next_earnings": earnings_date, "days_until": days_until}
    except Exception:
        return {"ticker": ticker, "next_earnings": None, "days_until": None}


@st.cache_data(ttl=3600)  # 1 hour cache
def get_sec_cik(ticker: str) -> str | None:
    """Get SEC CIK for a ticker. Required for SEC EDGAR API."""
    try:
        url = "https://www.sec.gov/files/company_tickers.json"
        headers = {"User-Agent": "PortfolioMonitor research@example.com"}
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        for entry in data.values():
            if entry.get("ticker", "").upper() == ticker.upper():
                cik = str(entry["cik_str"]).zfill(10)
                return cik
        return None
    except Exception:
        return None


@st.cache_data(ttl=1800)  # 30 minute cache
def get_recent_filings(ticker: str, days: int = 30) -> list:
    """Fetch recent SEC filings for a ticker via EDGAR API."""
    cik = get_sec_cik(ticker)
    if cik is None:
        return []

    try:
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        headers = {"User-Agent": "PortfolioMonitor research@example.com"}
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return []
        data = r.json()
        recent = data.get("filings", {}).get("recent", {})
        if not recent:
            return []

        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accession = recent.get("accessionNumber", [])
        primary_doc = recent.get("primaryDocument", [])

        cutoff = datetime.now().date() - timedelta(days=days)
        results = []

        # Forms we care about — filter out routine ones like Form 4 (insider trades)
        # to keep signal high. User can change this list later.
        relevant_forms = {"10-K", "10-Q", "8-K", "DEF 14A", "S-1", "20-F", "6-K", "13D", "13G", "13D/A", "13G/A"}

        for i in range(len(forms)):
            try:
                filing_date = datetime.strptime(dates[i], "%Y-%m-%d").date()
                if filing_date < cutoff:
                    continue
                if forms[i] not in relevant_forms:
                    continue
                acc_clean = accession[i].replace("-", "")
                doc_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{primary_doc[i]}"
                results.append({
                    "form": forms[i],
                    "date": filing_date,
                    "url": doc_url,
                })
            except (IndexError, ValueError):
                continue

        return results
    except Exception:
        return []


# ------------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------------
def format_pct(pct: float) -> str:
    """Format percentage with color coding via HTML."""
    if pct is None:
        return "—"
    cls = "pos" if pct > 0 else ("neg" if pct < 0 else "neutral")
    sign = "+" if pct > 0 else ""
    return f'<span class="{cls}">{sign}{pct:.2f}%</span>'


def format_money(val: float, decimals: int = 2) -> str:
    if val is None:
        return "—"
    return f"${val:,.{decimals}f}"


def format_market_cap(mc) -> str:
    if mc is None:
        return "—"
    if mc >= 1e12:
        return f"${mc/1e12:.2f}T"
    if mc >= 1e9:
        return f"${mc/1e9:.2f}B"
    if mc >= 1e6:
        return f"${mc/1e6:.0f}M"
    return f"${mc:,.0f}"


# ------------------------------------------------------------------
# Sidebar — controls and watchlist management
# ------------------------------------------------------------------
with st.sidebar:
    st.markdown("### Portfolio Monitor")
    st.caption("v1 — built on Streamlit + yfinance + SEC EDGAR")

    st.divider()

    # Watchlist management
    st.markdown("#### Watchlist")
    new_ticker = st.text_input("Add ticker (e.g. AAPL)", key="new_ticker_input").upper().strip()
    col_add, col_clear = st.columns(2)
    with col_add:
        if st.button("Add", use_container_width=True):
            if new_ticker and new_ticker not in st.session_state.watchlist:
                st.session_state.watchlist.append(new_ticker)
                st.rerun()
    with col_clear:
        if st.button("Clear all", use_container_width=True):
            st.session_state.watchlist = []
            st.rerun()

    if st.session_state.watchlist:
        ticker_to_remove = st.selectbox(
            "Remove ticker",
            options=[""] + sorted(st.session_state.watchlist),
            key="remove_ticker_select",
        )
        if ticker_to_remove and st.button("Remove", use_container_width=True):
            st.session_state.watchlist.remove(ticker_to_remove)
            st.rerun()

    st.caption(f"Tracking {len(st.session_state.watchlist)} tickers")

    st.divider()

    # Refresh control
    if st.button("🔄 Refresh data", use_container_width=True, type="primary"):
        st.cache_data.clear()
        st.session_state.last_refresh = datetime.now()
        st.rerun()

    if st.session_state.last_refresh:
        st.caption(f"Last refresh: {st.session_state.last_refresh.strftime('%H:%M:%S')}")
    else:
        st.caption("Data cached for 5 min (prices), 30 min (filings), 1 hr (earnings)")

    st.divider()

    # Save / Load state
    st.markdown("#### Save / Load")

    # Build CSV for download
    save_data = {
        "watchlist": ",".join(st.session_state.watchlist),
        "holdings": pd.DataFrame(st.session_state.holdings).to_csv(index=False) if st.session_state.holdings else "",
    }

    # Watchlist CSV
    watchlist_csv = "ticker\n" + "\n".join(st.session_state.watchlist)
    st.download_button(
        "💾 Download watchlist CSV",
        watchlist_csv,
        file_name=f"watchlist_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
        use_container_width=True,
    )

    # Holdings CSV
    if st.session_state.holdings:
        holdings_df = pd.DataFrame(st.session_state.holdings)
        holdings_csv = holdings_df.to_csv(index=False)
        st.download_button(
            "💾 Download holdings CSV",
            holdings_csv,
            file_name=f"holdings_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    uploaded_watchlist = st.file_uploader("Restore watchlist CSV", type="csv", key="restore_watchlist")
    if uploaded_watchlist is not None:
        try:
            df = pd.read_csv(uploaded_watchlist)
            if "ticker" in df.columns:
                tickers = df["ticker"].dropna().str.upper().str.strip().tolist()
                st.session_state.watchlist = list(dict.fromkeys(tickers))  # dedupe preserving order
                st.success(f"Loaded {len(tickers)} tickers")
                st.rerun()
        except Exception as e:
            st.error(f"Could not parse: {e}")

    uploaded_holdings = st.file_uploader("Restore holdings CSV", type="csv", key="restore_holdings")
    if uploaded_holdings is not None:
        try:
            df = pd.read_csv(uploaded_holdings)
            required = {"ticker", "shares", "cost_basis"}
            if required.issubset(df.columns):
                st.session_state.holdings = df[list(required)].to_dict("records")
                st.success(f"Loaded {len(df)} positions")
                st.rerun()
            else:
                st.error(f"CSV must have columns: {', '.join(required)}")
        except Exception as e:
            st.error(f"Could not parse: {e}")

# ------------------------------------------------------------------
# Main content — tabbed layout
# ------------------------------------------------------------------
st.title("Portfolio Monitor")

tab_watchlist, tab_portfolio, tab_earnings, tab_filings = st.tabs([
    "📋 Watchlist",
    "💼 Portfolio",
    "📅 Earnings",
    "📄 SEC Filings",
])

# ------------------------------------------------------------------
# Tab 1: Watchlist with prices
# ------------------------------------------------------------------
with tab_watchlist:
    if not st.session_state.watchlist:
        st.info("No tickers in watchlist. Add one in the sidebar.")
    else:
        rows = []
        with st.spinner(f"Fetching prices for {len(st.session_state.watchlist)} tickers..."):
            for ticker in st.session_state.watchlist:
                data = get_price_data(ticker)
                rows.append(data)

        # Build a clean dataframe
        df = pd.DataFrame(rows)

        if df.empty:
            st.warning("No data available.")
        else:
            # Summary metrics across watchlist
            valid = df[df["price"].notna()]
            if not valid.empty:
                gainers = (valid["change_pct"] > 0).sum()
                losers = (valid["change_pct"] < 0).sum()
                avg_change = valid["change_pct"].mean()
                col_a, col_b, col_c, col_d = st.columns(4)
                col_a.metric("Tickers", len(df))
                col_b.metric("Gainers", int(gainers))
                col_c.metric("Losers", int(losers))
                col_d.metric("Avg change", f"{avg_change:+.2f}%")

            st.markdown("### Prices")

            # Render as HTML table for color-coded change column
            display_rows = []
            for _, r in df.iterrows():
                if r["price"] is None:
                    display_rows.append({
                        "Ticker": r["ticker"],
                        "Name": r.get("name", r["ticker"]) if isinstance(r.get("name"), str) else r["ticker"],
                        "Sector": r.get("sector") or "—",
                        "Price": "—",
                        "Change": "—",
                        "Market Cap": "—",
                    })
                else:
                    display_rows.append({
                        "Ticker": r["ticker"],
                        "Name": r["name"][:40] if r["name"] else r["ticker"],
                        "Sector": r.get("sector") or "—",
                        "Price": format_money(r["price"]),
                        "Change": format_pct(r["change_pct"]),
                        "Market Cap": format_market_cap(r.get("market_cap")),
                    })

            display_df = pd.DataFrame(display_rows)

            # Use HTML rendering for color-coded change column
            html = display_df.to_html(escape=False, index=False, classes="dataframe")
            st.markdown(html, unsafe_allow_html=True)

            # Show errors if any
            errors = df[df["error"].notna() & (df["price"].isna())]
            if not errors.empty:
                with st.expander(f"⚠️ {len(errors)} ticker(s) had errors"):
                    for _, r in errors.iterrows():
                        st.text(f"{r['ticker']}: {r['error']}")

# ------------------------------------------------------------------
# Tab 2: Portfolio with P&L
# ------------------------------------------------------------------
with tab_portfolio:
    st.markdown("### Holdings")
    st.caption("Manual entry. Use sidebar to download/restore CSV between sessions.")

    # Add new holding form
    with st.expander("➕ Add new position", expanded=len(st.session_state.holdings) == 0):
        col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
        with col1:
            h_ticker = st.text_input("Ticker", key="h_ticker_input").upper().strip()
        with col2:
            h_shares = st.number_input("Shares", min_value=0.0, step=1.0, format="%.4f", key="h_shares_input")
        with col3:
            h_cost = st.number_input("Cost basis ($/share)", min_value=0.0, step=0.01, format="%.4f", key="h_cost_input")
        with col4:
            st.write("")  # spacer
            st.write("")
            if st.button("Add position", use_container_width=True):
                if h_ticker and h_shares > 0 and h_cost > 0:
                    st.session_state.holdings.append({
                        "ticker": h_ticker,
                        "shares": h_shares,
                        "cost_basis": h_cost,
                    })
                    st.success(f"Added {h_shares} shares of {h_ticker} at ${h_cost}")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("All fields required and must be positive")

    if not st.session_state.holdings:
        st.info("No holdings yet. Add a position above.")
    else:
        # Fetch prices for holdings
        holdings_with_prices = []
        with st.spinner("Calculating P&L..."):
            for i, h in enumerate(st.session_state.holdings):
                price_data = get_price_data(h["ticker"])
                current_price = price_data["price"] if price_data["price"] else 0
                cost_total = h["shares"] * h["cost_basis"]
                market_value = h["shares"] * current_price if current_price else 0
                unrealized_pnl = market_value - cost_total
                pnl_pct = (unrealized_pnl / cost_total * 100) if cost_total else 0
                day_change_dollar = h["shares"] * (current_price - price_data.get("prev_close", current_price)) if current_price else 0

                holdings_with_prices.append({
                    "idx": i,
                    "ticker": h["ticker"],
                    "shares": h["shares"],
                    "cost_basis": h["cost_basis"],
                    "current_price": current_price,
                    "cost_total": cost_total,
                    "market_value": market_value,
                    "unrealized_pnl": unrealized_pnl,
                    "pnl_pct": pnl_pct,
                    "day_change_pct": price_data.get("change_pct", 0),
                    "day_change_dollar": day_change_dollar,
                })

        # Portfolio totals
        total_cost = sum(h["cost_total"] for h in holdings_with_prices)
        total_value = sum(h["market_value"] for h in holdings_with_prices)
        total_pnl = total_value - total_cost
        total_pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0
        total_day_change = sum(h["day_change_dollar"] for h in holdings_with_prices)

        col_a, col_b, col_c, col_d = st.columns(4)
        col_a.metric("Total cost", format_money(total_cost))
        col_b.metric("Market value", format_money(total_value), delta=f"{total_pnl_pct:+.2f}%")
        col_c.metric("Unrealized P&L", format_money(total_pnl))
        col_d.metric("Today's P&L", format_money(total_day_change))

        st.markdown("### Positions")

        # Build display table
        position_rows = []
        for h in holdings_with_prices:
            position_rows.append({
                "Ticker": h["ticker"],
                "Shares": f"{h['shares']:.4f}".rstrip("0").rstrip("."),
                "Cost basis": format_money(h["cost_basis"]),
                "Current": format_money(h["current_price"]) if h["current_price"] else "—",
                "Day %": format_pct(h["day_change_pct"]),
                "Cost total": format_money(h["cost_total"]),
                "Market value": format_money(h["market_value"]) if h["current_price"] else "—",
                "Unrealized P&L": format_money(h["unrealized_pnl"]) if h["current_price"] else "—",
                "Return %": format_pct(h["pnl_pct"]) if h["current_price"] else "—",
            })

        df_positions = pd.DataFrame(position_rows)
        st.markdown(df_positions.to_html(escape=False, index=False), unsafe_allow_html=True)

        # Position management
        st.markdown("### Manage positions")
        col_remove, _ = st.columns([1, 2])
        with col_remove:
            position_labels = [
                f"{h['ticker']} ({h['shares']:.2f} sh @ ${h['cost_basis']:.2f})"
                for h in st.session_state.holdings
            ]
            to_remove = st.selectbox("Remove position", options=[""] + position_labels)
            if to_remove and st.button("Remove this position"):
                idx = position_labels.index(to_remove)
                st.session_state.holdings.pop(idx)
                st.rerun()

# ------------------------------------------------------------------
# Tab 3: Upcoming earnings
# ------------------------------------------------------------------
with tab_earnings:
    st.markdown("### Upcoming earnings")
    st.caption("Earnings dates fetched from Yahoo Finance. Sometimes returns last announced date instead of next — verify before acting.")

    if not st.session_state.watchlist:
        st.info("No tickers in watchlist.")
    else:
        earnings_data = []
        with st.spinner("Fetching earnings dates..."):
            for ticker in st.session_state.watchlist:
                ed = get_earnings_date(ticker)
                earnings_data.append(ed)

        # Filter and sort
        future = [e for e in earnings_data if e["next_earnings"] and e["days_until"] is not None and e["days_until"] >= 0]
        past = [e for e in earnings_data if e["next_earnings"] and e["days_until"] is not None and e["days_until"] < 0]
        unknown = [e for e in earnings_data if e["next_earnings"] is None]

        future.sort(key=lambda x: x["days_until"])
        past.sort(key=lambda x: x["days_until"], reverse=True)

        if future:
            st.markdown("#### Upcoming")
            up_rows = []
            for e in future:
                urgency = "🔴" if e["days_until"] <= 7 else ("🟡" if e["days_until"] <= 14 else "🟢")
                up_rows.append({
                    "": urgency,
                    "Ticker": e["ticker"],
                    "Date": e["next_earnings"].strftime("%a %b %d, %Y") if e["next_earnings"] else "—",
                    "Days until": e["days_until"],
                })
            st.dataframe(pd.DataFrame(up_rows), hide_index=True, use_container_width=True)

        if past:
            with st.expander(f"📜 Recent ({len(past)})"):
                past_rows = []
                for e in past:
                    past_rows.append({
                        "Ticker": e["ticker"],
                        "Date": e["next_earnings"].strftime("%a %b %d, %Y") if e["next_earnings"] else "—",
                        "Days ago": -e["days_until"],
                    })
                st.dataframe(pd.DataFrame(past_rows), hide_index=True, use_container_width=True)

        if unknown:
            with st.expander(f"❓ Unknown ({len(unknown)})"):
                st.text("Could not fetch earnings dates for: " + ", ".join(e["ticker"] for e in unknown))

# ------------------------------------------------------------------
# Tab 4: SEC filings
# ------------------------------------------------------------------
with tab_filings:
    st.markdown("### Recent SEC filings")
    st.caption("Last 30 days. Includes 10-K, 10-Q, 8-K, DEF 14A, S-1, 20-F, 6-K, 13D/G filings.")

    if not st.session_state.watchlist:
        st.info("No tickers in watchlist.")
    else:
        # Days filter
        days_back = st.slider("Look back (days)", min_value=7, max_value=90, value=30, step=7)

        all_filings = []
        with st.spinner(f"Fetching SEC filings (last {days_back} days)..."):
            for ticker in st.session_state.watchlist:
                filings = get_recent_filings(ticker, days=days_back)
                for f in filings:
                    f["ticker"] = ticker
                    all_filings.append(f)

        if not all_filings:
            st.info(f"No relevant filings in the last {days_back} days for tracked tickers.")
        else:
            # Sort by date descending
            all_filings.sort(key=lambda x: x["date"], reverse=True)

            # Display as a table with clickable links
            filing_rows = []
            for f in all_filings:
                form_emoji = {
                    "10-K": "📕", "10-Q": "📘", "8-K": "📋",
                    "DEF 14A": "🗳️", "S-1": "📝", "13D": "🎯", "13G": "🎯",
                    "13D/A": "🎯", "13G/A": "🎯", "20-F": "🌍", "6-K": "🌍",
                }.get(f["form"], "📄")

                filing_rows.append({
                    "": form_emoji,
                    "Ticker": f["ticker"],
                    "Form": f["form"],
                    "Date": f["date"].strftime("%Y-%m-%d"),
                    "Days ago": (datetime.now().date() - f["date"]).days,
                    "Link": f'<a href="{f["url"]}" target="_blank">View</a>',
                })

            df_filings = pd.DataFrame(filing_rows)
            st.markdown(df_filings.to_html(escape=False, index=False), unsafe_allow_html=True)

            st.caption(f"{len(all_filings)} filings across {len(set(f['ticker'] for f in all_filings))} tickers")

# ------------------------------------------------------------------
# Footer
# ------------------------------------------------------------------
st.divider()
st.caption(
    "Data: Yahoo Finance (prices, earnings) and SEC EDGAR (filings). "
    "Prices delayed up to 15 min. This is not investment advice. "
    "Holdings are session-only — download CSV to persist between sessions."
)
      
