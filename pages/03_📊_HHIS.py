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

st.write("Columns:", Ticker_Price_log.columns.tolist())


divider()


#----------------------------#
# What IF 
# #----------------------------#

st.subheader("📈 Historical + Projected Growth for " + ticker)

# Ensure proper types

Ticker_Price_log = Ticker_Price_log.sort_values("date")

# --- User controls ---
col_ctrl1, col_ctrl2 = st.columns(2)

with col_ctrl1:
    initial_invest = st.number_input(
        "Initial investment ($)",
        min_value=100.0,
        value=10000.0,
        step=500.0
    )
    start_date_sel = st.date_input(
        "Backtest start date",
        value=Ticker_Price_log["date"].min().date()
    )

with col_ctrl2:
    annual_price_growth = st.number_input(
        "Assumed annual price growth (excl. dividends) %",
        min_value=-50.0,
        max_value=50.0,
        value=6.0,
        step=0.5,
        help="This is the forward-looking price growth rate you want to test."
    )
    annual_div_yield = st.number_input(
        "Assumed annual dividend yield %",
        min_value=0.0,
        max_value=20.0,
        value=2.0,
        step=0.5,
        help="Forward-looking dividend yield. Used for projections only."
    )

years_ahead = st.slider(
    "Projection horizon (years)",
    min_value=1,
    max_value=30,
    value=10
)

div_policy = st.radio(
    "Dividend treatment",
    ["Reinvest dividends", "Take dividends as cash"],
    index=0
)

# --- Historical growth (based on actual prices) ---
hist = Ticker_Price_log[Ticker_Price_log["date"] >= pd.to_datetime(start_date_sel)].copy()

if hist.empty:
    st.warning("No historical data after the selected start date.")
else:
    # Scale historical prices to an investment starting at 'initial_invest'
    start_price = hist["close"].iloc[0]
    hist["portfolio_value"] = initial_invest * (hist["close"] / start_price)

    # --- Future projection (constant growth model) ---

    # Use monthly compounding for future
    periods = years_ahead * 12
    last_hist_date = hist["date"].iloc[-1]
    future_dates = pd.date_range(
        last_hist_date + pd.Timedelta(days=1),
        periods=periods,
        freq="M"
    )

    # Convert annual rates to monthly
    price_growth_monthly = (1 + annual_price_growth / 100.0) ** (1 / 12.0) - 1
    div_yield_monthly = (1 + annual_div_yield / 100.0) ** (1 / 12.0) - 1

    # Start from last historical portfolio value
    value_reinvest = hist["portfolio_value"].iloc[-1]
    value_no = hist["portfolio_value"].iloc[-1]
    cash_divs = 0.0

    proj_reinvest = []
    proj_no_reinvest = []
    proj_cash_divs = []

    for _ in range(periods):
        # Reinvest scenario: dividends increase the invested value
        value_reinvest *= (1 + price_growth_monthly + div_yield_monthly)
        proj_reinvest.append(value_reinvest)

        # No-reinvest scenario:
        # - price grows
        # - dividends are taken as cash (not compounding in the portfolio)
        value_no *= (1 + price_growth_monthly)
        cash_divs += value_no * div_yield_monthly
        proj_no_reinvest.append(value_no)
        proj_cash_divs.append(cash_divs)

    future_df = pd.DataFrame({
        "date": future_dates,
        "proj_reinvest": proj_reinvest,
        "proj_no_reinvest": proj_no_reinvest,
        "div_cash": proj_cash_divs,
    })

    # --- Combine historical + future for chart ---
    hist_plot = hist[["date", "portfolio_value"]].copy()
    hist_plot = hist_plot.rename(columns={"portfolio_value": "Historical"})

    future_plot = future_df.rename(columns={
        "proj_reinvest": "Projected (Reinvest)",
        "proj_no_reinvest": "Projected (No reinvest)"
    })

    combined = pd.concat([
        hist_plot,
        future_plot[["date", "Projected (Reinvest)", "Projected (No reinvest)"]]
    ], ignore_index=True)

    combined = combined.set_index("date")

    # Choose which lines to display based on user dividend policy
    if div_policy == "Reinvest dividends":
        chart_df = combined[["Historical", "Projected (Reinvest)"]]
    else:
        chart_df = combined[["Historical", "Projected (No reinvest)"]]

    st.line_chart(chart_df, use_container_width=True)

    # --- Text summary ---
    st.markdown("#### 📘 Projection Summary")

    final_reinvest = future_df["proj_reinvest"].iloc[-1]
    final_no = future_df["proj_no_reinvest"].iloc[-1]
    final_cash = future_df["div_cash"].iloc[-1]

    st.markdown(
        f"""
- Initial investment: **${initial_invest:,.2f}**
- Historical period: **{hist['date'].iloc[0].date()} → {hist['date'].iloc[-1].date()}**
- Projection horizon: **{years_ahead} years**
- Assumed annual price growth: **{annual_price_growth:.2f}%**
- Assumed annual dividend yield: **{annual_div_yield:.2f}%**

**If dividends are reinvested**:
- Projected portfolio value after {years_ahead} years: **${final_reinvest:,.2f}**

**If dividends are taken as cash**:
- Projected portfolio (price only) after {years_ahead} years: **${final_no:,.2f}**
- Total dividends collected in cash: **${final_cash:,.2f}**
"""
    )










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
    last_price = Ticker_Price_log["close"].iloc[-1]
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

st.subheader("Volatility Profile — Heatmap of Return Frequencies/Year")

if returns.empty:
    st.warning("Not enough data to build a heatmap.")
else:
    # Convert returns to percent for intuitive bucketing
    returns_pct = returns * 100

    # Define return buckets (you can tweak these)
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

    # Bucket each daily return into a range
    buckets = pd.cut(
        returns_pct,
        bins=bins_pct + [999],   # big upper bound for the last bucket
        labels=labels,
        right=True
    )

    # Prepare a DataFrame with year + bucket for grouping
    df_heat = pd.DataFrame({
        "year": returns.index.year,
        "bucket": buckets
    })

    # Count number of days per (year, bucket)
    heat_table = (
        df_heat
        .groupby(["year", "bucket"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=labels)      # ensure consistent column order
        .sort_index()
    )

    # Plot heatmap
    fig, ax = plt.subplots(figsize=(12, 6))

    im = ax.imshow(heat_table.values, aspect="auto")

    # Axis ticks & labels
    ax.set_yticks(np.arange(len(heat_table.index)))
    ax.set_yticklabels(heat_table.index)

    ax.set_xticks(np.arange(len(heat_table.columns)))
    ax.set_xticklabels(heat_table.columns, rotation=45, ha="right")

    ax.set_title(f"Return Frequency Heatmap for {ticker}", fontsize=16, pad=15)
    ax.set_xlabel("Daily Return Bucket (%)")
    ax.set_ylabel("Year")

    # Colorbar: how many days in each cell
    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Number of days")

    st.pyplot(fig)

    # Also show the underlying table for exact numbers
    st.markdown("#### Underlying Frequency Table")
    st.dataframe(
        heat_table,
        use_container_width=True
    )

divider()
# ------------------------------------------------
# Monte Carlo
# ------------------------------------------------



st.subheader("🔮 Monte Carlo Simulation (Bootstrap from Historical Returns)")

if returns.empty:
    st.warning("Not enough data to run simulations.")
else:
    sim_horizon = st.slider("Simulation horizon (days)", min_value=5, max_value=252, value=20, step=5)
    n_sims = st.slider("Number of simulations", min_value=500, max_value=5000, value=2000, step=500)

    # Convert series to numpy for speed
    ret_array = returns.values

    # Simulate: each column is one path of sim_horizon days
    rng = np.random.default_rng()
    sims = rng.choice(ret_array, size=(sim_horizon, n_sims), replace=True)

    # Convert to cumulative returns
    sim_cum_rets = (1 + sims).prod(axis=0) - 1

    # Convert to simulated prices from last_price
    sim_final_prices = last_price * (1 + sim_cum_rets)

    # Summary stats
    p05 = np.percentile(sim_cum_rets, 5) * 100
    p50 = np.percentile(sim_cum_rets, 50) * 100
    p95 = np.percentile(sim_cum_rets, 95) * 100

    st.markdown(
        f"Simulated **{n_sims} paths** over **{sim_horizon} trading days** using bootstrapped daily "
        f"returns from historical data."
    )

    c1, c2, c3 = st.columns(3)
    c1.metric(f"{sim_horizon}-day P5 return", f"{p05:.2f}%")
    c2.metric(f"{sim_horizon}-day Median (P50)", f"{p50:.2f}%")
    c3.metric(f"{sim_horizon}-day P95 return", f"{p95:.2f}%")

    # Plot histogram of simulated cumulative returns
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(sim_cum_rets * 100, bins=40, color="#4A90E2", alpha=0.7, edgecolor="white")
    ax.set_title(f"Simulated {sim_horizon}-Day Returns for {ticker}")
    ax.set_xlabel(f"{sim_horizon}-Day Return (%)")
    ax.set_ylabel("Number of simulations")
    ax.axvline(p05, color="red", linestyle="--", label=f"P5 ({p05:.2f}%)")
    ax.axvline(p50, color="green", linestyle="--", label=f"P50 ({p50:.2f}%)")
    ax.axvline(p95, color="orange", linestyle="--", label=f"P95 ({p95:.2f}%)")
    ax.legend()
    ax.grid(alpha=0.3, linestyle="--")

    st.pyplot(fig)

    st.markdown(
        f"- **P5** ≈ very bad scenario (only 5% of simulations are worse)\n"
        f"- **P50** = median scenario\n"
        f"- **P95** ≈ very good scenario (only 5% of simulations are better)\n\n"
        f"You can interpret this as: over the next **{sim_horizon} days**, based on past behavior, "
        f"there is about a 90% chance the total return falls between roughly **{p05:.1f}%** and **{p95:.1f}%**."
    )

divider()

# ------------------------------------------------
# Parametric Price Range (Normal Approximation)
# # ------------------------------------------------

st.subheader("📐 Parametric Price Range (Normal Approximation)")

if returns.empty:
    st.warning("Not enough data to build a parametric model.")
else:
    horiz_param = st.slider("Horizon for parametric estimate (days)", min_value=5, max_value=252, value=21, step=1)

    mean_h = mu * horiz_param
    std_h = sigma * np.sqrt(horiz_param)

    # 95% normal interval for cumulative return
    lower_ret = mean_h - 1.96 * std_h
    upper_ret = mean_h + 1.96 * std_h

    lower_price = last_price * (1 + lower_ret)
    median_price = last_price * (1 + mean_h)
    upper_price = last_price * (1 + upper_ret)

    c1, c2, c3 = st.columns(3)
    c1.metric(f"{horiz_param}-day 95% Lower Price", f"{lower_price:,.2f}")
    c2.metric(f"{horiz_param}-day Median Price", f"{median_price:,.2f}")
    c3.metric(f"{horiz_param}-day 95% Upper Price", f"{upper_price:,.2f}")

    st.markdown(
        f"Using a **normal approximation** for daily returns with mean **{mu*100:.3f}%** "
        f"and daily volatility **{sigma*100:.3f}%**, we estimate a 95% confidence band "
        f"for the **{horiz_param}-day** price based on the historical distribution."
    )


# ------------------------------------------------
# Empirical Return Probabilities
# ------------------------------------------------

st.subheader("🎯 Empirical Return Probabilities")

if returns.empty:
    st.warning("Not enough data to compute probabilities.")
else:
    # Let user choose horizon and thresholds
    horizon = st.slider("Horizon (days)", min_value=1, max_value=60, value=5, step=1)
    loss_threshold = st.number_input("Loss threshold (%)", value=-5.0, step=0.5)
    gain_threshold = st.number_input("Gain threshold (%)", value=5.0, step=0.5)

    # Build rolling horizon returns (compounded)
    rolling_ret = (
        (1 + returns)
        .rolling(horizon)
        .apply(lambda x: (1 + x).prod() - 1, raw=False)
        .dropna()
    )

    # Convert thresholds from % to decimal
    loss_dec = loss_threshold / 100.0
    gain_dec = gain_threshold / 100.0

    # Probabilities
    prob_loss = (rolling_ret <= loss_dec).mean() * 100
    prob_gain = (rolling_ret >= gain_dec).mean() * 100
    prob_positive = (rolling_ret > 0).mean() * 100

    col1, col2, col3 = st.columns(3)
    col1.metric(f"P({horizon}-day return ≤ {loss_threshold:.1f}%)", f"{prob_loss:.2f}%")
    col2.metric(f"P({horizon}-day return ≥ {gain_threshold:.1f}%)", f"{prob_gain:.2f}%")
    col3.metric(f"P({horizon}-day return > 0%)", f"{prob_positive:.2f}%")

    st.markdown(
        f"These probabilities are **purely empirical**, using rolling {horizon}-day returns from your "
        f"historical sample of {len(rolling_ret)} overlapping periods."
    )


divider()

# -------------------------------------------
# 📊 Quant Summary Box 
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

divider()
