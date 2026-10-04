"""
check_answer_key.py - did the pipeline handle every planted issue?
Run after the pipeline:   python -m pipeline.check_answer_key
"""
import csv
import sys

from sqlalchemy import text

from pipeline.config import DATA_DIR
from pipeline.db import get_engine

ANSWER_KEY = DATA_DIR / "answer_key.csv"

LATEST_FILES_SQL = """
    SELECT DISTINCT ON (file_name) file_id, file_name, status
      FROM processed_files
     ORDER BY file_name, (status = 'loaded') DESC, file_id DESC
"""
SPOT_CHECKS = [
    ("ND/BDL/<LOD stored as NULL + flag",
     "SELECT count(*) > 0 FROM lab_results WHERE aflatoxin_below_detection AND aflatoxin_ppb IS NULL"),
    ("trader prices converted kg -> quintal",
     "SELECT count(*) = 0 FROM market_prices WHERE source = 'trader' AND modal_price_rs_qtl < 1000"),
    ("exactly one lab row flagged for review",
     "SELECT count(*) = 1 FROM lab_results WHERE needs_review"),
]


def expects_rejection(expected):
    e = expected.lower()
    return e.startswith("reject") or "rejected_rows" in e or "then reject" in e


def main():
    engine = get_engine()
    with engine.connect() as conn:
        files = {r.file_name: r for r in conn.execute(text(LATEST_FILES_SQL))}
        rejected = {(r.source_file_id, r.excel_row): r.reason for r in conn.execute(
            text("SELECT source_file_id, excel_row, reason FROM rejected_rows"))}
        spot_results = [(label, conn.execute(text(sql)).scalar_one()) for label, sql in SPOT_CHECKS]

    with open(ANSWER_KEY, newline="", encoding="utf-8") as f:
        key = list(csv.DictReader(f))

    passed = 0
    expected_rejections = set()
    for item in key:
        name, row, expected = item["file"], item["excel_row"], item["expected_handling"]
        file = files.get(name)
        if file is None:
            ok, detail = False, "file was never processed"
        elif item["column"] == "(file)":
            want = "failed" if "failed" in expected.lower() else "skipped_duplicate"
            ok, detail = file.status == want, f"status {file.status} (expected {want})"
        elif row.isdigit():
            should_reject = expects_rejection(expected)
            reason = rejected.get((file.file_id, int(row)))
            if should_reject:
                expected_rejections.add((file.file_id, int(row)))
            ok = should_reject == (reason is not None)
            detail = f"rejected: {reason}" if reason else "kept / not rejected"
        else:
            ok, detail = file.status == "loaded", f"file status {file.status}"
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'}  {name[:38]:<38} row {row:<13} {detail[:70]}")

    latest_ids = {f.file_id for f in files.values()}
    unexpected = [k for k in rejected if k[0] in latest_ids and k not in expected_rejections]

    print(f"\nAnswer key: {passed}/{len(key)} passed")
    print(f"Unexpected rejections (good rows thrown away): {len(unexpected)}")
    for file_id, row in unexpected:
        print(f"  file_id {file_id}, row {row}: {rejected[(file_id, row)]}")
    print("\nSpot checks:")
    for label, ok in spot_results:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")

    all_good = passed == len(key) and not unexpected and all(ok for _, ok in spot_results)
    return 0 if all_good else 1


if __name__ == "__main__":
    sys.exit(main())