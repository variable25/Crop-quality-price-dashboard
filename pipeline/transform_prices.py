"""
transform_prices.py - messy price rows in, (clean rows, rejected rows) out.

Hard rules first, then duplicates are collapsed, then each modal price is compared
with the recent median for the same market and crop (outlier check).
"""
import logging
import statistics
from collections import defaultdict
from datetime import date

import pandas as pd

from pipeline.clean import (RowRejected, clean_text, date_or_reject, is_blank_row,
                            lookup_or_reject, number_or_reject)
from pipeline.config import load_mappings
from pipeline.extract import list_inbox_files, read_sheet

log = logging.getLogger(__name__)

PRICE_FIELDS = ["min_price", "max_price", "modal_price"]


def clean_price_row(record, format_name, mappings, today):
    """Return one clean price row (a dict). Raises RowRejected with the reason if a hard rule fails."""
    fmt = mappings["formats"][format_name]
    empty = mappings["empty_values"]

    price_date = date_or_reject(record.get("price_date"), "price_date", mappings["date_formats"], empty)
    if price_date is None:
        raise RowRejected("price_date is missing")
    if price_date > today:
        raise RowRejected(f"price_date {price_date} is in the future")

    market = lookup_or_reject(record.get("market"), "market", mappings["markets"])
    commodity = lookup_or_reject(record.get("commodity"), "commodity", mappings["commodities"])

    prices = {}
    for field in PRICE_FIELDS:
        value = number_or_reject(record.get(field), field, empty)
        if value is None:
            raise RowRejected(f"{field} is missing")
        if value <= 0:
            raise RowRejected(f"{field} {value} must be above 0")
        prices[field] = round(value * fmt["unit_multiplier"], 2)     # always Rs per quintal

    if not prices["min_price"] <= prices["modal_price"] <= prices["max_price"]:
        raise RowRejected(
            f"prices out of order: min {prices['min_price']}, modal {prices['modal_price']}, "
            f"max {prices['max_price']} (need min <= modal <= max)")

    return {
        "price_date": price_date,
        "market": market,
        "district": clean_text(record.get("district")) or mappings["market_districts"].get(market),
        "commodity": commodity,
        "variety": clean_text(record.get("variety")),
        "grade": clean_text(record.get("grade")),
        "min_price_rs_qtl": prices["min_price"],
        "max_price_rs_qtl": prices["max_price"],
        "modal_price_rs_qtl": prices["modal_price"],
        "source": format_name,
    }


def drop_duplicate_prices(rows):
    """One row per market + crop + date. Rows are in file order, so a later row wins."""
    latest = {}
    for row in rows:
        key = (row["market"], row["commodity"], row["price_date"])
        if key in latest:
            log.info("%s %s %s: dropped Excel row %s (duplicate of row %s)",
                     *key, latest[key]["excel_row"], row["excel_row"])
        latest[key] = row
    return list(latest.values())


def split_outliers(rows, history, rules):
    """Reject modal prices far from the median of the last N accepted prices (same market + crop)."""
    window = rules["outlier_window"]
    ratio = rules["outlier_ratio"]
    min_history = rules["outlier_min_history"]

    past = defaultdict(list)                  # (market, commodity) -> [(date, modal price)]
    for h in history:
        past[(h["market"], h["commodity"])].append((h["price_date"], float(h["modal_price_rs_qtl"])))

    kept, outliers = [], []
    for row in sorted(rows, key=lambda r: r["price_date"]):
        series = past[(row["market"], row["commodity"])]
        recent = sorted(p for p in series if p[0] < row["price_date"])[-window:]
        modal = row["modal_price_rs_qtl"]
        if len(recent) >= min_history:
            median = statistics.median(price for _, price in recent)
            if modal > median * ratio or modal < median / ratio:
                outliers.append({
                    "excel_row": row["excel_row"],
                    "reason": f"modal price {modal:.0f} is far from the recent median {median:.0f} "
                              f"(allowed: within x{ratio})",
                    "raw": row["raw"],
                })
                continue                      # an outlier never becomes history
        series.append((row["price_date"], modal))
        kept.append(row)
    return kept, outliers


def transform(rows, format_name, mappings, history=(), today=None):
    """Clean every row. history = earlier accepted prices from the database."""
    today = today or date.today()
    good, rejected = [], []
    for record in rows.to_dict("records"):
        if is_blank_row(record):
            continue
        try:
            clean = clean_price_row(record, format_name, mappings, today)
        except RowRejected as exc:
            rejected.append({"excel_row": record["excel_row"], "reason": str(exc), "raw": record["raw"]})
            continue
        clean["excel_row"] = record["excel_row"]
        clean["raw"] = record["raw"]
        good.append(clean)

    good = drop_duplicate_prices(good)
    good, outliers = split_outliers(good, history, mappings["rules"]["prices"])
    rejected.extend(outliers)
    return pd.DataFrame(good), pd.DataFrame(rejected)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    mappings = load_mappings()
    for path in list_inbox_files():
        try:
            sheet = read_sheet(path, mappings)
        except Exception:
            continue
        if sheet.file_type != "price":
            continue
        good, rejected = transform(sheet.rows, sheet.format_name, mappings)
        print(f"\n{path.name} ({sheet.format_name}): {len(good)} good, {len(rejected)} rejected")
        for r in rejected.itertuples():
            print(f"  rejected row {r.excel_row}: {r.reason}")