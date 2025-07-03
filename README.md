# Australian Hospital Separations ETL & Streamlit Dashboard

## Overview
This project delivers a **fully‑automated data pipeline** that downloads publicly‑available hospital‑separation tables from the Australian Institute of Health & Welfare (AIHW), cleans and normalises them into a relational schema, and then serves an **interactive Streamlit dashboard** with rich visual analytics and auto‑generated insights.

* **ETL (Python)** – Web‑scrapes/ingests Excel workbooks, detects headers on the fly, removes noise, converts values to numeric, and writes two tables to PostgreSQL:
  * `staging_admissions`   ↳ raw tidy rows
  * `clean_admissions`    ↳ aggregated by every categorical dimension
* **Analytics (Streamlit)** – When you launch the app it pulls from `clean_admissions` (or falls back to `staging_admissions` if the former is empty) and renders **7 production‑ready visuals** (bar, line, pie, heat‑map, treemap, choropleth, box‑plot) plus key‑takeaway text.
* **Optional Data‑Profiling** – A one‑click pandas‑profiling report for deeper EDA (gracefully skipped if the `numba`/`visions` dependency chain fails under Python 3.12).

## Features
- 📥 **Robust Extraction** – Dynamic header detection; supports new AIHW workbook versions without code edits.
- 🧹 **Smart Transformation** – Auto‑deduplicates column names, harmonises categories, coerces numeric types.
- 🗄 **PostgreSQL Load** – Idempotent writes using SQLAlchemy with automatic upserts.
- 📊 **Interactive Dashboard** – Sidebar filters on every categorical column, real‑time Plotly charts, AUS map.
- 🗒 **Insight Generator** – Tiny NLP summary highlights top states, categories, YoY change.
- 🧮 **Optional Profiling** – Generates an HTML report inside Streamlit.

## Prerequisites
| Tool | Version | Notes |
|------|---------|-------|
| **Python** | 3.9 – 3.11 recommended | 3.12 works but skip profiling or pin `numba<0.59` |
| **PostgreSQL** | ≥ 12 | Any connection string supported by SQLAlchemy |
| **AIHW Access** | None | Data is public; no API key required |

## Installation
```bash
# 1 — Clone
git clone https://github.com/your‑org/aihw‑hospital‑etl.git
cd aihw‑hospital‑etl

# 2 — Virtual‑env
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3 — Dependencies
pip install -r requirements.txt

# 4 — Environment
cp .env.example .env  # then edit
```
### .env
```
DB_URL=postgresql+psycopg2://user:pass@localhost:5432/health
```

## Initialising the Database
No manual DDL is needed; the ETL script will create both tables if they do not exist. Optionally seed permissions & indices with `schema.sql`.

## Usage
### 1. Run the ETL
```bash
python etl.py
# ➜ Extracted 314 672 rows – loading …
# ✅ ETL completed.
```
### 2. Launch the Dashboard
```bash
streamlit run streamlit_app.py
```
The app opens at <http://localhost:8501>.

## Project Structure
```
aihw‑hospital‑etl/
├── etl.py              # Extract‑Transform‑Load pipeline
├── streamlit_app.py    # Dashboard & insights
├── requirements.txt    # Python dependencies
├── .env.example        # Env vars template
├── schema.sql          # Optional indices / grants
└── README.md           # This file
```

## Data Model
### staging_admissions
| Column | Type | Description |
|--------|------|-------------|
| `year` | INT | Financial year (e.g. 2023) |
| `state` | TEXT | AUS state code (NSW, VIC …) |
| `category` | TEXT | ICD‑10 chapter or other grouping |
| `principal_diagnosis` | TEXT | Detailed diagnosis (if available) |
| _…dynamic dims…_ | TEXT | Other categorical dimensions (care_type, etc.) |
| `separations` | NUMERIC | Rate per 1 000 population |

### clean_admissions
Same columns but **aggregated** (`GROUP BY year, state, *all categoricals* → SUM(separations)`).

## Running in Production
- **Scheduler**: Hook `python etl.py` in cron/Airflow for monthly refresh.
- **Docker**: Copy the sample `Dockerfile`/`docker‑compose.yml` for containerised deployment.
- **Metrics**: The app logs to stdout; pair with Prometheus/Grafana if needed.

## Troubleshooting
| Issue | Fix |
|-------|-----|
| "DB_URL env var not set" | Export `DB_URL` or add to `.env`. |
| Duplicate columns error | ETL now auto‑dedups; re‑run ETL. |
| Profiling fails under Py 3.12 | `pip install "numba<0.59"` or un‑tick the profiling button. |

## Future Enhancements
- Auto‑download GeoJSON for precise choropleth maps.
- Great Expectations data‑validation checkpoints.
- CI/CD workflow (GitHub Actions) to lint, test, and deploy.

## License
MIT

## Acknowledgements
* **AIHW** – Source of open hospital‑separation data.
* **Streamlit & Plotly** – Rapid interactive visualisation.
* **pandas‑profiling** – Quick EDA inside the browser.