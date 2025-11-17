import streamlit as st
import requests
import pandas as pd 
from datetime import datetime
import numpy as np
import matplotlib.pyplot as plt


#----------------------------#
    # DECLARING FUNCTIONS #
#----------------------------#

@st.cache_data(ttl=15)
def fetch_live_gold():
    Live_Gold_Url = 'https://financialmodelingprep.com/stable/quote?symbol=XAUUSD&apikey=beUiETWAQ7Ert13VnAd7qkiEqjT1GrFC'
    Gold_Price = requests.get(Live_Gold_Url)
    return Gold_Price.json()

@st.cache_data(ttl=10000)
def fetch_histo_quotes():
    Historical_quotes_url = 'https://financialmodelingprep.com/stable/historical-price-eod/full?symbol=XAUUSD&from=2010-11-17&to=2025-11-17&apikey=beUiETWAQ7Ert13VnAd7qkiEqjT1GrFC'
    All_quotes = requests.get(Historical_quotes_url)
    return All_quotes.json()

def divider():
    st.markdown(
        "<hr style='border: 0; border-top: 1px solid #ddd; margin: 20px 0;'>",
        unsafe_allow_html=True
    )
#----------------------------#
    # EXECUTING FUNCTIONS #
#----------------------------#

Gold_info = fetch_live_gold()
Gold_Price = Gold_info[0]["price"]
P_Change = Gold_info[0]["changePercentage"]
P_Change_percent = f"{P_Change :.2f}%"

timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


#----------------------------#
    # TABLES #
#----------------------------#

Gold_History_Table = pd.DataFrame(fetch_histo_quotes())

Gold_History_Table["date"] = pd.to_datetime(Gold_History_Table["date"])
Gold_History_Table = Gold_History_Table.sort_values("date").set_index("date")

# Rename close → price for convenience
Gold_History_Table = Gold_History_Table.rename(columns={"close": "price"})

# Ensure numeric
numeric_cols = ["open", "high", "low", "price", "volume", "change", "changePercent", "vwap"]
for col in numeric_cols:
        if col in Gold_History_Table.columns:
            Gold_History_Table[col] = pd.to_numeric(Gold_History_Table[col], errors="coerce")

Gold_History_Table = Gold_History_Table.dropna(subset=["price"])
Gold_History_Table = Gold_History_Table[~Gold_History_Table.index.duplicated(keep="last")]

# -----------------------------------------
# Quant transforms
# -----------------------------------------

trading_days = 252

# Returns: from price
Gold_History_Table["ret"] = Gold_History_Table["price"].pct_change()

# API-provided changePercent (your sample shows it as decimal, e.g. -0.02488 ≈ -2.49%)
if "changePercent" in Gold_History_Table.columns:
    Gold_History_Table["ret_api"] = Gold_History_Table["changePercent"]
else:
    Gold_History_Table["ret_api"] = np.nan

Gold_History_Table["log_ret"] = np.log(Gold_History_Table["price"]).diff()

# Cumulative performance
Gold_History_Table["cum_growth"] = (1 + Gold_History_Table["ret"].fillna(0)).cumprod()
Gold_History_Table["cum_index"] = 100 * Gold_History_Table["cum_growth"] / Gold_History_Table["cum_growth"].iloc[0]

# Drawdown
Gold_History_Table["running_max"] = Gold_History_Table["cum_index"].cummax()
Gold_History_Table["drawdown"] = Gold_History_Table["cum_index"] / Gold_History_Table["running_max"] - 1

# Rolling volatility
Gold_History_Table["vol_30d"] = Gold_History_Table["ret"].rolling(30).std() * np.sqrt(trading_days)
Gold_History_Table["vol_90d"] = Gold_History_Table["ret"].rolling(90).std() * np.sqrt(trading_days)

# Monthly & DOW helpers
Gold_History_Table["year"] = Gold_History_Table.index.year
Gold_History_Table["month"] = Gold_History_Table.index.month
Gold_History_Table["dow"] = Gold_History_Table.index.day_name()

with st.expander("🔍 Raw Data Preview"):
    st.dataframe(Gold_History_Table.tail(50), use_container_width=True)

#----------------------------#
    # UI #
#----------------------------#

st.markdown(
    f"""
    <style>
    @keyframes pulse {{
        0%   {{ transform: scale(1);   }}
        50%  {{ transform: scale(1.02); }}
        100% {{ transform: scale(1);   }}
    }}
    .gold-pulse {{
        background: linear-gradient(135deg, #8d6e37, #d4af37, #f5d76e);
        padding: 20px;
        border-radius: 14px;
        text-align: center;
        color: white;
        font-size: 34px;
        font-weight: 700;
        letter-spacing: 1px;
        border: 1px solid rgba(255,255,255,0.25);
        backdrop-filter: blur(6px);
        animation: pulse 3s ease-in-out infinite;
        transform-origin: center;
    }}
    </style>

    <div class="gold-pulse">
        GOLD — ${Gold_Price:,.2f} ({P_Change_percent})
        <div style="
            font-size: 14px;
            font-weight: 400;
            margin-top: 6px;
            opacity: 0.9;
        ">
            <span style ="
            color: black;
            ">
            Updated: {timestamp}
            </span>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

divider()

# -----------------------------------------
# Top-level metrics
# -----------------------------------------
last_row = Gold_History_Table.iloc[-1]
first_row = Gold_History_Table.iloc[0]

mean_daily = Gold_History_Table["ret"].mean()
std_daily = Gold_History_Table["ret"].std()

annual_return = (1 + mean_daily) ** trading_days - 1
annual_vol = std_daily * np.sqrt(trading_days)
sharpe = annual_return / annual_vol if annual_vol > 0 else np.nan

max_dd = Gold_History_Table["drawdown"].min()
dd_end = Gold_History_Table["drawdown"].idxmin()
dd_start = Gold_History_Table["cum_index"].loc[:dd_end].idxmax()

col1, col2, col3, col4 = st.columns(4)

col1.metric(
    "Last Close",
    f"${last_row['price']:,.2f}",
    f"{last_row['ret'] * 100:.2f}%" if pd.notna(last_row["ret"]) else None,
)

col2.metric(
    "15Y (Selected Period) Return",
    f"{(Gold_History_Table['cum_growth'].iloc[-1] - 1) * 100:.2f}%",
    help="Cumulative return over the visible period.",
)

col3.metric(
    "Annualized Return / Vol",
    f"{annual_return * 100:.2f}% / {annual_vol * 100:.2f}%",
    help="Geometric annualized return and annualized volatility.",
)

col4.metric(
    "Max Drawdown",
    f"{max_dd * 100:.2f}%",
    help=f"Worst peak-to-trough loss from {dd_start.date()} to {dd_end.date()}.",
)
divider()
# -----------------------------------------
# 0 — Quant Summary (auto-generated)
# -----------------------------------------
# ----------------- core stats -----------------
last_row = Gold_History_Table.iloc[-1]
first_row = Gold_History_Table.iloc[0]

mean_daily = Gold_History_Table["ret"].mean()
std_daily = Gold_History_Table["ret"].std()

annual_return = (1 + mean_daily) ** trading_days - 1
annual_vol = std_daily * np.sqrt(trading_days)
sharpe = annual_return / annual_vol if annual_vol > 0 else np.nan

max_dd = Gold_History_Table["drawdown"].min()
dd_end = Gold_History_Table["drawdown"].idxmin()
dd_start = Gold_History_Table["cum_index"].loc[:dd_end].idxmax()

# Month-of-year stats
monthly_ret = (
    Gold_History_Table["ret"]
    .resample("M")
    .apply(lambda x: (1 + x).prod() - 1)
    .to_frame(name="monthly_ret")
)

month_stats = (
    monthly_ret
    .groupby(monthly_ret.index.month)["monthly_ret"]
    .agg(["mean", "std", "count"])
)
month_stats["mean_pct"] = month_stats["mean"] * 100
month_stats["std_pct"] = month_stats["std"] * 100

# Day-of-week stats
dow_stats = Gold_History_Table.groupby("dow")["ret"].agg(["mean", "std", "count"])
dow_stats["mean_pct"] = dow_stats["mean"] * 100
dow_stats["std_pct"] = dow_stats["std"] * 100

# Tail-risk stats
ret_series = Gold_History_Table["ret"].dropna()
skew_val = ret_series.skew()
kurt_val = ret_series.kurt()  # excess kurtosis
var_95 = ret_series.quantile(0.05)
cvar_95 = ret_series[ret_series <= var_95].mean()

# Momentum vs mean reversion
lookback = 20
Gold_History_Table["past20"] = (1 + Gold_History_Table["ret"]).rolling(lookback).apply(lambda x: np.prod(1 + x) - 1)
Gold_History_Table["future20"] = (
    (1 + Gold_History_Table["ret"]).shift(-lookback).rolling(lookback).apply(lambda x: np.prod(1 + x) - 1)
)

test = Gold_History_Table.dropna(subset=["past20", "future20"]).copy()
bucket_perf = None
if not test.empty:
    test["past20_bucket"] = pd.qcut(test["past20"], 5, labels=False)
    bucket_perf = test.groupby("past20_bucket")["future20"].mean().to_frame("avg_future20")
    bucket_perf["avg_future20_pct"] = bucket_perf["avg_future20"] * 100

# Short-term vol regime (where is current vol vs history?)
vol_hist = Gold_History_Table["vol_30d"].dropna()
current_vol_30 = vol_hist.iloc[-1] if not vol_hist.empty else np.nan
if not vol_hist.empty and not np.isnan(current_vol_30):
    vol_percentile = (vol_hist < current_vol_30).mean() * 100
else:
    vol_percentile = np.nan


st.subheader("0. Quant Summary (Auto-Generated)")

# Build a simple text summary from the stats
def describe_sharpe(s: float) -> str:
    if np.isnan(s):
        return "Sharpe ratio could not be computed."
    if s < 0:
        return "Risk-adjusted performance has been **negative overall** (Sharpe < 0)."
    elif s < 0.5:
        return "Risk-adjusted performance is **weak** (Sharpe in the 0.0–0.5 range)."
    elif s < 1.0:
        return "Risk-adjusted performance is **decent but not amazing** (Sharpe ~0.5–1.0)."
    else:
        return "Risk-adjusted performance is **strong** (Sharpe > 1.0)."

def describe_skew_and_kurt(sk: float, kt: float) -> str:
    direction = "roughly symmetric" if abs(sk) < 0.2 else ("positively skewed (more big up moves than down moves)" if sk > 0 else "negatively skewed (down moves tend to be larger than up moves)")
    tail = "close to normal" if abs(kt) < 1 else ("fat-tailed with more extreme moves than a normal distribution" if kt > 0 else "light-tailed compared to a normal distribution")
    return f"Daily return distribution is **{direction}**, and tails are **{tail}**."

# Best / worst month
if not month_stats.empty:
    best_month_idx = month_stats["mean"].idxmax()
    worst_month_idx = month_stats["mean"].idxmin()
    best_month_name = pd.to_datetime(str(best_month_idx), format="%m").strftime("%b")
    worst_month_name = pd.to_datetime(str(worst_month_idx), format="%m").strftime("%b")
    best_month_ret = month_stats.loc[best_month_idx, "mean_pct"]
    worst_month_ret = month_stats.loc[worst_month_idx, "mean_pct"]
else:
    best_month_name = worst_month_name = None
    best_month_ret = worst_month_ret = np.nan

# Best / worst day-of-week
if not dow_stats.empty:
    best_dow = dow_stats["mean"].idxmax()
    worst_dow = dow_stats["mean"].idxmin()
    best_dow_ret = dow_stats.loc[best_dow, "mean_pct"]
    worst_dow_ret = dow_stats.loc[worst_dow, "mean_pct"]
else:
    best_dow = worst_dow = None
    best_dow_ret = worst_dow_ret = np.nan

# Momentum vs mean reversion
momentum_comment = "Not enough data yet to test 20-day momentum vs mean reversion."
if bucket_perf is not None:
    best_bucket = bucket_perf["avg_future20"].idxmax()
    worst_bucket = bucket_perf["avg_future20"].idxmin()
    if best_bucket > worst_bucket:
        momentum_comment = (
            "On a 20-day horizon, periods with **strong recent gains** tend to be followed by "
            "relatively **better future returns** → a **momentum tilt**."
        )
    elif best_bucket < worst_bucket:
        momentum_comment = (
            "On a 20-day horizon, periods with **strong recent gains** tend to be followed by "
            "**weaker future returns** → a **mean-reverting tilt**."
        )
    else:
        momentum_comment = (
            "On a 20-day horizon, future returns do not show a strong monotonic relationship with past returns."
        )

summary_lines = []

summary_lines.append(
    f"- Over the selected period, gold has compounded at **{(Gold_History_Table['cum_growth'].iloc[-1] - 1) * 100:.2f}%** in total, "
    f"with an annualized return of **{annual_return * 100:.2f}%** and annualized volatility of **{annual_vol * 100:.2f}%**. "
    + describe_sharpe(sharpe)
)

summary_lines.append(
    f"- The **worst peak-to-trough drawdown** was **{max_dd * 100:.2f}%**, occurring between "
    f"**{dd_start.date()}** and **{dd_end.date()}**. This is a key measure of downside risk."
)

summary_lines.append(
    f"- At the daily level, the **95% historical VaR** is about **{var_95 * 100:.2f}%**, "
    f"and the **average loss in the worst 5% of days (CVaR)** is about **{cvar_95 * 100:.2f}%**. "
    + describe_skew_and_kurt(skew_val, kurt_val)
)

if best_month_name is not None:
    summary_lines.append(
        f"- Seasonally, **{best_month_name}** has been the strongest month on average "
        f"(~{best_month_ret:.2f}% average monthly return), while **{worst_month_name}** has been the weakest "
        f"(~{worst_month_ret:.2f}%)."
    )

if best_dow is not None:
    summary_lines.append(
        f"- By day-of-week, **{best_dow}** has shown the best average daily return (~{best_dow_ret:.3f}%), "
        f"whereas **{worst_dow}** has been the softest (~{worst_dow_ret:.3f}%). "
        "These patterns may reflect how macro news and positioning flow through the week."
    )

if not np.isnan(current_vol_30):
    summary_lines.append(
        f"- The current **30-day annualized volatility** is about **{current_vol_30 * 100:.2f}%**, "
        f"which sits around the **{vol_percentile:.0f}th percentile** of the past 30-day vol history "
        "(lower percentiles = calm regime, higher = stressed regime)."
    )

summary_lines.append(f"- **Momentum vs mean reversion (20 days):** {momentum_comment}")

st.markdown(
    "Here’s an automatically generated summary of how gold has behaved over the selected period:\n\n"
    + "\n\n".join(summary_lines)
)

# -----------------------------------------
# Section 1 — Price & Cumulative Performance
# -----------------------------------------
divider()

st.subheader("1. Price & Cumulative Performance")

c1, c2 = st.columns(2)

with c1:
    st.markdown("**Daily Price (Close)**")
    st.line_chart(Gold_History_Table["price"])

with c2:
    st.markdown("**Cumulative Performance (Index = 100)**")
    st.line_chart(Gold_History_Table["cum_index"])


# -----------------------------------------
# Section 2 — Drawdowns (Risk)
# -----------------------------------------

divider()

st.subheader("2. Drawdowns & Crash Analysis")

c3, c4 = st.columns(2)

with c3:
    st.markdown("**Drawdown Curve**")
    # Drawdown as percentage
    dd_chart_data = Gold_History_Table["drawdown"] * 100
    st.area_chart(dd_chart_data)

with c4:
    st.markdown("**Worst 10 Drawdown Days (Daily Returns)**")
    worst_days = Gold_History_Table["ret"].nsmallest(10).to_frame(name="daily_return")
    worst_days["daily_return_pct"] = worst_days["daily_return"] * 100
    st.dataframe(
        worst_days[["daily_return_pct"]],
        use_container_width=True,
        hide_index=False,
    )


# -----------------------------------------
# Section 3 — Volatility Regimes
# -----------------------------------------

divider()

st.subheader("3. Volatility Regimes (30d & 90d Rolling)")

vol_cols = ["vol_30d", "vol_90d"]
st.line_chart(Gold_History_Table[vol_cols])


# -----------------------------------------
# Section 4 — Seasonality (Month & Day-of-Week)
# -----------------------------------------

divider()

st.subheader("4. Seasonality Patterns")

# Monthly returns (calendar months)
monthly_ret = (
    Gold_History_Table["ret"]
    .resample("M")
    .apply(lambda x: (1 + x).prod() - 1)
    .to_frame(name="monthly_ret")
)

month_stats = (
    monthly_ret
    .groupby(monthly_ret.index.month)["monthly_ret"]
    .agg(["mean", "std", "count"])
)

month_stats["mean_pct"] = month_stats["mean"] * 100
month_stats["std_pct"] = month_stats["std"] * 100

# Day-of-week stats
dow_stats = Gold_History_Table.groupby("dow")["ret"].agg(["mean", "std", "count"])
dow_stats["mean_pct"] = dow_stats["mean"] * 100
dow_stats["std_pct"] = dow_stats["std"] * 100

c5, c6 = st.columns(2)

with c5:
    st.markdown("**Month-of-Year Average Returns**")
    month_stats_display = month_stats.copy()
    month_stats_display.index = [
        pd.to_datetime(str(m), format="%m").strftime("%b") for m in month_stats_display.index
    ]
    st.dataframe(
        month_stats_display[["mean_pct", "std_pct", "count"]].round(2),
        use_container_width=True,
    )

with c6:
    st.markdown("**Day-of-Week Average Returns**")
    dow_stats_display = dow_stats.loc[
        ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        if set(["Monday", "Friday"]).issubset(dow_stats.index)
        else dow_stats.index
    ]
    st.dataframe(
        dow_stats_display[["mean_pct", "std_pct", "count"]].round(2),
        use_container_width=True,
    )


# -----------------------------------------
# Section 5 — Distribution & Tail Risk
# -----------------------------------------
divider()

st.subheader("5. Return Distribution & Tail Risk")

ret_series = Gold_History_Table["ret"].dropna()

skew_val = ret_series.skew()
kurt_val = ret_series.kurt()  # excess kurtosis

var_95 = ret_series.quantile(0.05)
cvar_95 = ret_series[ret_series <= var_95].mean()

c7, c8, c9 = st.columns(3)
c7.metric("Daily Skew", f"{skew_val:.3f}")
c8.metric("Excess Kurtosis", f"{kurt_val:.3f}")
c9.metric("95% VaR / CVaR (Daily)", f"{var_95*100:.2f}% / {cvar_95*100:.2f}%")

# Simple histogram with Streamlit (bins via value_counts on cut)
hist = ret_series.clip(lower=ret_series.quantile(0.01), upper=ret_series.quantile(0.99))
hist_Gold_History_Table = hist.to_frame(name="ret")
hist_Gold_History_Table["bucket"] = pd.cut(hist_Gold_History_Table["ret"], bins=30)
hist_counts = hist_Gold_History_Table["bucket"].value_counts().sort_index()
hist_plot_Gold_History_Table = pd.DataFrame(
    {"bucket": hist_counts.index.astype(str), "count": hist_counts.values}
).set_index("bucket")

st.markdown("**Approximate Distribution of Daily Returns (clipped 1% tails)**")
st.bar_chart(hist_plot_Gold_History_Table)

divider()

# -----------------------------------------
# Section 6 — Momentum vs Mean Reversion (20-day)
# -----------------------------------------
st.subheader("6. Momentum vs Mean Reversion (20-Day Lookback)")

lookback = 20

Gold_History_Table["past20"] = (1 + Gold_History_Table["ret"]).rolling(lookback).apply(lambda x: np.prod(1 + x) - 1)
Gold_History_Table["future20"] = (
    (1 + Gold_History_Table["ret"]).shift(-lookback).rolling(lookback).apply(lambda x: np.prod(1 + x) - 1)
)

test = Gold_History_Table.dropna(subset=["past20", "future20"]).copy()

if not test.empty:
    test["past20_bucket"] = pd.qcut(test["past20"], 5, labels=False)
    bucket_perf = test.groupby("past20_bucket")["future20"].mean().to_frame("avg_future20")
    bucket_perf["avg_future20_pct"] = bucket_perf["avg_future20"] * 100

    st.markdown(
        "We bucket past 20-day returns into quintiles and look at the average future 20-day return in "
        "each bucket. If higher buckets have higher future returns → momentum; if lower → mean reversion."
    )
    st.dataframe(bucket_perf[["avg_future20_pct"]].round(2), use_container_width=True)
else:
    st.info("Not enough data to compute 20-day momentum / mean reversion statistics yet.")

divider()