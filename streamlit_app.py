# STILL NEED TO FIX YPROFILING, NUMBA ERROR

from __future__ import annotations
import os
from typing import List, Optional
from dotenv import load_dotenv
load_dotenv()
import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine


# Configuration & caching helpers
DB_URL = os.getenv("DB_URL")
if DB_URL is None:
    st.error("DB_URL env var not set – e.g. postgresql+psycopg2://user:pass@host:5432/health")
    st.stop()

@st.cache_resource(show_spinner=False, hash_funcs={create_engine: id})
def _get_engine():
    return create_engine(DB_URL, pool_pre_ping=True)


# Data loader – resilient to empty clean_admissions
@st.cache_data(show_spinner=True)
def load_data() -> pd.DataFrame:
    """Return a tidy dataframe; fall back to staging if clean is empty."""
    with _get_engine().begin() as conn:
        df = pd.read_sql("SELECT * FROM clean_admissions", conn)
        if df.empty:
            st.warning("clean_admissions is empty – falling back to staging_admissions and aggregating on the fly …")
            staging = pd.read_sql("SELECT * FROM staging_admissions", conn)
            if staging.empty:
                return staging  # nothing we can do
            cats = [c for c in staging.columns if c not in {"year", "state", "separations"}]
            df = staging.groupby(["year", "state", *cats], as_index=False)["separations"].sum()

    rename_map = {}
    if "diagnosis" in df.columns and "principal_diagnosis" not in df.columns:
        rename_map["diagnosis"] = "principal_diagnosis"
    if "icd_chapter" in df.columns and "category" not in df.columns:
        rename_map["icd_chapter"] = "category"
    df = df.rename(columns=rename_map)

    # Ensure dtypes
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    df["separations"] = pd.to_numeric(df["separations"], errors="coerce")
    df = df.dropna(subset=["year", "state", "separations"]).reset_index(drop=True)
    return df


# Sidebar filters – now NULL‑safe
def sidebar_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.header("Filters 🧮")

    years = sorted(df["year"].dropna().unique())
    year_sel = st.sidebar.multiselect("Year", years, default=years)

    states = sorted(df["state"].dropna().unique())
    state_sel = st.sidebar.multiselect("State", states, default=states)

    mask = df["year"].isin(year_sel) & df["state"].isin(state_sel)

    # Dynamic categorical filters (ignore very sparse/high‑card columns)
    other_dims = [c for c in df.columns if c not in {"year", "state", "separations"}]
    for col in other_dims:
        uniq = sorted([v for v in df[col].dropna().unique() if v != ""])
        if 1 < len(uniq) < 50:
            sel = st.sidebar.multiselect(col.replace("_", " ").title(), uniq, default=uniq)
            # Only filter if the user removed at least one value
            if len(sel) != len(uniq):
                mask &= df[col].isin(sel)
    return df[mask]


# Insights generator
def generate_insights(df: pd.DataFrame) -> Optional[str]:
    if df.empty:
        return None

    top_state = (
        df.groupby("state", as_index=False)["separations"].sum()
          .sort_values("separations", ascending=False).iloc[0]
    )

    lines = [
        f"• **{top_state['state']}** shows the highest separations in the current view (~{int(top_state['separations']):,})."
    ]

    if "category" in df.columns:
        top_cat = (
            df.groupby("category", as_index=False)["separations"].sum()
              .sort_values("separations", ascending=False).iloc[0]
        )
        lines.append(f"• Leading category: **{top_cat['category']}** (~{int(top_cat['separations']):,}).")

    if df['year'].nunique() > 1:
        yr = df.groupby('year', as_index=False)['separations'].sum().sort_values('year')
        pct = (yr['separations'].iat[-1] - yr['separations'].iat[0]) / yr['separations'].iat[0] * 100
        trend = "increased" if pct > 0 else "decreased"
        lines.append(f"• Overall separations have **{trend} {abs(pct):.1f}%** from {yr['year'].iat[0]} to {yr['year'].iat[-1]}.")

    return "\n".join(lines)


# Plot helpers (guard against empty frames)
def plot_state_bar(df: pd.DataFrame):
    if df.empty:
        st.info("No data for bar chart.")
        return
    bar = df.groupby("state", as_index=False)["separations"].sum()
    fig = px.bar(bar, x="state", y="separations", text="separations", title="Total separations by state")
    st.plotly_chart(fig, use_container_width=True)


def plot_year_trend(df: pd.DataFrame):
    if df.empty:
        return
    trend = df.groupby(["year", "state"], as_index=False)["separations"].sum()
    fig = px.line(trend, x="year", y="separations", color="state", markers=True,
                  title="Year‑on‑year trend by state")
    st.plotly_chart(fig, use_container_width=True)


def plot_category_pie(df: pd.DataFrame):
    if "category" not in df.columns or df.empty:
        return
    pie_df = df.groupby("category", as_index=False)["separations"].sum().nlargest(10, "separations")
    fig = px.pie(pie_df, names="category", values="separations", title="Top 10 diagnosis categories")
    st.plotly_chart(fig, use_container_width=True)


def plot_heatmap(df: pd.DataFrame):
    if "category" not in df.columns or df.empty:
        st.info("Heatmap needs the *category* column.")
        return
    heat = df.groupby(["category", "state"], as_index=False)["separations"].sum()
    heat = heat.pivot(index="category", columns="state", values="separations")
    fig = px.imshow(heat, aspect="auto", color_continuous_scale="Blues", title="Category × State heatmap")
    st.plotly_chart(fig, use_container_width=True)


def plot_treemap(df: pd.DataFrame):
    if not {"category", "principal_diagnosis"}.issubset(df.columns) or df.empty:
        return
    tm = df.groupby(["category", "principal_diagnosis"], as_index=False)["separations"].sum()
    if tm.empty:
        return
    fig = px.treemap(tm, path=["category", "principal_diagnosis"], values="separations",
                     title="Principal diagnoses within each category")
    st.plotly_chart(fig, use_container_width=True)


# Streamlit main – includes a DEBUG expander
def main():
    st.set_page_config(page_title="AU Hospital Separations", layout="wide")
    st.title("🏥 Australian Hospital Separations Dashboard – DEBUG mode")

    df = load_data()
    if df.empty:
        st.error("Database tables are empty – run the ETL first.")
        st.stop()

    with st.expander("🔎 Raw data preview (first 5 rows)"):
        st.write("Columns:", df.columns.tolist())
        st.dataframe(df.head())

    filtered = sidebar_filters(df)

    st.markdown("### Hypotheses & Automatic Insights")
    st.markdown(
        """1. States with larger rural\/remote populations have **higher separation rates for preventable conditions**.  
2. **Mental & behavioural disorder** separations are growing faster than the national average.  
3. Hospitals serving SEIFA quintile 1‑2 catchments show **longer average stays**.

---
**Current data slice:**""")
    if (ins := generate_insights(filtered)):
        st.success(ins)
    else:
        st.info("No data in current slice – adjust filters.")

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Overview", "Heatmap", "Treemap", "Data table", "Profiling"])

    with tab1:
        col1, col2 = st.columns(2)
        with col1:
            plot_state_bar(filtered)
        with col2:
            plot_year_trend(filtered)
        st.divider()
        plot_category_pie(filtered)

    with tab2:
        plot_heatmap(filtered)

    with tab3:
        plot_treemap(filtered)

    with tab4:
        st.dataframe(filtered, use_container_width=True)

    with tab5:
        st.subheader("Pandas‑Profiling report")
        if st.button("Generate profiling report"):
            from ydata_profiling import ProfileReport
            from streamlit_pandas_profiling import st_profile_report
            st_profile_report(ProfileReport(filtered, title="Profiling", minimal=True))

if __name__ == "__main__":
    main()
