"""
load.py - write clean rows through a staging table (upsert) and park rejected rows.
"""
import json

from sqlalchemy import text

from pipeline.clean import is_missing

LAB_COLUMNS = ["sample_id", "commodity", "batch_no", "test_date", "moisture_pct", "oil_pct",
               "foreign_matter_pct", "aflatoxin_ppb", "aflatoxin_below_detection",
               "needs_review", "review_note", "remarks", "source_file_id"]
PRICE_COLUMNS = ["price_date", "market", "district", "commodity", "variety", "grade",
                 "min_price_rs_qtl", "max_price_rs_qtl", "modal_price_rs_qtl", "source", "source_file_id"]

TABLES = {
    "lab_results": {
        "columns": LAB_COLUMNS,
        "key": ["sample_id"],
        "only_if": "EXCLUDED.test_date >= lab_results.test_date",   # never overwrite a newer test
    },
    "market_prices": {
        "columns": PRICE_COLUMNS,
        "key": ["market", "commodity", "price_date"],
        "only_if": None,
    },
}


def to_records(df, columns):
    """DataFrame -> list of plain dicts, with NaN turned into None (NULL in the database)."""
    return [{c: (None if is_missing(v) else v) for c, v in rec.items()}
            for rec in df[columns].to_dict("records")]


def upsert(conn, table, df, file_id):
    """Copy rows into a temporary staging table, then insert-or-update the real table in one go."""
    if df.empty:
        return 0
    spec = TABLES[table]
    columns = spec["columns"]
    col_list = ", ".join(columns)
    stage = f"stage_{table}"
    df = df.assign(source_file_id=file_id)

    # 1. Staging: same column types as the real table, no rules, dropped automatically at commit
    conn.execute(text(f"CREATE TEMP TABLE {stage} ON COMMIT DROP AS "
                      f"SELECT {col_list} FROM {table} WITH NO DATA"))
    placeholders = ", ".join(f":{c}" for c in columns)
    conn.execute(text(f"INSERT INTO {stage} ({col_list}) VALUES ({placeholders})"),
                 to_records(df, columns))

    # 2. Upsert: insert new rows, update existing ones (matched on the natural key)
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in columns if c not in spec["key"])
    sql = (f"INSERT INTO {table} ({col_list}) SELECT {col_list} FROM {stage} "
           f"ON CONFLICT ({', '.join(spec['key'])}) DO UPDATE SET {updates}, loaded_at = now()")
    if spec["only_if"]:
        sql += f" WHERE {spec['only_if']}"
    return conn.execute(text(sql)).rowcount


def load_rejected(conn, df, target_table, file_id):
    """Store bad rows with their reason and the original cells (as JSON)."""
    if df.empty:
        return 0
    records = [{
        "source_file_id": file_id,
        "target_table": target_table,
        "excel_row": int(r["excel_row"]),
        "reason": r["reason"],
        "raw_data": json.dumps(r["raw"], default=str),     # default=str turns dates into text
    } for r in df.to_dict("records")]
    conn.execute(text("""
        INSERT INTO rejected_rows (source_file_id, target_table, excel_row, reason, raw_data)
        VALUES (:source_file_id, :target_table, :excel_row, :reason, CAST(:raw_data AS JSONB))
    """), records)
    return len(records)