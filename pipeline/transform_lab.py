"""
transform_lab.py - messy lab rows in, (clean rows, rejected rows) out.
"""
import logging
from datetime import date

import pandas as pd

from pipeline.clean import (RowRejected, clean_id, clean_text, date_or_reject, is_below_detection,
                            is_blank_row, lookup_or_reject, number_or_reject)
from pipeline.config import load_mappings
from pipeline.extract import list_inbox_files, read_sheet

log = logging.getLogger(__name__)

PERCENT_COLUMNS = ["moisture_pct", "oil_pct", "foreign_matter_pct"]


def clean_lab_row(record, mappings, today):
    """Return one clean lab row (a dict). Raises RowRejected with the reason if a hard rule fails."""
    empty = mappings["empty_values"]

    sample_id = clean_id(record.get("sample_id"))
    if sample_id is None:
        raise RowRejected("sample_id is missing")

    commodity = lookup_or_reject(record.get("commodity"), "commodity", mappings["commodities"])

    test_date = date_or_reject(record.get("test_date"), "test_date", mappings["date_formats"], empty)
    if test_date is None:
        raise RowRejected("test_date is missing")
    if test_date > today:
        raise RowRejected(f"test_date {test_date} is in the future")

    clean = {
        "sample_id": sample_id,
        "commodity": commodity,
        "test_date": test_date,
        "batch_no": clean_text(record.get("batch_no")),
        "remarks": clean_text(record.get("remarks")),
    }

    for column in PERCENT_COLUMNS:
        value = number_or_reject(record.get(column), column, empty)
        if value is not None and not 0 <= value <= 100:
            raise RowRejected(f"{column} {value} is outside 0-100")
        clean[column] = value

    raw_afla = record.get("aflatoxin_ppb")
    if is_below_detection(raw_afla, mappings["below_detection"]):
        clean["aflatoxin_ppb"] = None                 # not measured, so NOT zero
        clean["aflatoxin_below_detection"] = True
    else:
        value = number_or_reject(raw_afla, "aflatoxin_ppb", empty)
        if value is not None and value < 0:
            raise RowRejected(f"aflatoxin_ppb {value} is negative")
        clean["aflatoxin_ppb"] = value
        clean["aflatoxin_below_detection"] = False

    notes = [f"{column} {clean[column]} is above the usual {limit}"
             for column, limit in mappings["rules"]["lab"]["review_above"].items()
             if clean.get(column) is not None and clean[column] > limit]
    clean["needs_review"] = bool(notes)
    clean["review_note"] = "; ".join(notes) or None
    return clean


def keep_latest_per_sample(df):
    """One row per sample_id: a retest replaces the older test, exact duplicates collapse."""
    if df.empty:
        return df
    df = df.sort_values(["sample_id", "test_date", "excel_row"])
    for row in df[df.duplicated("sample_id", keep="last")].itertuples():
        log.info("sample %s: dropped Excel row %s (older test or duplicate)", row.sample_id, row.excel_row)
    return df.drop_duplicates("sample_id", keep="last")


def transform(rows, mappings, today=None):
    """Clean every row. Returns (good DataFrame, rejected DataFrame)."""
    today = today or date.today()
    good, rejected = [], []
    for record in rows.to_dict("records"):
        if is_blank_row(record):
            continue                                  # blank rows are dropped silently
        try:
            clean = clean_lab_row(record, mappings, today)
        except RowRejected as exc:
            rejected.append({"excel_row": record["excel_row"], "reason": str(exc), "raw": record["raw"]})
            continue
        clean["excel_row"] = record["excel_row"]
        good.append(clean)
    return keep_latest_per_sample(pd.DataFrame(good)), pd.DataFrame(rejected)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    mappings = load_mappings()
    for path in list_inbox_files():
        try:
            sheet = read_sheet(path, mappings)
        except Exception:
            continue                                  # the broken file; extract.py already showed it
        if sheet.file_type != "lab":
            continue
        good, rejected = transform(sheet.rows, mappings)
        print(f"\n{path.name}: {len(good)} good, {len(rejected)} rejected")
        for r in rejected.itertuples():
            print(f"  rejected row {r.excel_row}: {r.reason}")
        if not good.empty:
            for r in good[good["needs_review"]].itertuples():
                print(f"  review {r.sample_id}: {r.review_note}")