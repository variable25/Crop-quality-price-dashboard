"""
dashboard.py - a read-only view of the Crop Lab ETL database.

Run from the project folder:   streamlit run dashboard.py
"""
import altair as alt
import pandas as pd
import streamlit as st
from sqlalchemy import text

from pipeline.db import get_engine

CROPS = ["Tur", "Groundnut", "Chana", "Turmeric"]

# Print-style palette: dark ink, rust and olive on warm paper.
INK = "#22201C"
RUST = "#9C4A1A"
OLIVE = "#4B5A35"
RULE = "#CBC2AE"
LINE_COLORS = [INK, RUST, OLIVE]      # each crop has at most 2 markets in our data

# Switch off every transition and animation Streamlit ships with (hover effects, fades, shimmer).
NO_MOTION_CSS = """
<style>
*, *::before, *::after { transition: none !important; animation: none !important; }
</style>
"""

st.set_page_config(page_title="Crop quality and prices", layout="wide")
st.markdown(NO_MOTION_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------- data access

@st.cache_resource
def engine():
    """One database engine for the whole app, created on first use."""
    return get_engine()


@st.cache_data(ttl=300, show_spinner=False)
def run_query(sql):
    """Run a read-only query and return a DataFrame. Cached for 5 minutes."""
    with engine().connect() as conn:
        return pd.read_sql(text(sql), conn)


def load_prices():
    df = run_query("""
        SELECT price_date, market, commodity, source,
               min_price_rs_qtl, modal_price_rs_qtl, max_price_rs_qtl
          FROM market_prices
         ORDER BY price_date, market
    """)
    df["price_date"] = pd.to_datetime(df["price_date"])
    return df


def load_lab():
    df = run_query("""
        SELECT sample_id, commodity, test_date, moisture_pct, oil_pct, foreign_matter_pct,
               aflatoxin_ppb, aflatoxin_below_detection, needs_review, review_note
          FROM lab_results
         ORDER BY test_date, sample_id
    """)
    df["test_date"] = pd.to_datetime(df["test_date"])
    return df


def load_rejected():
    return run_query("""
        SELECT f.file_name, r.excel_row, r.target_table, r.reason
          FROM rejected_rows r
          JOIN processed_files f ON f.file_id = r.source_file_id
         ORDER BY f.file_name, r.excel_row
    """)


def load_files():
    return run_query("""
        SELECT file_name, file_type, status, rows_loaded, rows_rejected, error_message, processed_at
          FROM processed_files
         ORDER BY file_id
    """)


def load_runs():
    return run_query("""
        SELECT run_id, started_at, finished_at, status, files_seen, files_loaded,
               files_skipped, files_failed, rows_loaded, rows_rejected
          FROM pipeline_runs
         ORDER BY run_id DESC
    """)


# ---------------------------------------------------------------- display

def plain_chart(chart):
    """Flat, print-style chart: thin rules, muted ink, no box around the plot."""
    return (chart
            .configure(background="transparent")
            .configure_view(stroke=None)
            .configure_axis(gridColor=RULE, gridOpacity=0.5, domainColor=INK, tickColor=INK,
                            labelColor=INK, titleColor=INK, titleFontWeight="normal")
            .configure_legend(labelColor=INK, titleColor=INK, titleFontWeight="normal", orient="top"))


def show_scorecard(prices, lab, rejected, files, runs):
    last = runs.iloc[0]
    cols = st.columns(4)
    cols[0].metric("Last run", f"#{last['run_id']} {last['status']}")
    cols[1].metric("Clean rows stored", f"{len(lab) + len(prices):,}")
    cols[2].metric("Rows set aside", f"{len(rejected):,}")
    cols[3].metric("Files failed", f"{(files['status'] == 'failed').sum():,}")


def show_prices_tab(prices, crop, start, end):
    df = prices[(prices["commodity"] == crop) & prices["price_date"].between(start, end)]
    st.subheader(f"{crop}: modal price per market")
    if df.empty:
        st.write("No prices for this crop and date range.")
        return

    chart = alt.Chart(df).mark_line(strokeWidth=1.8).encode(
        x=alt.X("price_date:T", title=None),
        y=alt.Y("modal_price_rs_qtl:Q", title="Rs per quintal", scale=alt.Scale(zero=False)),
        color=alt.Color("market:N", title="Market", scale=alt.Scale(range=LINE_COLORS)),
        tooltip=[alt.Tooltip("price_date:T", title="Date"),
                 alt.Tooltip("market:N", title="Market"),
                 alt.Tooltip("modal_price_rs_qtl:Q", title="Modal price", format=",.0f")],
    ).properties(height=340)
    st.altair_chart(plain_chart(chart), theme=None)
    st.caption("Modal price is the most common trading price of the day. "
               "Gaps are Sundays, when markets are closed.")
    st.dataframe(df.drop(columns="commodity"), hide_index=True)


def show_lab_tab(lab, crop, start, end):
    in_range = lab[lab["test_date"].between(start, end)]
    if in_range.empty:
        st.write("No lab results in this date range.")
        return

    summary = (in_range.groupby("commodity")
               .agg(samples=("sample_id", "count"),
                    avg_moisture_pct=("moisture_pct", "mean"),
                    avg_foreign_matter_pct=("foreign_matter_pct", "mean"),
                    below_detection_share=("aflatoxin_below_detection", "mean"))
               .reindex(CROPS)
               .dropna(subset=["samples"])
               .reset_index())
    summary["aflatoxin_below_detection_pct"] = (summary.pop("below_detection_share") * 100).round(0)
    summary = summary.round(2)

    left, right = st.columns(2)
    with left:
        st.subheader("Average moisture per crop")
        bars = alt.Chart(summary).mark_bar(color=OLIVE, size=32).encode(
            x=alt.X("commodity:N", title=None, sort=CROPS, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("avg_moisture_pct:Q", title="Moisture %"),
            tooltip=[alt.Tooltip("commodity:N", title="Crop"),
                     alt.Tooltip("avg_moisture_pct:Q", title="Average moisture %")],
        ).properties(height=300)
        st.altair_chart(plain_chart(bars), theme=None)
    with right:
        st.subheader("Summary")
        st.dataframe(summary, hide_index=True)
        st.caption("Below detection means the lab reported ND, BDL or <LOD: "
                   "too small to measure, stored as empty with a flag.")

    st.divider()
    st.subheader("Samples flagged for review")
    flagged = in_range[in_range["needs_review"]]
    if flagged.empty:
        st.write("None in this date range.")
    else:
        st.dataframe(flagged[["sample_id", "commodity", "test_date", "foreign_matter_pct", "review_note"]],
                     hide_index=True)

    st.divider()
    st.subheader(f"{crop} samples")
    st.dataframe(in_range[in_range["commodity"] == crop].drop(columns=["commodity"]), hide_index=True)


def show_quality_tab(rejected, files, runs):
    st.subheader("Rows set aside")
    st.write(f"{len(rejected)} rows broke a rule and were kept out of the clean tables. "
             "Each one is stored with its reason and its original cells, so nothing disappears silently.")
    st.dataframe(rejected, hide_index=True)

    st.divider()
    st.subheader("Files")
    st.dataframe(files, hide_index=True)

    st.divider()
    st.subheader("Pipeline runs")
    st.dataframe(runs, hide_index=True)


# ---------------------------------------------------------------- page

def main():
    prices, lab = load_prices(), load_lab()
    rejected, files, runs = load_rejected(), load_files(), load_runs()

    st.title("Crop quality and market prices")
    st.caption("Karnataka, September 2022. Lab tests from a partner lab and prices from Agmarknet "
               "and a local trader, cleaned and loaded by the Crop Lab ETL pipeline.")

    if runs.empty:
        st.write("No pipeline runs yet. Load data first with:  python -m pipeline.run")
        st.stop()
    show_scorecard(prices, lab, rejected, files, runs)

    all_dates = pd.concat([prices["price_date"], lab["test_date"]])
    first, last = all_dates.min().date(), all_dates.max().date()

    st.sidebar.header("Filters")
    crop = st.sidebar.selectbox("Crop", CROPS)
    picked = st.sidebar.date_input("Date range", value=(first, last), min_value=first, max_value=last)
    if len(picked) != 2:
        st.sidebar.write("Pick an end date to finish the range.")
        st.stop()
    start, end = pd.Timestamp(picked[0]), pd.Timestamp(picked[1])

    prices_tab, lab_tab, quality_tab = st.tabs(["Prices", "Lab quality", "Data quality"])
    with prices_tab:
        show_prices_tab(prices, crop, start, end)
    with lab_tab:
        show_lab_tab(lab, crop, start, end)
    with quality_tab:
        show_quality_tab(rejected, files, runs)


main()