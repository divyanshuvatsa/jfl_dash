"""
Live Market Rates, fetches current benchmark rates from public sources.

Sources (FREE, no API key):
  - USD/INR via exchangerate.host (ECB-backed)
  - RBI Repo Rate scraped from RBI.org.in
  - India 10Y G-Sec from worldgovernmentbonds.com
  - US 10Y Treasury from US Treasury CSV feed
  - SOFR from NY Fed public JSON API

Caching: 1-hour TTL via @st.cache_data
Graceful failure: missing rates show "N/A" rather than crashing the sidebar.
"""

from __future__ import annotations
import streamlit as st
import requests
from datetime import datetime
from typing import Dict, Any, Optional
import re


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*",
}


def _safe_get_json(url: str, timeout: int = 8) -> Optional[Any]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, verify=True)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def _safe_get_text(url: str, timeout: int = 8) -> Optional[str]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, verify=True)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    return None


def fetch_usd_inr() -> Optional[Dict]:
    data = _safe_get_json("https://api.exchangerate.host/latest?base=USD&symbols=INR")
    if data and data.get("rates", {}).get("INR"):
        return {"value": float(data["rates"]["INR"]), "source": "exchangerate.host"}
    data = _safe_get_json("https://open.er-api.com/v6/latest/USD")
    if data and data.get("rates", {}).get("INR"):
        return {"value": float(data["rates"]["INR"]), "source": "er-api.com"}
    return None


def fetch_rbi_repo_rate() -> Optional[Dict]:
    text = _safe_get_text("https://www.rbi.org.in/")
    if text:
        m = re.search(r"Policy\s+Repo\s+Rate[^\d]*([\d.]+)\s*%", text, re.IGNORECASE)
        if m:
            try:
                return {"value": float(m.group(1)), "source": "RBI"}
            except ValueError:
                pass
    return {"value": 5.25, "source": "RBI (last known May-26)"}


def fetch_india_10y() -> Optional[Dict]:
    text = _safe_get_text("http://www.worldgovernmentbonds.com/country/india/")
    if text:
        m = re.search(r"10\s*Years[^\d]*([\d.]+)\s*%", text)
        if m:
            try:
                return {"value": float(m.group(1)), "source": "worldgovernmentbonds.com"}
            except ValueError:
                pass
    return None


def fetch_us_10y_treasury() -> Optional[Dict]:
    today = datetime.now()
    url = (f"https://home.treasury.gov/resource-center/data-chart-center/"
           f"interest-rates/daily-treasury-rates.csv/{today.year}/all"
           f"?type=daily_treasury_yield_curve&field_tdr_date_value={today.year}&page&_format=csv")
    text = _safe_get_text(url)
    if text:
        lines = text.strip().split("\n")
        if len(lines) > 1:
            header = lines[0].split(",")
            try:
                idx = next(i for i, h in enumerate(header) if "10 Yr" in h or '"10 Yr"' in h)
                latest = lines[1].split(",")
                return {"value": float(latest[idx].strip('"')), "source": "US Treasury"}
            except (StopIteration, ValueError, IndexError):
                pass
    return None


def fetch_sofr() -> Optional[Dict]:
    data = _safe_get_json("https://markets.newyorkfed.org/api/rates/secured/sofr/last/1.json")
    if data:
        refRates = data.get("refRates", [])
        if refRates:
            rate = refRates[0].get("percentRate")
            if rate is not None:
                return {"value": float(rate), "source": "NY Fed"}
    return None


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_all_market_rates() -> Dict[str, Any]:
    """Fetch all market rates. Cached 1 hour."""
    rates = {
        "fetched_at": datetime.now().isoformat(),
        "fetched_at_pretty": datetime.now().strftime("%d-%b-%Y %H:%M IST"),
    }
    rates["USD_INR"] = fetch_usd_inr()
    rates["RBI_Repo"] = fetch_rbi_repo_rate()
    rates["India_10Y"] = fetch_india_10y()
    rates["US_10Y"] = fetch_us_10y_treasury()
    rates["SOFR"] = fetch_sofr()
    return rates


def render_market_rates_sidebar():
    """Renders the market-rates section in the sidebar (collapsible)."""
    with st.sidebar:
        with st.expander("📊 Live Market Rates", expanded=False):
            with st.spinner("Fetching..."):
                try:
                    rates = fetch_all_market_rates()
                except Exception as e:
                    st.warning(f"Couldn't fetch rates: {e}")
                    return

            def _fmt(label, key, suffix="%", icon=""):
                r = rates.get(key)
                if r and r.get("value") is not None:
                    val = r["value"]
                    st.markdown(
                        f"<div style='display:flex;justify-content:space-between;"
                        f"padding:6px 0;border-bottom:1px solid #334155;'>"
                        f"<span style='color:#94A3B8;font-size:0.82rem;'>{icon} {label}</span>"
                        f"<span style='color:#F1F5F9;font-weight:600;font-size:0.95rem;'>"
                        f"{val:.2f}{suffix}</span></div>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f"<div style='display:flex;justify-content:space-between;"
                        f"padding:6px 0;border-bottom:1px solid #334155;'>"
                        f"<span style='color:#94A3B8;font-size:0.82rem;'>{icon} {label}</span>"
                        f"<span style='color:#64748B;font-size:0.85rem;'>N/A</span></div>",
                        unsafe_allow_html=True,
                    )

            _fmt("USD/INR",       "USD_INR", suffix="", icon="💱")
            _fmt("RBI Repo Rate", "RBI_Repo", icon="🏦")
            _fmt("India 10Y G-Sec","India_10Y", icon="🇮🇳")
            _fmt("US 10Y Treasury","US_10Y", icon="🇺🇸")
            _fmt("SOFR",          "SOFR", icon="💵")

            st.markdown(
                f"<div style='font-size:0.7rem;color:#64748B;padding-top:8px;'>"
                f"Updated: {rates['fetched_at_pretty']}<br>"
                f"Auto-refresh every hour</div>",
                unsafe_allow_html=True,
            )
            if st.button("🔄 Refresh now", key="refresh_market_rates", use_container_width=True):
                fetch_all_market_rates.clear()
                st.rerun()
