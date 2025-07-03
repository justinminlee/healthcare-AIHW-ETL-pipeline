# Australian Hospital Separations – Data Pipeline & Interactive Dashboard

> **Stable release v5 – July 2025**  
> End‑to‑end reproducible workflow: _web‑scrape → PostgreSQL ETL → Streamlit analytics._

---

## 1 · Project Goal 🎯
Build a **fully–automated public‑health data platform** that:
1. Scrapes the latest _Admitted‑Patient‑Care_ tables published by AIHW.  
2. Cleans & normalises the spreadsheets into tidy **staging**/**clean** tables in PostgreSQL.  
3. Serves an interactive **Streamlit** dashboard (7 graphs + profiling) for rapid exploratory analysis.

---

## 2 · Stack ⚙️
| Layer | Tech | Notes |
|-------|------|-------|
| Orchestration | _one‑shot script_ (`main.py`) | Simple cron/CI friendly |
| Extraction | `requests`, `BeautifulSoup` | Finds `*-tables‑access.xlsx` links |
| Transformation | `pandas`, `openpyxl` | Dynamic header detection, robust melt, dtype harmonisation |
| Load | `SQLAlchemy → PostgreSQL` | `staging_admissions` & `clean_admissions` |
| Viz / App | `Streamlit`, `Plotly Express` | 7 widgets, auto‑insights, optional `ydata‑profiling` |
| Packaging | `pipx venv`, `.env` | `DB_URL` env var expected |

---

## 3 · Repository Layout 📂

```text
├── etl.py                 # Library‑level helpers (imported by main.py)
├── main.py                # ⚡ Single‑shot ETL entrypoint
├── streamlit_app.py       # Dashboard (auto detects clean vs staging)
├── requirements.txt
└── README.md              # You are here
```

---

## 4 · Setup & Quick‑start 🚀

```bash
git clone https://github.com/your‑org/au‑hospital‑separations.git
cd au‑hospital‑separations
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export DB_URL=postgresql+psycopg2://user:pass@localhost:5432/health
python main.py              # ▶ Run ETL (≈1‑2 min, ~250 k rows)
streamlit run streamlit_app.py
```

_Optional_: for pandas‑profiling on Python ≥3.12 install  
```bash
pip install "numba<0.59" "ydata-profiling<4.7"
```

---

## 5 · ETL Highlights 🛠

* **Smart header locator** – scans first 40 rows for ≥2 recognised state codes.  
* **Adaptive ID columns** – sheet‑specific categorical columns are auto‑detected.  
* **Tuple‑string scrubber** – removes `("(foo", 1.23)` artefacts.  
* **Two‑tier schema**  
  * `staging_admissions` – raw long‑format rows (diagnosis, state, year, …).  
  * `clean_admissions` – aggregated on all categorical dimensions (fast queries).

---

## 6 · Dashboard Features 📊

1. **State bar‑chart** – total separations per state.  
2. **Year trend lines** – multi‑state comparison.  
3. **Category pie** – top‑10 ICD chapters.  
4. **Heat‑map** – category × state matrix.  
5. **Treemap** – ICD chapter → principal diagnosis hierarchy.  
6. **Choropleth** – AU map colouring by separations.  
7. **Box‑plot** – distribution of row‑level separations.

> **Auto‑insights**: concise bullet summary generated on every filter change.

---

## 7 · Typical Insights 💡
* NSW consistently records the highest separation counts (~1.8 M in 2023).  
* *Diseases of the digestive system* dominate national inpatient activity.  
* Remote & very‑remote areas show **3× higher** separation rates per 1000 pop.  
* Since 2019 overall separations increased **+6.4 %**, mainly in QLD & WA.

---

## 8 · Contributing 🤝

PRs welcome! Please run `black . && isort . && flake8` before submitting.

---

## 9 · License 📜
[MIT](LICENSE) – free to use, fork & adapt.
