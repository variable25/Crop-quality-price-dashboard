"""
db.py - the database connection plus the 'diary' helpers (pipeline_runs, processed_files).
"""
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

from pipeline.config import load_db_settings

TABLES = ["pipeline_runs", "processed_files", "lab_results", "market_prices", "rejected_rows"]


def get_engine():
    s = load_db_settings()
    url = URL.create(
        drivername="postgresql+psycopg2",
        username=s["POSTGRES_USER"],
        password=s["POSTGRES_PASSWORD"],
        host=s["POSTGRES_HOST"],
        port=int(s["POSTGRES_PORT"]),
        database=s["POSTGRES_DB"],
    )
    return create_engine(url)


def start_run(engine):
    with engine.begin() as conn:
        return conn.execute(text("INSERT INTO pipeline_runs DEFAULT VALUES RETURNING run_id")).scalar_one()


def finish_run(engine, run_id, status, counts, error_message=None):
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE pipeline_runs
               SET finished_at = now(), status = :status,
                   files_seen = :files_seen, files_loaded = :files_loaded,
                   files_skipped = :files_skipped, files_failed = :files_failed,
                   rows_loaded = :rows_loaded, rows_rejected = :rows_rejected,
                   error_message = :error_message
             WHERE run_id = :run_id
        """), {"run_id": run_id, "status": status, "error_message": error_message, **counts})


def is_already_loaded(conn, file_hash):
    return conn.execute(text(
        "SELECT EXISTS (SELECT 1 FROM processed_files WHERE file_hash = :h AND status = 'loaded')"
    ), {"h": file_hash}).scalar_one()


def record_file(conn, run_id, file_name, file_hash, status, file_type=None, error_message=None):
    return conn.execute(text("""
        INSERT INTO processed_files (run_id, file_name, file_hash, file_type, status, error_message)
        VALUES (:run_id, :file_name, :file_hash, :file_type, :status, :error_message)
        RETURNING file_id
    """), {"run_id": run_id, "file_name": file_name, "file_hash": file_hash,
           "file_type": file_type, "status": status, "error_message": error_message}).scalar_one()


def update_file_counts(conn, file_id, rows_loaded, rows_rejected):
    conn.execute(text(
        "UPDATE processed_files SET rows_loaded = :loaded, rows_rejected = :rejected WHERE file_id = :id"
    ), {"loaded": rows_loaded, "rejected": rows_rejected, "id": file_id})


def load_price_history(engine):
    """All accepted prices so far: the memory the outlier check compares against."""
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT market, commodity, price_date, modal_price_rs_qtl FROM market_prices"
        )).mappings().all()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    engine = get_engine()
    with engine.connect() as conn:
        for table in TABLES:          # a fixed list in our code, never user input
            count = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
            print(f"{table:<16} {count} rows")