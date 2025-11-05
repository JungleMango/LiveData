import json
from pathlib import Path
from typing import Dict, List

import pandas as pd
import yfinance as yf
import altair as alt
import streamlit as st
from urllib.parse import quote, unquote

st.set_page_config(
    page_title="Multi-Portfolio Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

import streamlit as st

def colored_header_bg(title, bg_color, text_color="white", font_size=26):
    st.markdown(
        f"""
        <div style="
            background-color: {bg_color};
            color: {text_color};
            padding: 10px;
            border-radius: 8px;
            font-size: {font_size}px;
            font-weight: bold;
            text-align: left;">
            {title}
        </div>
        """,
        unsafe_allow_html=True
    )



# ---------- 4) Watchlist ----------
colored_header_bg("👀 Watchlist", "#8A2BE2", "white", 26)
watch_edited = st.data_editor(
    st.session_state["watchlist"],
    num_rows="dynamic",
    use_container_width=True,
    key="watchlist_editor",
    column_config={
        "Ticker": st.column_config.TextColumn(help="Any Yahoo Finance symbol, e.g., MSFT, ETH-USD, XAUUSD=X"),
    },
)
st.session_state["watchlist"] = watch_edited

watch = st.session_state["watchlist"].copy()
watch["Ticker"] = watch["Ticker"].astype(str).str.upper().str.strip()
watch["Live Price"] = watch["Ticker"].map(prices)

@st.cache_data(ttl=60)
def day_change(tickers: List[str]) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame(columns=["Ticker", "Daily Change %"])
    try:
        df = yf.download(tickers=tickers, period="5d", interval="1d", group_by="ticker", progress=False, threads=True)
        rows = []
        if isinstance(df.columns, pd.MultiIndex):
            for t in tickers:
                try:
                    d = df[t].dropna()
                    if len(d) >= 2:
                        prev_close = float(d["Close"].iloc[-2])
                        last_close = float(d["Close"].iloc[-1])
                        rows.append({"Ticker": t, "Daily Change %": round((last_close/prev_close - 1)*100, 2)})
                except Exception:
                    pass
        else:
            d = df.dropna()
            if len(d) >= 2:
                prev_close = float(d["Close"].iloc[-2])
                last_close = float(d["Close"].iloc[-1])
                rows.append({"Ticker": tickers[0], "Daily Change %": round((last_close/prev_close - 1)*100, 2)})
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame(columns=["Ticker", "Daily Change %"])

wl_changes = day_change([t for t in watch["Ticker"] if t])
watch = watch.merge(wl_changes, on="Ticker", how="left")

st.dataframe(
    watch.style.format({"Live Price": "${:,.4f}", "Daily Change %": "{:,.2f}%"}),
    use_container_width=True,
)
