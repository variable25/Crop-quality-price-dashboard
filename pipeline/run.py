"""
run.py - run the whole pipeline once:   python -m pipeline.run
"""
import logging
import shutil
import sys
from datetime import datetime

from pipeline import db, extract, load, transform_lab, transform_prices
from pipeline.config import FAILED_DIR, INBOX_DIR, LOG_DIR, PROCESSED_DIR, load_mappings

log = logging.getLogger("pipeline")
TARGET_TABLE = {"lab": "lab_results", "price": "market_prices"}


def setup_logging():
    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(),
                  logging.FileHandler(LOG_DIR / "pipeline.log", encoding="utf-8")],
    )


def move_file(path, folder):
    """Move a finished file out of the inbox. Never overwrite: add a timestamp if the name exists."""
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / path.name
    if target.exists():
        target = folder / f"{path.stem}_{datetime.now():%Y%m%d_%H%M%S}{path.suffix}"
    shutil.move(str(path), str(target))


def process_file(engine, run_id, path, mappings, counts):
    log.info("--- %s", path.name)
    fingerprint = extract.file_hash(path)

    with engine.begin() as conn:
        duplicate = db.is_already_loaded(conn, fingerprint)
        if duplicate:
            db.record_file(conn, run_id, path.name, fingerprint, "skipped_duplicate")
    if duplicate:
        log.info("skipped: identical content was already loaded (hash %s...)", fingerprint[:12])
        counts["files_skipped"] += 1
        move_file(path, PROCESSED_DIR)
        return

    try:
        sheet = extract.read_sheet(path, mappings)
        log.info("format %s, header on Excel row %s, %s rows",
                 sheet.format_name, sheet.header_row, len(sheet.rows))
        if sheet.file_type == "lab":
            good, rejected = transform_lab.transform(sheet.rows, mappings)
        else:
            history = db.load_price_history(engine)
            good, rejected = transform_prices.transform(sheet.rows, sheet.format_name, mappings, history)
        table = TARGET_TABLE[sheet.file_type]

        with engine.begin() as conn:          # one file = one transaction: all or nothing
            file_id = db.record_file(conn, run_id, path.name, fingerprint, "loaded", sheet.file_type)
            loaded = load.upsert(conn, table, good, file_id)
            n_rejected = load.load_rejected(conn, rejected, table, file_id)
            db.update_file_counts(conn, file_id, loaded, n_rejected)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:500]
        log.error("FAILED: %s", error)
        with engine.begin() as conn:
            db.record_file(conn, run_id, path.name, fingerprint, "failed", error_message=error)
        counts["files_failed"] += 1
        move_file(path, FAILED_DIR)
        return

    log.info("loaded %s rows, rejected %s", loaded, n_rejected)
    counts["files_loaded"] += 1
    counts["rows_loaded"] += loaded
    counts["rows_rejected"] += n_rejected
    move_file(path, PROCESSED_DIR)


def main():
    setup_logging()
    mappings = load_mappings()
    engine = db.get_engine()
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    files = extract.list_inbox_files(INBOX_DIR)

    counts = {"files_seen": len(files), "files_loaded": 0, "files_skipped": 0,
              "files_failed": 0, "rows_loaded": 0, "rows_rejected": 0}
    run_id = db.start_run(engine)
    log.info("run %s started: %s file(s) in %s", run_id, len(files), INBOX_DIR)

    try:
        for path in files:
            process_file(engine, run_id, path, mappings, counts)
    except Exception as exc:
        log.exception("run %s crashed", run_id)
        db.finish_run(engine, run_id, "failed", counts, error_message=str(exc)[:500])
        return 1

    if counts["files_failed"] == 0:
        status = "success"
    elif counts["files_loaded"] + counts["files_skipped"] > 0:
        status = "partial"
    else:
        status = "failed"
    db.finish_run(engine, run_id, status, counts)
    log.info("run %s finished: %s | %s", run_id, status, counts)
    return 0 if status == "success" else 1


if __name__ == "__main__":
    sys.exit(main())