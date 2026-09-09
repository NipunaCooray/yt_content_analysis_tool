from __future__ import annotations

import datetime

import streamlit as st

from components.navigation import page_header, render_context_sidebar
from db import crud
from db.database import get_session
from utils.constants import (
    DEFAULT_COUNTRY,
    DEFAULT_LANGUAGE,
    SEARCH_ORDER_OPTIONS,
    STUDY_SEARCH_STATUSES,
)
from utils.validators import validate_study_fields

db = get_session()
current_study, current_reviewer = render_context_sidebar(db)

page_header("Study setup", "Create and manage research studies.")

studies = crud.list_studies(db)

tab_list, tab_create = st.tabs(["Existing studies", "Create new study"])

with tab_create:
    with st.form("create_study_form", clear_on_submit=True):
        name = st.text_input("Study name*")
        description = st.text_area("Description")
        col1, col2 = st.columns(2)
        country = col1.text_input("Country", value=DEFAULT_COUNTRY)
        language = col2.text_input("Language", value=DEFAULT_LANGUAGE)
        col3, col4 = st.columns(2)
        search_date = col3.date_input("Search date", value=datetime.date.today())
        default_results = col4.number_input(
            "Default results per query", min_value=1, max_value=50, value=10
        )
        search_order = st.selectbox("Default search order", SEARCH_ORDER_OPTIONS, index=0)
        notes = st.text_area("Notes")
        submitted = st.form_submit_button("Create study", type="primary")

        if submitted:
            errors = validate_study_fields(name, default_results)
            if errors:
                for e in errors:
                    st.error(e)
            else:
                study = crud.create_study(
                    db,
                    name=name.strip(),
                    description=description or None,
                    country=country or DEFAULT_COUNTRY,
                    language=language or DEFAULT_LANGUAGE,
                    search_date=datetime.datetime.combine(search_date, datetime.time.min),
                    default_results_per_query=int(default_results),
                    search_order=search_order,
                    search_status="Draft",
                    notes=notes or None,
                )
                st.session_state["current_study_id"] = study.id
                st.success(f"Study '{study.name}' created.")
                st.rerun()

with tab_list:
    if not studies:
        st.info("No studies yet. Create one in the 'Create new study' tab.")
    else:
        for study in studies:
            with st.expander(f"{study.name}  —  {study.search_status}", expanded=False):
                with st.form(f"edit_study_{study.id}"):
                    name = st.text_input("Study name*", value=study.name, key=f"name_{study.id}")
                    description = st.text_area(
                        "Description", value=study.description or "", key=f"desc_{study.id}"
                    )
                    col1, col2 = st.columns(2)
                    country = col1.text_input(
                        "Country", value=study.country or DEFAULT_COUNTRY, key=f"country_{study.id}"
                    )
                    language = col2.text_input(
                        "Language", value=study.language or DEFAULT_LANGUAGE, key=f"lang_{study.id}"
                    )
                    col3, col4 = st.columns(2)
                    default_results = col3.number_input(
                        "Default results per query",
                        min_value=1,
                        max_value=50,
                        value=study.default_results_per_query or 10,
                        key=f"dr_{study.id}",
                    )
                    search_order = col4.selectbox(
                        "Default search order",
                        SEARCH_ORDER_OPTIONS,
                        index=SEARCH_ORDER_OPTIONS.index(study.search_order)
                        if study.search_order in SEARCH_ORDER_OPTIONS
                        else 0,
                        key=f"order_{study.id}",
                    )
                    status = st.selectbox(
                        "Search status",
                        STUDY_SEARCH_STATUSES,
                        index=STUDY_SEARCH_STATUSES.index(study.search_status)
                        if study.search_status in STUDY_SEARCH_STATUSES
                        else 0,
                        key=f"status_{study.id}",
                    )
                    notes = st.text_area(
                        "Notes", value=study.notes or "", key=f"notes_{study.id}"
                    )

                    col_save, col_select, col_delete = st.columns(3)
                    save = col_save.form_submit_button("Save changes", type="primary")
                    select = col_select.form_submit_button("Set as current study")
                    delete = col_delete.form_submit_button("Delete study")

                    if save:
                        errors = validate_study_fields(name, default_results)
                        if errors:
                            for e in errors:
                                st.error(e)
                        else:
                            crud.update_study(
                                db,
                                study.id,
                                name=name.strip(),
                                description=description or None,
                                country=country or DEFAULT_COUNTRY,
                                language=language or DEFAULT_LANGUAGE,
                                default_results_per_query=int(default_results),
                                search_order=search_order,
                                search_status=status,
                                notes=notes or None,
                            )
                            st.success("Study updated.")
                            st.rerun()

                    if select:
                        st.session_state["current_study_id"] = study.id
                        st.success(f"'{study.name}' is now the current study.")
                        st.rerun()

                    if delete:
                        crud.delete_study(db, study.id)
                        st.warning(f"Deleted study '{study.name}'.")
                        st.rerun()

db.close()
