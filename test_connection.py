"""Check that python can reach the Postgres container using the settings in .env"""
import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import OperationalError

REQUIRED_VARS = [
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "POSTGRES_HOST",
    "POSTGRES_PORT"
]

def load_settings():
    """Read .env and stop with a clear message if anything is missing"""
    load_dotenv()
    missing = [name for name in REQUIRED_VARS if not os.getenv(name)]
    if missing:
        sys.exit(f"Missing in .env: {','.join(missing)}")
    settings = {name: os.getenv(name) for name in REQUIRED_VARS}
    return settings

def build_engine(settings):
    """Build the connection URL safely (handles special characters in passwords)"""
    url = URL.create(
        drivername="postgresql+psycopg2",
        username=settings["POSTGRES_USER"],
        password=settings["POSTGRES_PASSWORD"],
        host=settings["POSTGRES_HOST"],
        port=int(settings["POSTGRES_PORT"]),
        database=settings["POSTGRES_DB"],
    )
    return create_engine(url)

def main():
    settings = load_settings()
    engine = build_engine(settings)
    '''This is a context manager, helps use conn.close() without explicitly mentioning it'''
    try:
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version()")).scalar()
            db, user = conn.execute(text("SELECT current_database(), current_user")).one()
    except OperationalError as exc:
        sys.exit(f"Could not connect to Postgres:\n{exc.orig}")
    finally:
        engine.dispose()

    print("Connected!")
    print(f" database: {db}")
    print(f" user:      {user}")
    print(f" server:    {version}")

if __name__ == '__main__':
    main()