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

def divider():
    st.markdown(
        "<hr style='border: 0; border-top: 1px solid #ddd; margin: 20px 0;'>",
        unsafe_allow_html=True
    )

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

divider()

#----------------------------#
    # BELL CURVE #
#----------------------------#
st.subheader("📈 Bell Curve of Daily Returns (Clean & Readable)")

if returns.empty:
    st.warning("Not enough data to compute returns.")
else:
    fig, ax = plt.subplots(figsize=(10, 6))

    # --- Stats ---
    mu = returns.mean()
    sigma = returns.std()
    median = returns.median()
    skew_val = returns.skew()
    kurt_val = returns.kurt()

    # --- Histogram (soft, modern style) ---
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

    # --- SMOOTH KDE-LIKE CURVE (no seaborn needed) ---
    from scipy.stats import gaussian_kde
    kde = gaussian_kde(returns)
    x = np.linspace(returns.min(), returns.max(), 400)
    ax.plot(
        x,
        kde(x),
        color="#9013FE",
        linewidth=2.5,
        label="KDE (smooth curve)"
    )

    # --- Normal PDF ---
    normal_pdf = (
        1 / (sigma * np.sqrt(2 * np.pi))
        * np.exp(-0.5 * ((x - mu) / sigma) ** 2)
    )
    ax.plot(
        x,
        normal_pdf,
        color="#D0021B",
        linewidth=2.3,
        linestyle="--",
        label="Normal fit"
    )

    # --- Mean line ---
    ax.axvline(
        mu,
        color="#417505",
        linestyle="--",
        linewidth=2,
        label=f"Mean ({mu*100:.2f}%)"
    )

    # --- Median line ---
    ax.axvline(
        median,
        color="#F5A623",
        linestyle=":",
        linewidth=2,
        label=f"Median ({median*100:.2f}%)"
    )

    # --- Shaded ±1σ region ---
    ax.fill_between(
        x,
        0,
        normal_pdf,
        where=((x >= mu - sigma) & (x <= mu + sigma)),
        color="#50E3C2",
        alpha=0.25,
        label="±1σ range"
    )

    # --- Title & labels ---
    ax.set_title(
        f"Daily Return Distribution for {ticker}",
        fontsize=16,
        fontweight="bold",
        pad=20
    )
    ax.set_xlabel("Daily return (%)", fontsize=13)
    ax.set_ylabel("Density", fontsize=13)

    # --- Format x-axis as %
    ax.xaxis.set_major_formatter(mtick.PercentFormatter(1.0))

    # --- Light grid ---
    ax.grid(alpha=0.25, linestyle="--")

    # --- Stats box ---
    stats_text = (
        f"Mean: {mu*100:.3f}%\n"
        f"Median: {median*100:.3f}%\n"
        f"Std Dev: {sigma*100:.3f}%\n"
        f"Skew: {skew_val:.3f}\n"
        f"Kurtosis: {kurt_val:.3f}"
    )

    ax.text(
        0.98, 0.95,
        stats_text,
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
        fontsize=10
    )

    st.pyplot(fig)

# -------------------------------------------
# 📘 Explanation of the Bell Curve (Dynamic)
# -------------------------------------------

st.markdown("### 📘 Interpretation of the Bell Curve")

explanation = f"""
The chart above shows the **distribution of daily returns** for **{ticker}**, based on
its historical price data.

Here’s what each component means:

### **🔹 1. Histogram (blue bars)**
This represents how often certain daily returns occurred.

- Taller bars = that return range occurred more often  
- Wider spread = more volatility  
- Narrow spread = more stable price movements  

This histogram is normalized into a **probability density**, meaning the total area = 1.

---

### **🔹 2. KDE Curve (purple smooth line)**
This is a smoothed estimate of the return distribution.

It helps reveal the **true shape** of the distribution:
- Fat tails
- Skewness (asymmetry)
- Sharp or wide peaks

KDE is often preferred by quants because it doesn’t assume normality.

---

### **🔹 3. Normal Distribution Curve (red dashed line)**
This curve represents what the returns **would look like** *if* they were perfectly normal
(bell-shaped) with the same mean and standard deviation.

Comparing the blue histogram and purple KDE curve to the red normal curve shows:
- Whether volatility is higher than expected  
- Whether extreme events occur more often (fat tails)  
- Whether returns are symmetric or skewed  

---

### **🔹 4. Mean Line (green dashed) — {mu*100:.3f}%**
This is the **average daily return**.

A positive mean indicates long-term upward drift.
A negative mean indicates long-term decay.

---

### **🔹 5. Median Line (orange dotted) — {median*100:.3f}%**
The middle value of all daily returns.

If mean ≠ median, the distribution is skewed.

---

### **🔹 6. ±1σ Region (mint shaded) — ±{sigma*100:.3f}%**
This shows the range in which **68% of daily returns would fall** *if* returns were normal.

Comparing this shaded region to actual data helps you understand:
- Whether gold/HHIS has fatter tails  
- Whether risk is higher than normal  
- Whether volatility is unusual  

---

### **🔹 7. Skewness — {skew_val:.3f}**
- Positive skew → big upside spikes
- Negative skew → big downside crashes  
- Near zero → symmetric distribution  

Most financial assets are **negatively skewed** (crashes are worse than euphoria).

---

### **🔹 8. Kurtosis — {kurt_val:.3f}**
- Above 0 = **fat tails** (extreme events more likely than normal distribution)
- Below 0 = light tails  
- Exactly 0 = perfect normal distribution  

Fat tails are common in:
- equities  
- commodities  
- crypto  
- FX  

and are important for risk management.

---

### **📊 Summary**
This bell curve lets you quickly see whether **{ticker}** behaves normally, trends,
crashes often, or has unusual volatility patterns.  
It’s a core quant tool for understanding an asset’s risk profile.
"""

st.markdown(explanation)
