import streamlit as st
import requests
import pandas as pd 
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np



api_key = 'beUiETWAQ7Ert13VnAd7qkiEqjT1GrFC'
base_url = 'https://financialmodelingprep.com'
data_type = 'income-statement'
ticker = st.text_input("Enter Ticker")
years = '120'
time = 'quarter'

#----------------------------#
    # DECLARING FUNCTIONS #
#----------------------------#

@st.cache_data(ttl=10000)
def fetch_histo_quotes(ticker):
    Historical_quotes_url = f'{base_url}/stable/historical-price-eod/full?symbol={ticker}&from=2010-11-17&to=2025-11-17&apikey={api_key}'
    All_quotes = requests.get(Historical_quotes_url)
    return All_quotes.json()

#----------------------------#
    # EXECUTING FUNCTIONS #
#----------------------------#

All_Quotes = fetch_histo_quotes(ticker)
Ticker_Price_log = pd.DataFrame(All_Quotes)
Ticker_Price_log["date"] = pd.to_datetime(Ticker_Price_log["date"])
Ticker_Price_log = Ticker_Price_log.sort_values("date")
price_col = "close"
Ticker_Price_log["Return"] = Ticker_Price_log[price_col].pct_change()
returns = Ticker_Price_log["Return"].dropna()
returns_pct = returns * 100


st.dataframe(Ticker_Price_log, hide_index=True)

#----------------------------#
    # BELL CURVE #
#----------------------------#

st.subheader("📈 Bell Curve of Daily Returns")

if returns.empty:
    st.warning("Not enough data to compute returns.")
else:
    fig, ax = plt.subplots()

    # Histogram of returns (this is your bell curve)
    # density=True → area under all bars = 1 (probability density)
    n, bins, patches = ax.hist(returns, bins=50, density=True)

    # Basic stats
    mu = returns.mean()        # mean (decimal)
    sigma = returns.std()      # standard deviation (decimal)
    median = returns.median()  # median (decimal)

    # Normal distribution overlay with same mean & std
    x = np.linspace(returns.min(), returns.max(), 400)
    normal_pdf = (
        1 / (sigma * np.sqrt(2 * np.pi))
        * np.exp(-0.5 * ((x - mu) / sigma) ** 2)
    )
    ax.plot(x, normal_pdf, linewidth=2, label="Normal PDF")

    # Vertical lines: mean & median
    ax.axvline(mu, linestyle="--", linewidth=2, label=f"Mean ({mu*100:.2f}%)")
    ax.axvline(median, linestyle=":", linewidth=2, label=f"Median ({median*100:.2f}%)")

    # Shade ±1 standard deviation region under the normal curve
    ax.fill_between(
        x,
        0,
        normal_pdf,
        where=(x >= mu - sigma) & (x <= mu + sigma),
        alpha=0.2,
        label="±1σ region",
    )

    # Labels & formatting
    ax.set_title(f"Distribution of Daily Returns — {ticker}")
    ax.set_xlabel("Daily return")
    ax.set_ylabel("Density")

    # Show x-axis as percentages (0.01 → 1%)
    ax.xaxis.set_major_formatter(mtick.PercentFormatter(1.0))

    ax.legend()

    st.pyplot(fig)
