import streamlit as st
import requests
import pandas as pd 
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
from datetime import date



api_key = 'beUiETWAQ7Ert13VnAd7qkiEqjT1GrFC'
base_url = 'https://financialmodelingprep.com'
ticker = st.text_input("Enter Ticker")

# Default date range (you can tweak this)
default_from = date(2010, 11, 17)
default_to = date.today()

col1, col2 = st.columns(2)
with col1:
    from_date = st.date_input("From date", value=default_from)
with col2:
    to_date = st.date_input("To date", value=default_to)


#----------------------------#
    # DECLARING FUNCTIONS #
#----------------------------#

def divider():
    st.markdown(
        "<hr style='border: 0; border-top: 1px solid #ddd; margin: 20px 0;'>",
        unsafe_allow_html=True
    )


@st.cache_data(ttl=10000)
def fetch_histo_quotes(ticker: str, from_date: date, to_date: date):
    # Convert date objects to YYYY-MM-DD strings
    from_str = from_date.isoformat()
    to_str = to_date.isoformat()

    historical_quotes_url = (
        f"{base_url}/stable/historical-price-eod/full"
        f"?symbol={ticker}&from={from_str}&to={to_str}&apikey={api_key}"
    )

    resp = requests.get(historical_quotes_url, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return data

#----------------------------#
    # EXECUTING FUNCTIONS #
#----------------------------#

All_Quotes = fetch_histo_quotes(ticker, from_date, to_date)
Ticker_Price_log = pd.DataFrame(All_Quotes)
Ticker_Price_log["date"] = pd.to_datetime(Ticker_Price_log["date"])
Ticker_Price_log = Ticker_Price_log.sort_values("date")
Ticker_Price_log = Ticker_Price_log.set_index("date")

if not ticker:
    st.info("Please enter a ticker.")
else:
    if from_date > to_date:
        st.error("From date must be earlier than To date.")
    else:
        all_quotes = fetch_histo_quotes(ticker, from_date, to_date)
        # Now you can turn this into a DataFrame, etc.
        # Ticker_Price_log = pd.DataFrame(all_quotes)

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
        density=False,
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

# ------------------------------------------------
# 📊 Volatility Profile
# ------------------------------------------------

st.subheader("🔥 Monthly Volatility Profile — Return Frequency Heatmap")

if returns.empty:
    st.warning("Not enough data to build a monthly heatmap.")
else:
    # Convert returns to percent
    returns_pct = returns * 100

    # Define return buckets
    bins_pct = [-5, -4, -3, -2, -1, -0.5, 0, 0.5, 1, 2, 3, 4, 5]
    labels = [
        "< -5%",
        "-5% to -4%",
        "-4% to -3%",
        "-3% to -2%",
        "-2% to -1%",
        "-1% to -0.5%",
        "-0.5% to 0%",
        "0% to 0.5%",
        "0.5% to 1%",
        "1% to 2%",
        "2% to 3%",
        "3% to 4%",
        "> 4%",
    ]

    # Bucket each return
    buckets = pd.cut(
        returns_pct,
        bins=bins_pct + [999],
        labels=labels,
        right=True
    )

    # Build monthly index
    df_monthly = pd.DataFrame({
        "year": returns.index.year,
        "month": returns.index.month,
        "bucket": buckets
    })

    # Create YYYY-MM labels
    df_monthly["period"] = df_monthly["year"].astype(str) + "-" + df_monthly["month"].astype(str).str.zfill(2)

    # Compute frequency table by month
    heat_table_month = (
        df_monthly
        .groupby(["period", "bucket"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=labels)
    )

    # Plot heatmap
    fig, ax = plt.subplots(figsize=(14, 10))

    im = ax.imshow(heat_table_month.values, aspect="auto", cmap="viridis")

    # Y-axis = months
    ax.set_yticks(np.arange(len(heat_table_month.index)))
    ax.set_yticklabels(heat_table_month.index)

    # X-axis = buckets
    ax.set_xticks(np.arange(len(heat_table_month.columns)))
    ax.set_xticklabels(heat_table_month.columns, rotation=45, ha="right")

    ax.set_title(f"Monthly Return-Frequency Heatmap for {ticker}", fontsize=16, pad=15)
    ax.set_xlabel("Daily Return Bucket (%)")
    ax.set_ylabel("Month")

    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Number of days")

    st.pyplot(fig)

    # Show table under it
    st.markdown("#### Underlying Monthly Frequency Table")
    st.dataframe(heat_table_month, use_container_width=True)

# -------------------------------------------
# 📊 Quant Summary Box (Dynamic, Professional)
# -------------------------------------------

st.markdown("Summary")

# Annualize volatility (typical for daily data)
trading_days = 252
annual_vol = sigma * np.sqrt(trading_days)
annual_mean = (1 + mu) ** trading_days - 1

# Downside tail probability
p_tail_2 = (returns < -0.02).mean() * 100      # probability of a daily loss < -2%
p_tail_1 = (returns < -0.01).mean() * 100      # probability of a daily loss < -1%
p_big_up  = (returns > 0.02).mean() * 100      # probability of a daily gain > +2%

summary_text = f"""
### **Return Behavior**
- Average daily return is **{mu*100:.3f}%**, which annualizes to **{annual_mean*100:.2f}%**.
- Median return is **{median*100:.3f}%**, showing that typical days are {'stronger' if median>mu else 'weaker'} than the mean.
- Daily volatility is **{sigma*100:.3f}%**, which annualizes to **{annual_vol*100:.2f}%**.
- This places **{ticker}** in the category of {"high" if annual_vol>0.25 else "moderate" if annual_vol>0.10 else "low"} volatility assets.

### **Tail Risk**
- Probability of a daily drop worse than **–2%**: **{p_tail_2:.2f}%**
- Probability of a daily drop worse than **–1%**: **{p_tail_1:.2f}%**
- Probability of a daily gain above **+2%**: **{p_big_up:.2f}%**

{"This distribution has *fat negative tails*, meaning large downside shocks occur more frequently than a normal model would predict."
 if kurt_val > 0 and skew_val < 0 else
"This distribution is relatively symmetric, with limited extreme downside tail events."
 if kurt_val < 0.5 and abs(skew_val) < 0.1 else
"This asset shows occasional extreme moves, but not pathologically so."
}

### **Skewness & Crash Risk**
- Skewness is **{skew_val:.3f}**, indicating:
  - {"Upside spikes dominate (positive skew)." if skew_val>0 else
     "Downside crashes dominate (negative skew)." if skew_val<0 else
     "Returns are symmetric."}

- Kurtosis is **{kurt_val:.3f}**  
  - Values > 0 mean **fat tails** → extreme moves happen more often than a normal model suggests.
  - Values < 0 mean light tails → fewer extreme moves.

- **Return Quality:** {"Strong" if mu>0 else "Weak"}
- **Volatility:** {"High" if annual_vol>0.25 else "Moderate" if annual_vol>0.10 else "Low"}
- **Tail Risk:** {"Elevated" if kurt_val>0 else "Normal"}
- **Crash Profile:** {"Crash-prone (negative skew)" if skew_val<0 else "Upside biased (positive skew)"}

Together, these metrics suggest that **{ticker}** behaves like a(n) **{"trend-following, high-volatility asset" if annual_vol>0.2 else "stable, low-volatility asset"}** with **{"fat-tailed downside risk" if skew_val<0 and kurt_val>0 else "balanced risk distribution"}**.
"""

st.markdown(summary_text)
