from __future__ import annotations

import streamlit as st

from components.navigation import page_header, render_context_sidebar, require_study
from db.database import get_session
from services import export_service
from utils.helpers import study_export_code

db = get_session()
current_study, current_reviewer = render_context_sidebar(db)

page_header("Export", "Export analysis-ready CSV datasets. Stable IDs, one flat table per dataset.")

if not require_study(current_study):
    st.stop()

study_id = current_study.id
code = study_export_code(study_id)

required_count = sum(1 for d in export_service.EXPORT_DATASETS if d.required)
bonus_count = len(export_service.EXPORT_DATASETS) - required_count

st.download_button(
    f"⬇ Download all {len(export_service.EXPORT_DATASETS)} datasets ({code}_all.zip)",
    data=export_service.build_zip_export(db, study_id),
    file_name=f"{code}_all.zip",
    mime="application/zip",
    type="primary",
)
st.caption(
    f"{required_count} required datasets plus {bonus_count} reliability datasets (every "
    "reviewer's independent screening/coding records, and computed agreement/kappa — see "
    "the Reliability page). Each is also available individually below, as CSV (priority "
    "format) or JSON."
)

st.markdown("---")

for dataset in export_service.EXPORT_DATASETS:
    df = export_service.build_dataframe(db, study_id, dataset)
    badge = "" if dataset.required else " 🎯"
    with st.expander(f"{dataset.label}{badge} — {len(df)} row{'s' if len(df) != 1 else ''}"):
        if df.empty:
            st.caption("No data yet for this dataset.")
        else:
            st.dataframe(df.head(20), width="stretch", hide_index=True)
            if len(df) > 20:
                st.caption(f"Showing 20 of {len(df)} rows — the download includes all of them.")

        b1, b2 = st.columns(2)
        b1.download_button(
            "Download CSV",
            data=export_service.to_csv_bytes(df),
            file_name=export_service.export_filename(study_id, dataset, "csv"),
            mime="text/csv",
            key=f"csv_{dataset.key}",
            disabled=df.empty,
        )
        b2.download_button(
            "Download JSON",
            data=export_service.to_json_bytes(df),
            file_name=export_service.export_filename(study_id, dataset, "json"),
            mime="application/json",
            key=f"json_{dataset.key}",
            disabled=df.empty,
        )

db.close()
