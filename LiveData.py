import streamlit as st, yfinance as yf
from datetime import datetime, timezone

st.title("💰 Live Bitcoin Price (BTC-USD)")
if st.button("Refresh"):
    st.rerun()

data = yf.Ticker("BTC-USD").history(period="1d", interval="1m")
price = float(data["Close"].iloc[-1])
ts = data.index[-1].to_pydatetime().astimezone(timezone.utc)
st.metric("BTC Price", f"${price:,.2f}")
st.caption(f"Last update (UTC): {ts:%Y-%m-%d %H:%M:%S}")
st.line_chart(data["Close"].rename("BTC-USD Close"))
