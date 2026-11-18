import io
import pandas as pd
import streamlit as st

from ui_theme import render_page_banner, render_html, queue_popup
from database import (
    get_all_results_joined,
    get_all_tea_standards,
    save_tea_standard,
    update_tea_standards_bulk,
    delete_tea_standard,
    normalize_test_info,
)

TEA_SOURCE_OPTIONS = [
    "CLIA",
    "BV (Desirable)",
    "BV (Minimum)",
    "BV (Optimum)",
    "RCPA",
    "Rili-BÄK",
    "CAP",
    "Other",
]


def _build_analyte_catalog_for_inst(df_eqa: pd.DataFrame, df_tea: pd.DataFrame, instrument_name: str):
    catalog = {}
    if not df_eqa.empty:
        sub_eqa = df_eqa[df_eqa["instrument_name"].astype(str).str.lower() == instrument_name.strip().lower()]
        if sub_eqa.empty:
            sub_eqa = df_eqa
        for t_code, grp in sub_eqa.groupby("test_code"):
            code_str = str(t_code).strip()
            full_str = str(grp["test_full_name"].iloc[0]).strip() if not grp.empty else code_str
            unit_str = str(grp["unit"].dropna().iloc[0]).strip() if not grp["unit"].dropna().empty else ""
            catalog[code_str.upper()] = (code_str, full_str, unit_str)

    if not df_tea.empty:
        sub_tea = df_tea[df_tea["instrument_name"].astype(str).str.lower() == instrument_name.strip().lower()]
        for _, r in sub_tea.iterrows():
            code_str = str(r.get("test_code", "")).strip()
            if code_str and code_str.upper() not in catalog:
                catalog[code_str.upper()] = (
                    code_str,
                    str(r.get("test_full_name", "") or code_str).strip(),
                    str(r.get("unit", "") or "").strip(),
                )

    return sorted(catalog.values(), key=lambda x: x[0].upper())


def render_tea_manager_page():
    render_page_banner("TEa% Standards Manager")

    df_eqa = get_all_results_joined()
    df_tea = get_all_tea_standards()

    inst_set = set()
    if not df_eqa.empty and "instrument_name" in df_eqa.columns:
        inst_set.update(df_eqa["instrument_name"].dropna().unique().tolist())
    if not df_tea.empty and "instrument_name" in df_tea.columns:
        inst_set.update(df_tea["instrument_name"].dropna().unique().tolist())
    inst_list = sorted([str(x).strip() for x in inst_set if str(x).strip()])

    # ==========================================================================
    # SECTION 1: ADD / UPDATE TEA STANDARD (WITH INSTRUMENT)
    # ==========================================================================
    with st.container(border=True):
        st.markdown("#### :material/add_circle: 1. Add / Update TEa% Standard")

        inst_options = inst_list + ["+ Custom Instrument"]
        c_inst, c1, c2, c3, c4, c5 = st.columns(
            [1.35, 1.75, 0.65, 1.15, 0.85, 0.85], vertical_alignment="bottom"
        )

        sel_inst_opt = c_inst.selectbox(
            "Instrument",
            options=inst_options,
            key="tea_inst_sel",
        )
        active_inst_for_lookup = "" if sel_inst_opt == "+ Custom Instrument" else sel_inst_opt

        catalog = _build_analyte_catalog_for_inst(df_eqa, df_tea, active_inst_for_lookup)

        configured_tests_on_inst = set()
        if not df_tea.empty and active_inst_for_lookup:
            sub_t_inst = df_tea[
                df_tea["instrument_name"].astype(str).str.strip().str.lower() == active_inst_for_lookup.lower()
            ]
            configured_tests_on_inst = set(sub_t_inst["test_code"].astype(str).str.strip().str.upper().tolist())

        test_options = [x[0] for x in catalog] + ["+ Custom Analyte"]
        label_map = {
            x[0]: ("✅ " if x[0].upper() in configured_tests_on_inst else "") + f"{x[0]} — {x[1]}"
            for x in catalog
        }
        label_map["+ Custom Analyte"] = "➕ Add Custom Analyte..."
        unit_lookup = {x[0]: x[2] for x in catalog}
        name_lookup = {x[0]: x[1] for x in catalog}

        sel_test_opt = c1.selectbox(
            f"Analyte ({len(configured_tests_on_inst)}/{len(catalog)} configured)",
            options=test_options,
            format_func=lambda k: label_map.get(k, k),
            key=f"tea_analyte_sel_{sel_inst_opt}",
        )

        default_unit = unit_lookup.get(sel_test_opt, "") if sel_test_opt != "+ Custom Analyte" else ""
        unit_in = c2.text_input("Unit", value=default_unit, key=f"tea_unit_in_{sel_inst_opt}_{sel_test_opt}")

        sel_source = c3.selectbox("TEa Source", options=TEA_SOURCE_OPTIONS, key="tea_source_sel")

        existing_val = 10.0
        if not df_tea.empty and sel_inst_opt != "+ Custom Instrument" and sel_test_opt != "+ Custom Analyte":
            m_row = df_tea[
                (df_tea["instrument_name"].astype(str).str.lower() == sel_inst_opt.lower())
                & (df_tea["test_code"].astype(str).str.upper() == sel_test_opt.upper())
                & (df_tea["tea_source"].astype(str).str.lower() == sel_source.lower())
            ]
            if not m_row.empty and pd.notna(m_row["tea_pct"].iloc[0]):
                existing_val = float(m_row["tea_pct"].iloc[0])

        tea_pct_in = c4.number_input(
            "TEa %",
            min_value=0.01,
            max_value=300.0,
            value=existing_val,
            step=0.5,
            format="%.2f",
            key=f"tea_pct_in_{sel_inst_opt}_{sel_test_opt}_{sel_source}",
        )

        is_def_opt = c5.selectbox(
            "Default",
            options=[True, False],
            format_func=lambda x: "★ Default" if x else "Secondary",
            key="tea_is_default_sel",
        )

        need_custom_row = (
            sel_inst_opt == "+ Custom Instrument"
            or sel_test_opt == "+ Custom Analyte"
            or sel_source == "Other"
        )
        if need_custom_row:
            sc0, sc1, sc2, sc3 = st.columns([1.3, 1.0, 1.5, 1.4], vertical_alignment="bottom")
            custom_inst = (
                sc0.text_input("Custom Instrument Name", placeholder="e.g., Cobas c501")
                if sel_inst_opt == "+ Custom Instrument"
                else sel_inst_opt
            )
            custom_code = (
                sc1.text_input("Custom Code", placeholder="e.g., LDH")
                if sel_test_opt == "+ Custom Analyte"
                else sel_test_opt
            )
            custom_name = (
                sc2.text_input("Full Name", placeholder="e.g., Lactate Dehydrogenase")
                if sel_test_opt == "+ Custom Analyte"
                else name_lookup.get(sel_test_opt, sel_test_opt)
            )
            custom_source = (
                sc3.text_input("Custom Source Name", placeholder="e.g., Lab Target")
                if sel_source == "Other"
                else sel_source
            )
        else:
            custom_inst = sel_inst_opt
            custom_code = sel_test_opt
            custom_name = name_lookup.get(sel_test_opt, sel_test_opt)
            custom_source = sel_source

        b_col1, b_col2 = st.columns([3.6, 1.4], vertical_alignment="bottom")
        notes_in = b_col1.text_input(
            "Notes",
            placeholder="Optional notes (e.g., concentration threshold)...",
            key="tea_notes_in",
        )

        if b_col2.button(":material/save: Save TEa%", type="primary", use_container_width=True):
            if not str(custom_inst).strip():
                queue_popup("Missing Instrument", "Please select or enter an Instrument name.", "warning")
                st.rerun()
            elif not str(custom_code).strip():
                queue_popup("Missing Analyte", "Please enter a valid Analyte code.", "warning")
                st.rerun()
            elif not str(custom_source).strip():
                queue_popup("Missing Source", "Please enter a TEa source name.", "warning")
                st.rerun()
            else:
                norm_c, norm_n = normalize_test_info(custom_code, custom_name)
                save_tea_standard(
                    instrument_name=str(custom_inst).strip(),
                    test_code=norm_c,
                    test_full_name=norm_n or norm_c,
                    unit=unit_in,
                    tea_source=custom_source,
                    tea_pct=float(tea_pct_in),
                    is_default=bool(is_def_opt),
                    notes=notes_in,
                )
                queue_popup(
                    "Saved Successfully",
                    f"Saved TEa = {float(tea_pct_in):.2f}% ({custom_source}) for {norm_c} on {custom_inst}.",
                    "success",
                )
                st.rerun()

        n_sources = df_tea["tea_source"].nunique() if not df_tea.empty else 0
        render_html(f"""
        <div class="history-meta-bar" style="margin-top:6px; margin-bottom:2px;">
            <span>🔬 <b>Instrument:</b> <code>{custom_inst or '-'}</code></span>
            <span>📊 <b>Configured on Instrument:</b> <span class="lot-pill">{len(configured_tests_on_inst)}/{len(catalog)}</span></span>
            <span>📑 <b>Total TEa Records:</b> <b>{len(df_tea)}</b></span>
            <span>🏛️ <b>Sources in DB:</b> <code>{n_sources}</code></span>
        </div>
        """)

    # ==========================================================================
    # SECTION 2: SAVED TEA STANDARDS TABLE & BULK EDITOR
    # ==========================================================================
    with st.container(border=True):
        st.markdown("#### :material/table_chart: 2. Saved TEa% Standards")

        if df_tea.empty:
            render_html('<div class="search-result-pill">No TEa% standards saved yet. Add one above.</div>')
            return

        f0, f1, f2, f3 = st.columns([1.4, 1.3, 1.5, 1.1], vertical_alignment="bottom")
        saved_inst_list = ["All Instruments"] + sorted(
            [str(x) for x in df_tea["instrument_name"].dropna().unique().tolist() if str(x).strip()]
        )
        sel_filter_inst = f0.selectbox("Filter Instrument", options=saved_inst_list, key="tea_filter_inst")

        src_list = ["All Sources"] + sorted(df_tea["tea_source"].dropna().unique().tolist())
        sel_filter_src = f1.selectbox("Filter Source", options=src_list, key="tea_filter_src")
        kw_filter = f2.text_input("Search Analyte", placeholder="ALT, AST, GLU...", key="tea_filter_kw").strip().lower()
        only_default = f3.selectbox(
            "View Mode",
            options=["All Records", "Default Only (★)"],
            key="tea_filter_mode",
        )

        df_view = df_tea.copy()
        if sel_filter_inst != "All Instruments":
            df_view = df_view[df_view["instrument_name"] == sel_filter_inst]
        if sel_filter_src != "All Sources":
            df_view = df_view[df_view["tea_source"] == sel_filter_src]
        if kw_filter:
            df_view = df_view[
                df_view["test_code"].astype(str).str.lower().str.contains(kw_filter, na=False)
                | df_view["test_full_name"].astype(str).str.lower().str.contains(kw_filter, na=False)
            ]
        if only_default == "Default Only (★)":
            df_view = df_view[df_view["is_default"] == True]

        if df_view.empty:
            render_html('<div class="search-result-pill">No records match the current filter.</div>')
            return

        edited_df = st.data_editor(
            df_view,
            column_config={
                "id": st.column_config.NumberColumn("ID", width="small", disabled=True),
                "instrument_name": st.column_config.TextColumn("Instrument", width="medium"),
                "test_code": st.column_config.TextColumn("Analyte", width="small", disabled=True),
                "test_full_name": st.column_config.TextColumn("Full Name", width="medium", disabled=True),
                "unit": st.column_config.TextColumn("Unit", width="small"),
                "tea_source": st.column_config.SelectboxColumn("TEa Source", options=TEA_SOURCE_OPTIONS, width="medium"),
                "tea_pct": st.column_config.NumberColumn("TEa %", format="%.2f%%", min_value=0.01, max_value=300.0, step=0.1, width="small"),
                "is_default": st.column_config.CheckboxColumn("★ Default", width="small"),
                "notes": st.column_config.TextColumn("Notes", width="medium"),
                "updated_at": st.column_config.TextColumn("Updated", width="medium", disabled=True),
            },
            use_container_width=True,
            hide_index=True,
            key="tea_standards_editor",
        )

        act1, act2, act3, act4 = st.columns([1.2, 1.2, 1.8, 1.0], vertical_alignment="bottom")

        if act1.button(":material/save: Save Table Edits", type="primary", use_container_width=True):
            update_tea_standards_bulk(edited_df)
            queue_popup("Updated", "Saved table edits to TEa% database.", "success")
            st.rerun()

        excel_buf = io.BytesIO()
        df_export = df_view.rename(columns={
            "id": "ID",
            "instrument_name": "Instrument",
            "test_code": "Analyte",
            "test_full_name": "Full Name",
            "unit": "Unit",
            "tea_source": "TEa Source",
            "tea_pct": "TEa %",
            "is_default": "Default",
            "notes": "Notes",
            "updated_at": "Updated",
        })
        with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
            df_export.to_excel(writer, index=False, sheet_name="TEa_Standards")

        act2.download_button(
            ":material/table_view: Export Excel",
            data=excel_buf.getvalue(),
            file_name="TEa_Standards.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

        del_options = {
            f"[#{r['id']}] {r['instrument_name']} | {r['test_code']} — {r['tea_source']} ({r['tea_pct']:.2f}%)": int(r["id"])
            for _, r in df_view.iterrows()
        }
        sel_del_label = act3.selectbox(
            "Record to delete",
            options=list(del_options.keys()),
            label_visibility="collapsed",
            key="tea_del_sel",
        )
        if act4.button(":material/delete: Delete", type="secondary", use_container_width=True):
            delete_tea_standard(del_options[sel_del_label])
            queue_popup("Deleted", f"Removed {sel_del_label}.", "error")
            st.rerun()