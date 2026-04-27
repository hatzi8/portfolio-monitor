"""
Portfolio Monitor v2
- Dynamic watchlist (add/remove tickers) with notes per ticker
- Live prices with daily change
- Upcoming earnings dates
- Recent SEC filings (last 30 days)
- Portfolio P&L tracking
- Persistent storage via Supabase (auto-save, auto-load)
- CSV download/upload as backup option

Built for Streamlit Community Cloud (free hosting) + Supabase (free tier).
"""

import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from datetime import datetime, timedelta, timezone
from typing import Optional
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
# Styling
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
        .note-cell { font-style: italic; opacity: 0.8; font-size: 0.85rem; }
        .storage-ok { color: #15803d; font-size: 0.75rem; }
        .storage-fail { color: #b91c1c; font-size: 0.75rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ------------------------------------------------------------------
# Supabase client
# ------------------------------------------------------------------
class SupabaseClient:
    """Minimal Supabase REST client — no SDK dependency."""

    def __init__(self, url: str, anon_key: str):
        self.url = url.rstrip("/")
        self.headers = {
            "apikey": anon_key,
            "Authorization": f"Bearer {anon_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def select(self, table: str, columns: str = "*") -> list:
        try:
            r = requests.get(
                f"{self.url}/rest/v1/{table}",
                headers=self.headers,
                params={"select": columns},
                timeout=10,
            )
            if r.status_code == 200:
                return r.json()
            return []
        except Exception:
            return []

    def upsert(self, table: str, data, on_conflict: str = "ticker") -> bool:
        try:
            headers = {**self.headers, "Prefer": "resolution=merge-duplicates,return=representation"}
            r = requests.post(
                f"{self.url}/rest/v1/{table}",
                headers=headers,
                json=data,
                params={"on_conflict": on_conflict},
                timeout=10,
            )
            return r.status_code in (200, 201)
        except Exception:
            return False

    def delete(self, table: str, column: str, value: str) -> bool:
        try:
            r = requests.delete(
                f"{self.url}/rest/v1/{table}",
                headers=self.headers,
                params={column: f"eq.{value}"},
                timeout=10,
            )
            return r.status_code in (200, 204)
        except Exception:
            return False


def get_supabase() -> Optional[SupabaseClient]:
    """Initialize Supabase client from Streamlit secrets, if configured."""
    try:
        url = st.secrets.get("SUPABASE_URL") if hasattr(st, "secrets") else None
        key = st.secrets.get("SUPABASE_ANON_KEY") if hasattr(st, "secrets") else None
        if url and key:
            return SupabaseClient(url, key)
        return None
    except Exception:
        return None


# ------------------------------------------------------------------
# Persistence wrappers
# ------------------------------------------------------------------
def load_state_from_db():
    sb = get_supabase()
    if sb is None:
        return False, "Supabase not configured"

    try:
        wl_rows = sb.select("watchlist")
        st.session_state.watchlist = [r["ticker"] for r in wl_rows]
        st.session_state.notes = {r["ticker"]: r.get("note") or "" for r in wl_rows}
    except Exception as e:
        return False, f"Watchlist load failed: {e}"

    try:
        h_rows = sb.select("holdings")
        st.session_state.holdings = [
            {"id": r.get("id"), "ticker": r["ticker"], "shares": float(r["shares"]), "cost_basis": float(r["cost_basis"])}
            for r in h_rows
        ]
    except Exception as e:
        return False, f"Holdings load failed: {e}"

    return True, "Loaded from Supabase"


def save_watchlist_item(ticker: str, note: str = "") -> bool:
    sb = get_supabase()
    if sb is None:
        return False
    return sb.upsert("watchlist", {"ticker": ticker, "note": note}, on_conflict="ticker")


def delete_watchlist_item(ticker: str) -> bool:
    sb = get_supabase()
    if sb is None:
        return False
    return sb.delete("watchlist", "ticker", ticker)


def save_holding(holding: dict) -> bool:
    sb = get_supabase()
    if sb is None:
        return False
    payload = {
        "ticker": holding["ticker"],
        "shares": holding["shares"],
        "cost_basis": holding["cost_basis"],
    }
    try:
        r = requests.post(
            f"{sb.url}/rest/v1/holdings",
            headers=sb.headers,
            json=payload,
            timeout=10,
        )
        if r.status_code in (200, 201):
            data = r.json()
            if isinstance(data, list) and data:
                holding["id"] = data[0].get("id")
                return True
        return False
    except Exception:
        return False


def delete_holding(holding_id) -> bool:
    sb = get_supabase()
    if sb is None or holding_id is None:
        return False
    try:
        r = requests.delete(
            f"{sb.url}/rest/v1/holdings",
            headers=sb.headers,
            params={"id": f"eq.{holding_id}"},
            timeout=10,
        )
        return r.status_code in (200, 204)
    except Exception:
        return False


# ------------------------------------------------------------------
# Session state initialization
# ------------------------------------------------------------------
def init_session():
    if "initialized" in st.session_state:
        return

    st.session_state.initialized = True
    st.session_state.last_refresh = None
    st.session_state.storage_status = "unknown"

    sb = get_supabase()
    if sb is not None:
        ok, msg = load_state_from_db()
        if ok:
            st.session_state.storage_status = "connected"
            return
        else:
            st.session_state.storage_status = f"error: {msg}"

    if "watchlist" not in st.session_state:
        st.session_state.watchlist = ["HALO", "DLO", "KVYO", "BRZE", "MNTN", "TMDX", "ZETA", "CELH"]
    if "notes" not in st.session_state:
        st.session_state.notes = {}
    if "holdings" not in st.session_state:
        st.session_state.holdings = []
    if sb is None:
        st.session_state.storage_status = "session-only"


init_session()


# ------------------------------------------------------------------
# Data fetching
# ------------------------------------------------------------------
@st.cache_data(ttl=300)
def get_price_data(ticker: str) -> dict:
    try:
        t = yf.Ticker(ticker)
        info = t.info
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


@st.cache_data(ttl=3600)
def get_earnings_date(ticker: str) -> dict:
    try:
        t = yf.Ticker(ticker)
        cal = t.calendar
        if cal is None:
            return {"ticker": ticker, "next_earnings": None, "days_until": None}

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

        if isinstance(earnings_date, str):
            earnings_date = pd.to_datetime(earnings_date).date()
        elif hasattr(earnings_date, "date"):
            earnings_date = earnings_date.date()

        days_until = (earnings_date - datetime.now().date()).days
        return {"ticker": ticker, "next_earnings": earnings_date, "days_until": days_until}
    except Exception:
        return {"ticker": ticker, "next_earnings": None, "days_until": None}


@st.cache_data(ttl=3600)
def get_sec_cik(ticker: str) -> Optional[str]:
    try:
        url = "https://www.sec.gov/files/company_tickers.json"
        headers = {"User-Agent": "PortfolioMonitor research@example.com"}
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        for entry in data.values():
            if entry.get("ticker", "").upper() == ticker.upper():
                return str(entry["cik_str"]).zfill(10)
        return None
    except Exception:
        return None


@st.cache_data(ttl=1800)
def get_recent_filings(ticker: str, days: int = 30) -> list:
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
# Helpers
# ------------------------------------------------------------------
def format_pct(pct):
    if pct is None:
        return "—"
    cls = "pos" if pct > 0 else ("neg" if pct < 0 else "neutral")
    sign = "+" if pct > 0 else ""
    return f'<span class="{cls}">{sign}{pct:.2f}%</span>'


def format_money(val, decimals=2):
    if val is None:
        return "—"
    return f"${val:,.{decimals}f}"


def format_market_cap(mc):
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
# Sidebar
# ------------------------------------------------------------------
with st.sidebar:
    st.markdown("### Portfolio Monitor")

    if st.session_state.storage_status == "connected":
        st.markdown('<span class="storage-ok">● Supabase connected</span>', unsafe_allow_html=True)
    elif st.session_state.storage_status == "session-only":
        st.markdown('<span class="storage-fail">● Session-only (no Supabase)</span>', unsafe_allow_html=True)
    else:
        st.markdown(f'<span class="storage-fail">● {st.session_state.storage_status}</span>', unsafe_allow_html=True)

    st.caption("v2 — Supabase + yfinance + SEC EDGAR")

    st.divider()

    st.markdown("#### Watchlist")
    new_ticker = st.text_input("Add ticker (e.g. AAPL)", key="new_ticker_input").upper().strip()
    new_note = st.text_input("Note (optional)", key="new_note_input", max_chars=200,
                              placeholder="Why tracking? Thesis? Trigger?")

    col_add, col_clear = st.columns(2)
    with col_add:
        if st.button("Add", use_container_width=True):
            if new_ticker and new_ticker not in st.session_state.watchlist:
                st.session_state.watchlist.append(new_ticker)
                st.session_state.notes[new_ticker] = new_note
                save_watchlist_item(new_ticker, new_note)
                st.rerun()

    with col_clear:
        if st.button("Clear all", use_container_width=True):
            for t in list(st.session_state.watchlist):
                delete_watchlist_item(t)
            st.session_state.watchlist = []
            st.session_state.notes = {}
            st.rerun()

    if st.session_state.watchlist:
        ticker_to_remove = st.selectbox(
            "Remove ticker",
            options=[""] + sorted(st.session_state.watchlist),
            key="remove_ticker_select",
        )
        if ticker_to_remove and st.button("Remove", use_container_width=True):
            st.session_state.watchlist.remove(ticker_to_remove)
            st.session_state.notes.pop(ticker_to_remove, None)
            delete_watchlist_item(ticker_to_remove)
            st.rerun()

    st.caption(f"Tracking {len(st.session_state.watchlist)} tickers")

    st.divider()

    if st.button("🔄 Refresh data", use_container_width=True, type="primary"):
        st.cache_data.clear()
        st.session_state.last_refresh = datetime.now()
        st.rerun()

    if st.session_state.last_refresh:
        st.caption(f"Last refresh: {st.session_state.last_refresh.strftime('%H:%M:%S')}")
    else:
        st.caption("Cache: 5min prices, 30min filings, 1hr earnings")

    st.divider()

    with st.expander("💾 CSV backup"):
        watchlist_csv_lines = ["ticker,note"]
        for t in st.session_state.watchlist:
            note = (st.session_state.notes.get(t) or "").replace('"', '""').replace("\n", " ")
            watchlist_csv_lines.append(f'{t},"{note}"')
        watchlist_csv = "\n".join(watchlist_csv_lines)

        st.download_button(
            "Download watchlist",
            watchlist_csv,
            file_name=f"watchlist_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True,
        )

        if st.session_state.holdings:
            holdings_df = pd.DataFrame([
                {"ticker": h["ticker"], "shares": h["shares"], "cost_basis": h["cost_basis"]}
                for h in st.session_state.holdings
            ])
            st.download_button(
                "Download holdings",
                holdings_df.to_csv(index=False),
                file_name=f"holdings_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True,
            )

# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
st.title("Portfolio Monitor")

tab_watchlist, tab_portfolio, tab_earnings, tab_filings, tab_setup = st.tabs([
    "📋 Watchlist",
    "💼 Portfolio",
    "📅 Earnings",
    "📄 SEC Filings",
    "⚙️ Setup",
])

# Tab 1: Watchlist
with tab_watchlist:
    if not st.session_state.watchlist:
        st.info("No tickers in watchlist. Add one in the sidebar.")
    else:
        rows = []
        with st.spinner(f"Fetching prices for {len(st.session_state.watchlist)} tickers..."):
            for ticker in st.session_state.watchlist:
                data = get_price_data(ticker)
                rows.append(data)

        df = pd.DataFrame(rows)

        if not df.empty:
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

            display_rows = []
            for _, r in df.iterrows():
                note = st.session_state.notes.get(r["ticker"], "") or ""
                if r["price"] is None:
                    display_rows.append({
                        "Ticker": r["ticker"],
                        "Name": r.get("name", r["ticker"]) if isinstance(r.get("name"), str) else r["ticker"],
                        "Sector": r.get("sector") or "—",
                        "Price": "—",
                        "Change": "—",
                        "Market Cap": "—",
                        "Note": f'<span class="note-cell">{note}</span>' if note else "—",
                    })
                else:
                    display_rows.append({
                        "Ticker": r["ticker"],
                        "Name": r["name"][:35] if r["name"] else r["ticker"],
                        "Sector": r.get("sector") or "—",
                        "Price": format_money(r["price"]),
                        "Change": format_pct(r["change_pct"]),
                        "Market Cap": format_market_cap(r.get("market_cap")),
                        "Note": f'<span class="note-cell">{note}</span>' if note else "—",
                    })

            display_df = pd.DataFrame(display_rows)
            st.markdown(display_df.to_html(escape=False, index=False), unsafe_allow_html=True)

            errors = df[df["error"].notna() & (df["price"].isna())]
            if not errors.empty:
                with st.expander(f"⚠️ {len(errors)} ticker(s) had errors"):
                    for _, r in errors.iterrows():
                        st.text(f"{r['ticker']}: {r['error']}")

            st.markdown("### Edit notes")
            st.caption("Update your thesis or tracking reason. Saved automatically.")

            edit_ticker = st.selectbox(
                "Select ticker",
                options=sorted(st.session_state.watchlist),
                key="edit_note_ticker",
            )
            if edit_ticker:
                current_note = st.session_state.notes.get(edit_ticker, "") or ""
                new_note_text = st.text_area(
                    f"Note for {edit_ticker}",
                    value=current_note,
                    height=100,
                    key=f"note_edit_{edit_ticker}",
                    max_chars=500,
                )
                if st.button("💾 Save note", key=f"save_note_{edit_ticker}"):
                    st.session_state.notes[edit_ticker] = new_note_text
                    if save_watchlist_item(edit_ticker, new_note_text):
                        st.success(f"Saved note for {edit_ticker}")
                    else:
                        st.warning("Saved to session, but Supabase write failed")
                    time.sleep(0.5)
                    st.rerun()

# Tab 2: Portfolio
with tab_portfolio:
    st.markdown("### Holdings")
    if st.session_state.storage_status == "connected":
        st.caption("Auto-saved to Supabase.")
    else:
        st.caption("Session-only. Use sidebar CSV download to back up.")

    with st.expander("➕ Add new position", expanded=len(st.session_state.holdings) == 0):
        col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
        with col1:
            h_ticker = st.text_input("Ticker", key="h_ticker_input").upper().strip()
        with col2:
            h_shares = st.number_input("Shares", min_value=0.0, step=1.0, format="%.4f", key="h_shares_input")
        with col3:
            h_cost = st.number_input("Cost basis ($/share)", min_value=0.0, step=0.01, format="%.4f", key="h_cost_input")
        with col4:
            st.write("")
            st.write("")
            if st.button("Add position", use_container_width=True):
                if h_ticker and h_shares > 0 and h_cost > 0:
                    new_holding = {
                        "ticker": h_ticker,
                        "shares": h_shares,
                        "cost_basis": h_cost,
                        "id": None,
                    }
                    if save_holding(new_holding):
                        st.session_state.holdings.append(new_holding)
                        st.success(f"Added {h_shares} shares of {h_ticker}")
                    else:
                        st.session_state.holdings.append(new_holding)
                        st.warning("Added to session, but Supabase write failed")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("All fields required and must be positive")

    if not st.session_state.holdings:
        st.info("No holdings yet. Add a position above.")
    else:
        holdings_with_prices = []
        with st.spinner("Calculating P&L..."):
            for h in st.session_state.holdings:
                price_data = get_price_data(h["ticker"])
                current_price = price_data["price"] if price_data["price"] else 0
                cost_total = h["shares"] * h["cost_basis"]
                market_value = h["shares"] * current_price if current_price else 0
                unrealized_pnl = market_value - cost_total
                pnl_pct = (unrealized_pnl / cost_total * 100) if cost_total else 0
                day_change_dollar = h["shares"] * (current_price - price_data.get("prev_close", current_price)) if current_price else 0

                holdings_with_prices.append({
                    "id": h.get("id"),
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
                holding_to_remove = st.session_state.holdings[idx]
                if delete_holding(holding_to_remove.get("id")):
                    st.session_state.holdings.pop(idx)
                else:
                    st.session_state.holdings.pop(idx)
                    st.warning("Removed from session, but Supabase delete failed")
                st.rerun()

# Tab 3: Earnings
with tab_earnings:
    st.markdown("### Upcoming earnings")
    st.caption("Yahoo Finance dates can be stale. Verify before acting.")

    if not st.session_state.watchlist:
        st.info("No tickers in watchlist.")
    else:
        earnings_data = []
        with st.spinner("Fetching earnings dates..."):
            for ticker in st.session_state.watchlist:
                ed = get_earnings_date(ticker)
                earnings_data.append(ed)

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

# Tab 4: Filings
with tab_filings:
    st.markdown("### Recent SEC filings")
    st.caption("10-K, 10-Q, 8-K, DEF 14A, S-1, 20-F, 6-K, 13D/G filings.")

    if not st.session_state.watchlist:
        st.info("No tickers in watchlist.")
    else:
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
            all_filings.sort(key=lambda x: x["date"], reverse=True)

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

# Tab 5: Setup
with tab_setup:
    st.markdown("### Supabase setup")

    if st.session_state.storage_status == "connected":
        st.success("✅ Supabase is connected. Your data persists automatically.")
    else:
        st.warning(f"⚠️ Storage status: {st.session_state.storage_status}")

    st.markdown(
        """
#### One-time setup (10 minutes)

**1. Create a Supabase account** at [supabase.com](https://supabase.com) (free, no credit card).

**2. Create a new project.**
- Project name: anything (e.g. "portfolio-monitor")
- Database password: save this somewhere — you won't need it for the app, but Supabase requires it
- Region: closest to you (e.g. eu-central-1 for Europe / Greece)
- Wait ~2 minutes for the project to be ready.

**3. Create the tables.** In your Supabase project, go to **SQL Editor** (left sidebar), click "New query", paste this entire block, click "Run":

```sql
-- Watchlist table
CREATE TABLE IF NOT EXISTS watchlist (
    ticker TEXT PRIMARY KEY,
    note TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Holdings table
CREATE TABLE IF NOT EXISTS holdings (
    id BIGSERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    shares NUMERIC NOT NULL,
    cost_basis NUMERIC NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Disable RLS for simplicity (this is a single-user app)
ALTER TABLE watchlist DISABLE ROW LEVEL SECURITY;
ALTER TABLE holdings DISABLE ROW LEVEL SECURITY;
```

You should see "Success. No rows returned." in the bottom panel.

**4. Get your credentials.** In Supabase, go to **Project Settings** (gear icon at bottom left) → **API** (or **Data API** in newer Supabase UIs).
- Copy the **Project URL** (looks like `https://abcdefg.supabase.co`)
- Copy the **`anon` public** key (a long string starting with `eyJ...`)

**5. Add credentials to Streamlit Cloud.** Go to your Streamlit Community Cloud dashboard, click your app, click **Settings** → **Secrets**. Paste this in (replacing the placeholders):

```toml
SUPABASE_URL = "https://YOUR-PROJECT-ID.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIs..."
```

Click "Save". Streamlit will redeploy automatically (~1 min).

**6. Reload the app.** This Setup tab should now show "✅ Supabase is connected".

---

#### Migrating v1 watchlist to Supabase

If you've been using v1 and want to import your existing watchlist, paste tickers directly via Supabase SQL Editor:

```sql
INSERT INTO watchlist (ticker, note) VALUES
    ('HALO', 'Royalty platform, 23-30% growth'),
    ('DLO', 'EM payments, EM volatility risk'),
    ('KVYO', 'B2C SaaS, Shopify concentration')
ON CONFLICT (ticker) DO UPDATE SET note = EXCLUDED.note;
```

Replace with your own tickers and notes.

---

#### Why this storage approach?

- **Free forever** for hobby-scale apps (Supabase free tier: 500MB DB, 2GB bandwidth/month — way more than you need).
- **No SDK install** required (the app uses raw HTTPS calls).
- **Browser-only** — manage everything from Supabase's web UI.
- **Portable** — if you ever leave Supabase, you can export your data as CSV in 2 clicks.

#### Privacy note

Your Supabase URL and anon key are stored as Streamlit secrets — not in your public GitHub repo. Without those secrets, no one else can read or write to your tables.

The `anon` key has full table access (since RLS is off). For a single-user app, this is fine. If you ever share access, we'd add proper authentication.
        """
    )

# Footer
st.divider()
st.caption(
    "Data: Yahoo Finance (prices, earnings) and SEC EDGAR (filings). "
    "Storage: Supabase free tier. "
    "Prices delayed up to 15 min. Not investment advice."
)
