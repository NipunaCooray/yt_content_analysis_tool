from __future__ import annotations

import pandas as pd
import streamlit as st

from components.navigation import page_header, render_context_sidebar, require_study
from db import crud
from db.database import get_session
from utils.constants import QUERY_CATEGORIES, STATES_TERRITORIES
from utils.validators import validate_query_fields

db = get_session()
current_study, current_reviewer = render_context_sidebar(db)

page_header("Search strategy", "Define the reproducible set of search queries for this study.")

if not require_study(current_study):
    db.close()
    st.stop()

study_id = current_study.id

tab_add, tab_manage, tab_import = st.tabs(["Add query", "Manage queries", "Bulk import (CSV)"])

with tab_add:
    with st.form("add_query_form", clear_on_submit=True):
        query_text = st.text_input("Query text*")
        col1, col2 = st.columns(2)
        category = col1.selectbox("Category", QUERY_CATEGORIES, index=0)
        state_territory = col2.selectbox("State/territory", STATES_TERRITORIES, index=0)
        notes = st.text_area("Notes")
        submitted = st.form_submit_button("Add query", type="primary")

        if submitted:
            errors = validate_query_fields(query_text)
            if errors:
                for e in errors:
                    st.error(e)
            else:
                crud.create_search_query(
                    db,
                    study_id=study_id,
                    query_text=query_text.strip(),
                    category=category,
                    state_territory=state_territory,
                    notes=notes or None,
                    is_active=True,
                )
                st.success("Query added.")
                st.rerun()

with tab_manage:
    filter_col1, filter_col2 = st.columns(2)
    filter_category = filter_col1.selectbox(
        "Filter by category", ["All"] + QUERY_CATEGORIES, index=0
    )
    filter_state = filter_col2.selectbox(
        "Filter by state/territory", ["All"] + STATES_TERRITORIES, index=0
    )

    queries = crud.list_search_queries(
        db,
        study_id,
        category=None if filter_category == "All" else filter_category,
        state_territory=None if filter_state == "All" else filter_state,
    )

    if not queries:
        st.info("No queries match the current filters. Add one in the 'Add query' tab.")
    else:
        active_n = sum(1 for q in queries if q.is_active)
        st.caption(f"{len(queries)} quer{'y' if len(queries)==1 else 'ies'} shown — {active_n} active.")

        for query in queries:
            status_label = "🟢 Active" if query.is_active else "⚪ Inactive"
            with st.expander(f"{query.query_text}  —  {status_label}"):
                with st.form(f"edit_query_{query.id}"):
                    new_text = st.text_input(
                        "Query text*", value=query.query_text, key=f"qt_{query.id}"
                    )
                    col1, col2 = st.columns(2)
                    new_category = col1.selectbox(
                        "Category",
                        QUERY_CATEGORIES,
                        index=QUERY_CATEGORIES.index(query.category)
                        if query.category in QUERY_CATEGORIES
                        else 0,
                        key=f"qc_{query.id}",
                    )
                    new_state = col2.selectbox(
                        "State/territory",
                        STATES_TERRITORIES,
                        index=STATES_TERRITORIES.index(query.state_territory)
                        if query.state_territory in STATES_TERRITORIES
                        else 0,
                        key=f"qs_{query.id}",
                    )
                    new_notes = st.text_area(
                        "Notes", value=query.notes or "", key=f"qn_{query.id}"
                    )
                    new_active = st.checkbox(
                        "Active", value=query.is_active, key=f"qa_{query.id}"
                    )

                    b1, b2, b3 = st.columns(3)
                    save = b1.form_submit_button("Save", type="primary")
                    duplicate = b2.form_submit_button("Duplicate")
                    delete = b3.form_submit_button("Delete")

                    if save:
                        errors = validate_query_fields(new_text)
                        if errors:
                            for e in errors:
                                st.error(e)
                        else:
                            crud.update_search_query(
                                db,
                                query.id,
                                query_text=new_text.strip(),
                                category=new_category,
                                state_territory=new_state,
                                notes=new_notes or None,
                                is_active=new_active,
                            )
                            st.success("Query updated.")
                            st.rerun()

                    if duplicate:
                        crud.duplicate_search_query(db, query.id)
                        st.success("Query duplicated.")
                        st.rerun()

                    if delete:
                        crud.delete_search_query(db, query.id)
                        st.warning("Query deleted.")
                        st.rerun()

with tab_import:
    st.caption(
        "CSV columns: `query_text` (required), `category`, `state_territory`, `notes`. "
        "Category/state values are matched case-insensitively; unrecognised values are kept as-is."
    )
    uploaded = st.file_uploader("Upload CSV", type=["csv"])
    if uploaded is not None:
        try:
            df = pd.read_csv(uploaded)
        except Exception as exc:
            st.error(f"Could not read CSV: {exc}")
            df = None

        if df is not None:
            if "query_text" not in df.columns:
                st.error("CSV must include a 'query_text' column.")
            else:
                st.dataframe(df.head(20), width='stretch')
                if st.button(f"Import {len(df)} queries", type="primary"):
                    imported = 0
                    for _, row in df.iterrows():
                        text = str(row.get("query_text", "")).strip()
                        if not text or text.lower() == "nan":
                            continue
                        crud.create_search_query(
                            db,
                            study_id=study_id,
                            query_text=text,
                            category=str(row.get("category")) if pd.notna(row.get("category")) else None,
                            state_territory=str(row.get("state_territory"))
                            if pd.notna(row.get("state_territory"))
                            else None,
                            notes=str(row.get("notes")) if pd.notna(row.get("notes")) else None,
                            is_active=True,
                        )
                        imported += 1
                    st.success(f"Imported {imported} queries.")
                    st.rerun()

db.close()
