"""
dashboard.py - a read-only view of the Crop Lab ETL database.

Run from the project folder:   streamlit run dashboard.py
"""
import altair as alt
import pandas as pd
import streamlit as st
from sqlalchemy import text

from pipeline.config import load_mappings
from pipeline.db import get_engine

CROPS = ["Tur", "Groundnut", "Chana", "Turmeric"]

# One meaning per colour, across the whole page.
INK = "#22201C"      # main data
OLIVE = "#4B5A35"    # second market of a crop
RUST = "#9C4A1A"     # attention: rejected, flagged, above a limit
GREY = "#8C8270"     # "the rest", e.g. below detection
PAPER = "#F3EFE6"    # page background, also the 2px gap between bar parts
RULE = "#CBC2AE"     # gridlines

# Colour follows the market, never its position, so a filter never repaints a line.
MARKET_COLORS = {
    "Kalaburagi": INK, "Bidar": OLIVE,
    "Chitradurga": INK, "Challakere": OLIVE,
    "Gadag": INK, "Hubballi": OLIVE,
    "Chamarajanagar": INK,
}

# Short rule names for the rejection reasons written by the transform step.
REASON_RULES = [
    ("is missing", "Missing value"),
    ("not a valid date", "Invalid date"),
    ("in the future", "Future date"),
    ("outside 0-100", "Out of range"),
    ("is negative", "Negative value"),
    ("out of order", "Prices out of order"),
    ("recent median", "Price outlier"),
    ("unknown", "Unknown name"),
    ("not a number", "Not a number"),
]

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


def reason_category(reason):
    """Turn a full rejection reason into a short rule name."""
    for needle, label in REASON_RULES:
        if needle in reason:
            return label
    return "Other"


# ---------------------------------------------------------------- chart building blocks

def plain_chart(chart):
    """Flat, print-style chart: thin rules, muted ink, no box around the plot."""
    return (chart
            .configure(background="transparent")
            .configure_view(stroke=None)
            .configure_axis(gridColor=RULE, gridOpacity=0.6, domainColor=INK, tickColor=INK,
                            labelColor=INK, titleColor=INK, titleFontWeight="normal",
                            labelFontSize=12, titleFontSize=12)
            .configure_legend(labelColor=INK, titleColor=INK, titleFontWeight="normal", orient="top")
            .configure_header(labelColor=INK, labelFontSize=13, labelAnchor="start", title=None))


def table_view(df):
    """Every chart keeps its numbers one click away."""
    with st.expander("Table view"):
        st.dataframe(df, hide_index=True)


def price_lines(df):
    """Modal price per market, a light min-max band, and a label at each line end."""
    markets = sorted(df["market"].unique())
    color = alt.Color("market:N", title="Market",
                      scale=alt.Scale(domain=markets, range=[MARKET_COLORS.get(m, INK) for m in markets]))
    x = alt.X("price_date:T", title=None, axis=alt.Axis(grid=False, format="%d %b"))
    y_title = "Rs per quintal"
    base = alt.Chart(df).encode(x=x)

    band = base.mark_area(opacity=0.12).encode(
        y=alt.Y("min_price_rs_qtl:Q", title=y_title, scale=alt.Scale(zero=False)),
        y2="max_price_rs_qtl:Q",
        color=color,
    )
    lines = base.mark_line(strokeWidth=2).encode(
        y=alt.Y("modal_price_rs_qtl:Q", title=y_title), color=color)
    hover = base.mark_point(size=160, filled=True, opacity=0.001).encode(   # invisible hover targets
        y=alt.Y("modal_price_rs_qtl:Q", title=y_title),
        tooltip=[alt.Tooltip("price_date:T", title="Date", format="%d %b %Y"),
                 alt.Tooltip("market:N", title="Market"),
                 alt.Tooltip("min_price_rs_qtl:Q", title="Min", format=",.0f"),
                 alt.Tooltip("modal_price_rs_qtl:Q", title="Modal", format=",.0f"),
                 alt.Tooltip("max_price_rs_qtl:Q", title="Max", format=",.0f")],
    )

    ends = (df.sort_values("price_date")
              .groupby("market")
              .agg(first=("modal_price_rs_qtl", "first"),
                   last=("modal_price_rs_qtl", "last"),
                   price_date=("price_date", "last"))
              .reset_index())
    ends["label"] = [f"{m}  {(l - f) / f * 100:+.1f}%"
                     for m, f, l in zip(ends["market"], ends["first"], ends["last"])]
    labels = alt.Chart(ends).mark_text(align="left", dx=8, color=INK, fontSize=12).encode(
        x="price_date:T", y=alt.Y("last:Q", title=y_title), text="label:N")

    return alt.layer(band, lines, hover, labels).properties(
        height=360, padding={"left": 5, "top": 10, "right": 160, "bottom": 5})


def crop_small_multiples(prices):
    """Four small charts, one per crop: average modal price across that crop's markets."""
    avg = prices.groupby(["commodity", "price_date"], as_index=False)["modal_price_rs_qtl"].mean()
    return alt.Chart(avg).mark_line(color=INK, strokeWidth=1.5).encode(
        x=alt.X("price_date:T", title=None,
                axis=alt.Axis(grid=False, format="%d %b", tickCount=4, labelAngle=0)),
        y=alt.Y("modal_price_rs_qtl:Q", title=None, scale=alt.Scale(zero=False)),
        tooltip=[alt.Tooltip("commodity:N", title="Crop"),
                 alt.Tooltip("price_date:T", title="Date", format="%d %b %Y"),
                 alt.Tooltip("modal_price_rs_qtl:Q", title="Average modal", format=",.0f")],
    ).properties(width=230, height=130).facet(
        facet=alt.Facet("commodity:N", sort=CROPS, title=None), columns=4,
    ).resolve_scale(y="independent")


def dot_plot(df, column, title, limit=None):
    """One dot per sample, a short bar at each crop's average, an optional rust limit line."""
    y = alt.Y("commodity:N", title=None, sort=CROPS)
    x_title = title
    dots = alt.Chart(df).mark_circle(size=70, opacity=0.6).encode(
        x=alt.X(f"{column}:Q", title=x_title, scale=alt.Scale(zero=False)),
        y=y,
        color=alt.condition(alt.datum.needs_review, alt.value(RUST), alt.value(INK)),
        tooltip=[alt.Tooltip("sample_id:N", title="Sample"),
                 alt.Tooltip("commodity:N", title="Crop"),
                 alt.Tooltip(f"{column}:Q", title=title),
                 alt.Tooltip("review_note:N", title="Review note")],
    )
    means = df.groupby("commodity", as_index=False)[column].mean()
    avg = alt.Chart(means).mark_tick(color=INK, thickness=2, size=26).encode(
        x=alt.X(f"{column}:Q", title=x_title), y=y,
        tooltip=[alt.Tooltip("commodity:N", title="Crop"),
                 alt.Tooltip(f"{column}:Q", title="Average", format=".2f")],
    )
    layers = [dots, avg]
    if limit is not None:
        limit_df = pd.DataFrame({"limit": [limit], "text": [f"review limit {limit:g}%"]})
        layers.append(alt.Chart(limit_df).mark_rule(color=RUST, strokeWidth=1.5).encode(
            x=alt.X("limit:Q", title=x_title)))
        layers.append(alt.Chart(limit_df).mark_text(color=INK, align="left", dx=5, fontSize=11).encode(
            x=alt.X("limit:Q", title=x_title), y=alt.value(8), text="text:N"))
    return alt.layer(*layers).properties(height=220)


def share_bar(df, category, parts, colors, title, sort=None):
    """100% stacked bar: one bar per category, split into parts that add up to 100%.
    df needs the columns: <category>, part, count."""
    df = df.assign(part_order=df["part"].map({p: i for i, p in enumerate(parts)}))
    return alt.Chart(df).mark_bar(size=22, stroke=PAPER, strokeWidth=2).encode(
        x=alt.X("count:Q", stack="normalize", title=title, axis=alt.Axis(format="%", grid=False)),
        y=alt.Y(f"{category}:N", title=None, sort=sort, axis=alt.Axis(labelLimit=320)),
        color=alt.Color("part:N", title=None, scale=alt.Scale(domain=parts, range=colors)),
        order=alt.Order("part_order:Q"),
        tooltip=[alt.Tooltip(f"{category}:N"),
                 alt.Tooltip("part:N", title="Part"),
                 alt.Tooltip("count:Q", title="Rows")],
    ).properties(height=36 * df[category].nunique())


def count_bars(df, category, title):
    """Horizontal rust bars, longest at the top, with the count written at the bar end.
    df needs the columns: <category>, rows."""
    bars = alt.Chart(df).mark_bar(color=RUST, size=20).encode(
        x=alt.X("rows:Q", title=title, axis=alt.Axis(tickMinStep=1, grid=False)),
        y=alt.Y(f"{category}:N", title=None, sort="-x"),
        tooltip=[alt.Tooltip(f"{category}:N", title="Rule"), alt.Tooltip("rows:Q", title="Rows")],
    )
    counts = bars.mark_text(align="left", dx=5, color=INK, fontSize=12).encode(text="rows:Q")
    return alt.layer(bars, counts).properties(height=34 * len(df))


# ---------------------------------------------------------------- page sections

def show_scorecard(prices, lab, rejected, files, runs):
    last = runs.iloc[0]
    cols = st.columns(4)
    cols[0].metric("Last run", f"#{last['run_id']} {last['status']}")
    cols[1].metric("Clean rows stored", f"{len(lab) + len(prices):,}")
    cols[2].metric("Rows set aside", f"{len(rejected):,}")
    cols[3].metric("Files failed", f"{(files['status'] == 'failed').sum():,}")


def show_prices_tab(prices, crop, start, end):
    in_range = prices[prices["price_date"].between(start, end)]
    df = in_range[in_range["commodity"] == crop]

    st.subheader(f"{crop}: modal price per market")
    if df.empty:
        st.write("No prices for this crop and date range.")
    else:
        st.altair_chart(plain_chart(price_lines(df)), theme=None)
        st.caption("Line: modal price, the most common trading price of the day. "
                   "Shaded band: the day's minimum to maximum. Gaps are Sundays, when markets close. "
                   "The label at each line end is the change over the selected dates.")
        table_view(df.drop(columns="commodity"))

    st.divider()
    st.subheader("All crops at a glance")
    st.caption("Average modal price across each crop's markets, Rs per quintal. Each chart has its own scale.")
    if not in_range.empty:
        st.altair_chart(plain_chart(crop_small_multiples(in_range)), theme=None)


def show_lab_tab(lab, start, end, review_limit):
    in_range = lab[lab["test_date"].between(start, end)]
    if in_range.empty:
        st.write("No lab results in this date range.")
        return

    left, right = st.columns(2)
    with left:
        st.subheader("Moisture per sample")
        st.altair_chart(plain_chart(dot_plot(in_range, "moisture_pct", "Moisture %")), theme=None)
    with right:
        st.subheader("Foreign matter per sample")
        st.altair_chart(plain_chart(dot_plot(in_range, "foreign_matter_pct", "Foreign matter %",
                                             limit=review_limit)), theme=None)
    st.caption("Each dot is one sample and the short bar is the crop average. "
               "Rust marks a sample flagged for review.")

    st.divider()
    left, right = st.columns(2)
    with left:
        st.subheader("Aflatoxin results")
        results = in_range.assign(part=in_range["aflatoxin_below_detection"].map(
            {True: "Below detection", False: "Detected"}))
        results = results[results["part"] == "Below detection"].pipe(
            lambda below: pd.concat([below, results[(results["part"] == "Detected")
                                                    & results["aflatoxin_ppb"].notna()]]))
        afla = results.groupby(["commodity", "part"]).size().reset_index(name="count")
        st.altair_chart(plain_chart(share_bar(afla, "commodity", ["Detected", "Below detection"],
                                              [INK, GREY], "Share of samples", sort=CROPS)), theme=None)
        st.caption("Below detection means the lab reported ND, BDL or <LOD: too small to measure. "
                   "It is stored as empty with a flag, never as zero.")
    with right:
        st.subheader("Groundnut oil content")
        oil = in_range["oil_pct"].dropna()
        st.metric("Average across samples", f"{oil.mean():.1f}%" if not oil.empty else "No data")
        st.subheader("Flagged for review")
        flagged = in_range[in_range["needs_review"]]
        if flagged.empty:
            st.write("None in this date range.")
        for row in flagged.itertuples():
            note = str(row.review_note).replace("_", " ")
            st.write(f"{row.sample_id}, {row.commodity}, tested {row.test_date:%d %b %Y}: {note}")

    table_view(in_range)


def show_quality_tab(rejected, files, runs):
    status = files["status"].value_counts()
    st.write(f"File attempts across all runs: {status.get('loaded', 0)} loaded, "
             f"{status.get('skipped_duplicate', 0)} skipped as duplicates, "
             f"{status.get('failed', 0)} failed.")

    left, right = st.columns(2)
    with left:
        st.subheader("Rows per file")
        per_file = files[files["status"] == "loaded"].melt(
            id_vars="file_name", value_vars=["rows_loaded", "rows_rejected"],
            var_name="part", value_name="count")
        per_file["part"] = per_file["part"].map({"rows_loaded": "Loaded", "rows_rejected": "Rejected"})
        if not per_file.empty:
            st.altair_chart(plain_chart(share_bar(per_file, "file_name", ["Loaded", "Rejected"],
                                                  [INK, RUST], "Share of rows")), theme=None)
        st.caption("Loaded rows went into the clean tables. Rejected rows went into "
                   "rejected_rows, each with its reason.")
    with right:
        st.subheader("Rejections by rule")
        with_rule = rejected.assign(rule=rejected["reason"].map(reason_category))
        by_rule = with_rule.groupby("rule").size().reset_index(name="rows")
        if by_rule.empty:
            st.write("No rows were rejected.")
        else:
            st.altair_chart(plain_chart(count_bars(by_rule, "rule", "Rows set aside")), theme=None)

    table_view(with_rule)

    st.divider()
    st.subheader("Pipeline runs")
    st.dataframe(runs, hide_index=True)


# ---------------------------------------------------------------- page

def main():
    prices, lab = load_prices(), load_lab()
    rejected, files, runs = load_rejected(), load_files(), load_runs()
    review_limit = load_mappings()["rules"]["lab"]["review_above"]["foreign_matter_pct"]

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
    crop = st.sidebar.selectbox("Crop for the price chart", CROPS)
    picked = st.sidebar.date_input("Date range", value=(first, last), min_value=first, max_value=last)
    if len(picked) != 2:
        st.sidebar.write("Pick an end date to finish the range.")
        st.stop()
    start, end = pd.Timestamp(picked[0]), pd.Timestamp(picked[1])

    prices_tab, lab_tab, quality_tab = st.tabs(["Prices", "Lab quality", "Data quality"])
    with prices_tab:
        show_prices_tab(prices, crop, start, end)
    with lab_tab:
        show_lab_tab(lab, start, end, review_limit)
    with quality_tab:
        show_quality_tab(rejected, files, runs)


main()