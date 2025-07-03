from __future__ import annotations
import io
import os
import re
from typing import List
from dotenv import load_dotenv
load_dotenv()
import pandas as pd
import requests
from bs4 import BeautifulSoup
from sqlalchemy import create_engine

# Globals
ROOT_URL = (
    "https://www.aihw.gov.au/reports-data/myhospitals/separations/tables"
)
FALLBACK_LINKS = [
    "https://www.aihw.gov.au/getmedia/04e116a4-f579-4cd5-bbaf-b3fa6256ea45/4-admitted-patient-care-2022-23-tables-access.xlsx",
]
STATE_CODES = ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT", "AUST"]
HEADERS = {"User-Agent": "Mozilla/5.0"}


# Discover Excel workbooks
def discover_excels() -> List[str]:
    try:
        html = requests.get(ROOT_URL, headers=HEADERS, timeout=30).text
    except Exception:
        html = ""
    links: list[str] = []
    if html:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.endswith("tables-access.xlsx") and "admitted-patient-care" in href:
                links.append(
                    "https://www.aihw.gov.au" + href if href.startswith("/") else href
                )
    return links or FALLBACK_LINKS

# Regex & cleaners
def _norm_state(cell) -> str | None:
    """Strip everything except A‑Z then check against known state codes."""
    s = re.sub(r"[^A-Z]", "", str(cell).upper())
    return s if s in STATE_CODES else None


def _header_row(df: pd.DataFrame) -> int | None:
    """Return first row that contains ≥2 recognised state codes."""
    for i in range(min(40, len(df))):
        if sum(1 for v in df.iloc[i] if _norm_state(v)) >= 2:
            return i
    return None

_rx_tuple1 = re.compile(r'^\("?\s*')
_rx_tuple2 = re.compile(r'"?\)$')
_rx_tuple3 = re.compile(r',\s*[-+]?[0-9]*\.?[0-9]+$')


def _clean_text(series: pd.Series) -> pd.Series:  # noqa: N802
    return (
        series.astype(str)
        .str.replace(_rx_tuple1, "", regex=True)
        .str.replace(_rx_tuple2, "", regex=True)
        .str.replace(_rx_tuple3, "", regex=True)
        .str.strip()
        .str.strip('"')
    )


# Parse one sheet into tidy long‑form
def parse_sheet(xls: pd.ExcelFile, sheet: str, year: int) -> pd.DataFrame | None:
    raw = pd.read_excel(xls, sheet_name=sheet, header=None, engine="openpyxl")
    hdr = _header_row(raw)
    if hdr is None:
        return None

    df = pd.read_excel(xls, sheet_name=sheet, header=hdr, engine="openpyxl")
    df = df.loc[:, ~df.columns.duplicated()]

    id_cols: list[str] = []
    state_cols: list[str] = []
    rename: dict[str, str] = {}
    for c in df.columns:
        st = _norm_state(c)
        if st:
            rename[c] = st
            state_cols.append(st)
        else:
            safe = str(c).strip().lower().replace(" ", "_")
            rename[c] = safe
            id_cols.append(safe)
    df = df.rename(columns=rename)

    # First unnamed column → category
    if id_cols and id_cols[0].startswith("unnamed"):
        df = df.rename(columns={id_cols[0]: "category"})
        id_cols[0] = "category"

    # Second unnamed column (if present) → principal_diagnosis
    for idx, col in enumerate(id_cols[1:], start=1):
        if col.startswith("unnamed"):
            if "principal_diagnosis" not in df.columns:
                new_name = "principal_diagnosis"
            else:
                new_name = f"dimension_{idx}"
            df = df.rename(columns={col: new_name})
            id_cols[idx] = new_name

    # Drop rate/helper column "total"
    if "total" in df.columns:
        df = df.drop(columns=["total"])
        id_cols = [c for c in id_cols if c != "total"]

    if len(state_cols) < 2 or not id_cols:
        return None

    df = df.dropna(subset=[id_cols[0]])

    for col in id_cols:
        df[col] = _clean_text(df[col])

    for st in state_cols:
        df[st] = pd.to_numeric(df[st], errors="coerce")

    tidy = (
        df.melt(id_vars=id_cols, value_vars=state_cols, var_name="state", value_name="separations")
        .dropna(subset=["separations"])
    )
    tidy["year"] = year
    return tidy


# Compile all workbooks
def compile_all() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for url in discover_excels():
        print("📥", url.split("/")[-1])
        data = requests.get(url, headers=HEADERS, timeout=60).content
        xls = pd.ExcelFile(io.BytesIO(data), engine="openpyxl")
        m = re.search(r"(\d{4})-(\d{2})", url)
        year = int(m.group(2)) + 2000 if m else 9999
        for sht in [s for s in xls.sheet_names if re.match(r"Table\s*[45S]", s, re.I)]:
            df = parse_sheet(xls, sht, year)
            if df is not None and not df.empty:
                frames.append(df)
    if not frames:
        raise RuntimeError("❌ No valid data extracted – parsing rules may need an update.")
    tidy = pd.concat(frames, ignore_index=True)
    print(f"✅ Compiled {len(tidy):,} rows")
    return tidy


# Load to PostgreSQL
def load(df: pd.DataFrame, db_url: str):
    eng = create_engine(db_url, pool_pre_ping=True)
    with eng.begin() as conn:
        df.to_sql("staging_admissions", conn, if_exists="replace", index=False, method="multi")

        cats = [c for c in df.columns if c not in {"year", "state", "separations"} and df[c].notna().any()]
        df_filled = df.copy()
        df_filled[cats] = df_filled[cats].fillna("")

        agg = df_filled.groupby(["year", "state", *cats], as_index=False)["separations"].sum()
        agg.to_sql("clean_admissions", conn, if_exists="replace", index=False, method="multi")


# Main
if __name__ == "__main__":
    DB_URL = os.getenv("DB_URL")
    if not DB_URL:
        raise SystemExit("Set DB_URL env var – e.g. postgresql+psycopg2://user:pass@localhost:5432/health")

    tidy_df = compile_all()
    load(tidy_df, DB_URL)
    print("🎉 ETL finished – staging & clean tables updated.")
