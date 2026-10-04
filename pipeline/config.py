"""
config.py - settings in one place: folder paths, the database login (.env)
and the mappings (config/mappings.yaml).
"""
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from pipeline.clean import normalize_key

BASE_DIR = Path(__file__).resolve().parent.parent      # the project folder
DATA_DIR = BASE_DIR / "data"
INBOX_DIR = DATA_DIR / "inbox"
PROCESSED_DIR = DATA_DIR / "processed"
FAILED_DIR = DATA_DIR / "failed"
LOG_DIR = BASE_DIR / "logs"
MAPPINGS_FILE = BASE_DIR / "config" / "mappings.yaml"

DB_VARS = ["POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "POSTGRES_HOST", "POSTGRES_PORT"]


def load_db_settings():
    """Database login from .env. Stops with a clear message if anything is missing."""
    load_dotenv(BASE_DIR / ".env")
    missing = [name for name in DB_VARS if not os.getenv(name)]
    if missing:
        sys.exit(f"Missing in .env: {', '.join(missing)}")
    return {name: os.getenv(name) for name in DB_VARS}


def load_mappings(path=MAPPINGS_FILE):
    """Read mappings.yaml and turn it into lookup tables with normalized keys."""
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    formats = {}
    for name, fmt in raw["formats"].items():
        headers = {}
        for standard, aliases in fmt["columns"].items():
            for alias in aliases:
                headers[normalize_key(alias)] = standard
        formats[name] = {
            "file_type": fmt["file_type"],
            "unit_multiplier": fmt.get("unit_multiplier", 1),
            "headers": headers,
        }

    return {
        "formats": formats,
        "commodities": {normalize_key(k): v for k, v in raw["commodity_synonyms"].items()},
        "markets": {normalize_key(k): v for k, v in raw["market_synonyms"].items()},
        "market_districts": raw["market_districts"],
        "below_detection": {normalize_key(v) for v in raw["values"]["below_detection"]},
        "empty_values": {normalize_key(v) for v in raw["values"]["empty"]},
        "date_formats": raw["date_formats"],
        "rules": raw["rules"],
    }


if __name__ == "__main__":
    mappings = load_mappings()
    for name, fmt in mappings["formats"].items():
        print(f"format {name:<10} type={fmt['file_type']:<6} known headers={len(fmt['headers']):<3} "
              f"unit x{fmt['unit_multiplier']}")
    print(f"commodity synonyms: {len(mappings['commodities'])}")
    print(f"market synonyms:    {len(mappings['markets'])}")
    db = load_db_settings()
    print(f"database:           {db['POSTGRES_USER']}@{db['POSTGRES_HOST']}:{db['POSTGRES_PORT']}/{db['POSTGRES_DB']}")