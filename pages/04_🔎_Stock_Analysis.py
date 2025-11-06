import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

st.set_page_config(page_title="Bell Curve from Prices", layout="centered")
st.title("📈 Bell Curve of Daily Returns (from Prices)")

# ---------- Upload ----------
uploaded_file = st.file_uploader("Upload a CSV with a Date column and a price column", type=["csv"])

# ---------- Helpers ----------
def guess_date_col(cols):
    cands = [c for c in cols if c.lower() in ("date", "time", "datetime")]
    return cands[0] if cands else None

def guess_price_col(cols):
    priority = ["adj close", "adjusted close", "close", "price", "last"]
    for p in priority:
        for c in cols:
            if p == c.lower():
                return c
    # fallback: first numeric column
    return None

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)

    # Try to detect date column and parse dates
    date_col_guess = guess_date_col(df.columns)
    date_col = st.selectbox(
        "Select the date column",
        options=df.columns.tolist(),
        index=(df.columns.get_loc(date_col_guess) if date_col_guess in df.columns else 0)
    )

    # Coerce to datetime and sort
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col]).sort_values(date_col)

    # Price column selection (try good defaults)
    price_guess = guess_price_col(df.columns)
    price_col = st.selectbox(
        "Select the price column",
        options=[c for c in df.columns if c != date_col],
        index=([c.lower() for c in df.columns].index(price_guess) if price_guess and price_guess.lower() in [c.lower() for c in df.columns] else 0)
    )

    # Show preview
    st.write("### Preview")
    st.dataframe(df[[date_col, price_col]].head())

    # Resampling (optional) in case user uploads intraday
    resample = st.checkbox("Resample to daily (last price per day)", value=True)
    px = df[[date_col, price_col]].dropna().copy()
    px = px.rename(columns={date_col: "Date", price_col: "Price"}).set_index("Date")
    if resample:
        px = px.resample("1D").last().dropna()

    st.write(f"**Rows after prep:** {len(px):,}")

    # Returns type
    returns_type = st.radio("Return type", ["Simple % (ΔP/P × 100)", "Log % (ln(Pt/Pt-1) × 100)"], horizontal=True)

    if returns_type.startswith("Simple"):
        rets = px["Price"].pct_change() * 100.0
    else:
        rets = np.log(px["Price"] / px["Price"].shift(1)) * 100.0

    rets = rets.dropna()

    # Outlier trimming (optional)
    st.subheader("Trimming & Binning")
    trim = st.checkbox("Trim outliers by percentile", value=True)
    if trim:
        low_p, high_p = st.slider("Keep middle percentile range", 90, 100, (98, 100), help="e.g., 98–100 keeps the middle 98%")
        lo = (100 - low_p) / 2
        hi = 100 - lo
        lo_val, hi_val = np.percentile(rets, [lo, hi])
        rets = rets[(rets >= lo_val) & (rets <= hi_val)]

    bins = st.slider("Number of bins", 20, 150, 60)

    if rets.empty:
        st.warning("No returns left after processing. Try adjusting your options.")
    else:
        # ---------- Plot ----------
        st.subheader("Bell Curve of Daily Returns")
        fig, ax = plt.subplots(figsize=(8, 5))

        # Histogram (counts, not density)
        counts, bin_edges, _ = ax.hist(rets.values, bins=bins, density=False, alpha=0.6, edgecolor="black")

        # Normal fit scaled to counts (pdf × N × bin_width)
        mu, sigma = float(rets.mean()), float(rets.std(ddof=1))
        x = np.linspace(rets.min(), rets.max(), 400)
        bin_width = (bin_edges[-1] - bin_edges[0]) / bins
        pdf_counts = (1.0 / (sigma * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x - mu) / sigma) ** 2)
        pdf_counts *= len(rets) * bin_width
        ax.plot(x, pdf_counts, linewidth=2, label=f"Normal Fit (μ={mu:.2f}%, σ={sigma:.2f}%)")

        # Mean and ±1σ markers
        ax.axvline(mu, linestyle="--", linewidth=1, label="Mean")
        ax.axvline(mu - sigma, linestyle=":", linewidth=1, label="±1σ")
        ax.axvline(mu + sigma, linestyle=":", linewidth=1)

        ax.set_xlabel("Daily Return (%)")
        ax.set_ylabel("Frequency (count)")
        ax.legend()
        ax.grid(True, linestyle="--", alpha=0.4)
        st.pyplot(fig)

        # ---------- Summary ----------
        st.subheader("Summary Statistics")
        desc = rets.describe(percentiles=[0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99])
        extra = pd.Series(
            {
                "skew": rets.skew(),
                "kurtosis": rets.kurtosis(),
                "VaR 95% (one-day, %)": np.percentile(rets, 5),
                "VaR 99% (one-day, %)": np.percentile(rets, 1),
            }
        )
        st.dataframe(pd.concat([desc, extra]).to_frame(name="value").T)

else:
    st.info("Upload a CSV with a **Date** column and a **price** column (e.g., Adj Close, Close, Price).")
