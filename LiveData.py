import streamlit as st
from streamlit_autorefresh import st_autorefresh
import yfinance as yf
from datetime import datetime, timezone

st.set_page_config(page_title="Live Bitcoin Price", page_icon="💰")

st.title("💰 Live Bitcoin Price (BTC-USD)")
refresh_secs = st.sidebar.slider("Auto-refresh (seconds)", 10, 120, 30, 5)

# 🔁 Auto-refresh every N seconds (milliseconds)
st_autorefresh(interval=refresh_secs * 1000, key="btc_refresh")

# Fetch last 1D of 1-minute candles
try:
    data = yf.Ticker("BTC-USD").history(period="1d", interval="1m")
    if data.empty:
        st.warning("No data returned (temporary data issue).")
    else:
        price = float(data["Close"].iloc[-1])
        ts = data.index[-1].to_pydatetime().astimezone(timezone.utc)
        st.metric("BTC Price", f"${price:,.2f}")
        st.caption(f"Last update (UTC): {ts:%Y-%m-%d %H:%M:%S}")
        st.line_chart(data["Close"].rename("BTC-USD Close"))
except Exception as e:
    st.error("Couldn't fetch price right now. Try again shortly.")
    # Uncomment to see the exact error locally:
    # st.exception(e)
