#!/usr/bin/env python3
"""End‑to‑end ETL for AIHW Admitted Patient Care (Reasons for care) tables.

Usage (environment variables preferred):
    python etl_pipeline.py --db-url postgresql+psycopg2://user:pass@host/db
    python etl_pipeline.py --sqlite-path data/health.db

If neither --db-url nor --sqlite-path is provided the script will attempt to
read DB_URL / SQLITE_PATH from the environment.
"""
from __future__ import annotations
import argparse
import io
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, text

###############################################################################
# Config & helpers
###############################################################################
AIHW_BASE = "https://www.aihw.gov.au"
AIHW_PAGE = (
    "https://www.aihw.gov.au/reports-data/myhospitals/separations/table"
    "s"  # landing page listing the Excel files
)

ICD_CHAPTER_MAP = {
    **{c: "A–B: Infectious" for c in list("AB")},
    **{c: "C–D: Neoplasms" for c in list("CD")},
    # ... extend mapping as needed
}


def find_latest_xlsx_url() -> tuple[str, int]:
    """Scrape AIHW page and return (download_url, year)."""
    resp = requests.get(AIHW_PAGE, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    link = soup.find("a", href=re.compile(r"tables-reasons-for-care.*\.xlsx$"))
    if not link:
        raise RuntimeError("Could not locate .xlsx link on AIHW page")
    url = AIHW_BASE + link["href"]
    m = re.search(r"(20\d{2})-?(\d{2})?", url)
    year = int(m.group(1)) if m else datetime.year
    return url, year


def parse_excel(content: bytes, year: int) -> pd.DataFrame:
    """Return a tidy DataFrame ready for DB insert."""
    df = pd.read_excel(io.BytesIO(content), sheet_name="Table 1", skiprows=3)
    df = df.rename(columns=lambda c: c.strip())
    df = df[df["State"] == "QLD"]  # keep QLD only to reduce volume

    # Standardise columns
    df = df.rename(columns={
        "Principal diagnosis (ICD-10-AM 3-character code)": "icd3",
        "Separations": "separations",
        "Age group": "age_group",
        "Sex": "sex",
        "Same-day": "same_day",
        "State": "state",
    })

    df["year"] = year
    df["icd_chapter"] = df["icd3"].str[0].map(ICD_CHAPTER_MAP).fillna("Other")
    df = df[[
        "year", "state", "icd3", "icd_chapter", "age_group", "sex", "separations"
    ]]
    return df


def upsert(engine, df: pd.DataFrame, table: str = "staging_admissions") -> None:
    """Insert data using COPY‑like multi‑row inserts."""
    # Create table if not exists
    ddl = text(
        """
        CREATE TABLE IF NOT EXISTS staging_admissions (
            year        INTEGER,
            state       CHAR(3),
            icd3        CHAR(3),
            icd_chapter TEXT,
            age_group   TEXT,
            sex         TEXT,
            separations INTEGER,
            PRIMARY KEY(year, state, icd3, age_group, sex)
        )
        """
    )
    with engine.begin() as conn:
        conn.execute(ddl)
        df.to_sql(table, conn, if_exists="append", index=False, method="multi")


###############################################################################
# Main CLI
###############################################################################

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run AIHW ETL")
    parser.add_argument("--db-url", help="SQLAlchemy URL")
    parser.add_argument("--sqlite-path", help="SQLite file path")
    parser.add_argument("--url", help="Override AIHW xlsx URL")
    args = parser.parse_args(argv)

    db_url = args.db_url or os.getenv("DB_URL")
    if not db_url and args.sqlite_path:
        db_url = f"sqlite:///{args.sqlite_path}"
    if not db_url:
        print("No DB connection string supplied", file=sys.stderr)
        sys.exit(1)

    engine = create_engine(db_url)

    url, year = (args.url, datetime.utcnow().year) if args.url else find_latest_xlsx_url()
    print(f"Downloading {url}…")
    content = requests.get(url, timeout=60).content
    print("Parsing Excel…")
    tidy = parse_excel(content, year)
    print(f"Rows to insert: {len(tidy):,}")
    upsert(engine, tidy)
    print("✓ ETL completed")


if __name__ == "__main__":
    main()
