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
st.subheader("📈 Bell Curve of Daily Returns (Quant Optimized)")

if returns.empty:
    st.warning("Not enough data to compute returns.")
else:
    import seaborn as sns
    sns.set_style("whitegrid")

    fig, ax = plt.subplots(figsize=(10, 6))

    # --- Stats ---
    mu = returns.mean()
    sigma = returns.std()
    median = returns.median()
    skew_val = returns.skew()
    kurt_val = returns.kurt()

    # --- Histogram ---
    ax.hist(
        returns,
        bins=35,
        density=True,
        color="#4A90E2",
        alpha=0.35,
        edgecolor="white",
        linewidth=0.7,
        label="Histogram"
    )

    # --- KDE Smooth Curve ---
    sns.kdeplot(
        returns,
        ax=ax,
        color="#9013FE",
        linewidth=2.5,
        label="KDE (smooth estimate)"
    )

    # --- Normal Curve ---
    x = np.linspace(returns.min(), returns.max(), 400)
    normal_pdf = (
        1 / (sigma * np.sqrt(2 * np.pi))
        * np.exp(-0.5 * ((x - mu) / sigma) ** 2)
    )
    ax.plot(
        x,
        normal_pdf,
        color="#D0021B",
        linewidth=2.5,
        linestyle="--",
        label="Normal fit"
    )

    # --- Mean Line ---
    ax.axvline(
        mu,
        color="#417505",
        linestyle="--",
        linewidth=2,
        label=f"Mean ({mu*100:.2f}%)"
    )

    # --- Median Line ---
    ax.axvline(
        median,
        color="#F5A623",
        linestyle=":",
        linewidth=2,
        label=f"Median ({median*100:.2f}%)"
    )

    # --- ±1σ Shaded Region ---
    ax.fill_between(
        x,
        0,
        normal_pdf,
        where=((x >= mu - sigma) & (x <= mu + sigma)),
        color="#50E3C2",
        alpha=0.25,
        label="±1σ range"
    )

    # --- Title ---
    ax.set_title(
        f"Distribution of Daily Returns for {ticker}",
        fontsize=17,
        fontweight="bold",
        pad=20
    )

    # --- Axis Labels ---
    ax.set_xlabel("Daily Return (%)", fontsize=13)
    ax.set_ylabel("Density", fontsize=13)

    # --- Format X axis as percent ---
    ax.xaxis.set_major_formatter(mtick.PercentFormatter(1.0))

    # --- Stats Box Inside Chart ---
    textstr = (
        f"Mean: {mu*100:.3f}%\n"
        f"Median: {median*100:.3f}%\n"
        f"Std Dev (σ): {sigma*100:.3f}%\n"
        f"Skew: {skew_val:.3f}\n"
        f"Kurtosis: {kurt_val:.3f}"
    )

    ax.text(
        0.98, 0.95,
        textstr,
        transform=ax.transAxes,
        fontsize=11,
        verticalalignment="top",
        horizontalalignment="right",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8)
    )

    # --- Legend outside ---
    ax.legend(
        bbox_to_anchor=(1.02, 1),
        loc="upper left",
        borderaxespad=0,
        fontsize=10
    )

    # Render
    st.pyplot(fig)
