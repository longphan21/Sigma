import io
import streamlit as st
import pandas as pd

from ui_theme import (
    init_theme,
    render_sidebar_menu,
    render_page_banner,
    queue_popup,
    format_status_badge_html,
    render_html,
)
from database import (
    init_database,
    check_batch_exists,
    save_eqa_batch,
    get_all_batches,
    get_results_by_batch,
    get_all_results_joined,
    delete_batch,
)
from pdf_parser import parse_veqas_pdf
from components import (
    render_batch_meta_bar,
    render_eqa_results_table,
    render_overview_compact_card,
)
from bias_calculator import render_bias_calculator_page

init_theme(page_title="EQA Six Sigma System")
init_database()

# Menu Order: Tab 3 -> 1 (Bias Calculator), Overview -> 2, Import PDF -> 3, Batch Manager -> 4
MENU_ITEMS = [
    ("1. Bias Calculator", ":material/calculate:"),
    ("2. Overview", ":material/dashboard:"),
    ("3. Import PDF", ":material/upload_file:"),
    ("4. Batch Manager", ":material/folder_open:"),
]

page = render_sidebar_menu(
    brand_title="🔬 LAB SYSTEM",
    brand_subtitle="EQA & Six Sigma Module",
    menu_items=MENU_ITEMS,
)


# ==============================================================================
# TAB 1: EQA BIAS CALCULATOR
# ==============================================================================
if page == "1. Bias Calculator":
    render_bias_calculator_page()


# ==============================================================================
# TAB 2: OVERVIEW
# ==============================================================================
elif page == "2. Overview":
    render_page_banner("EQA Database Overview")

    batches = get_all_batches()
    df_all = get_all_results_joined()

    if not batches:
        with st.container(border=True):
            st.markdown("#### :material/info: No EQA Data Available")
            st.write("Please upload a VEQAS PDF report in **3. Import PDF**.")
    else:
        total_batches = len(batches)
        total_records = len(df_all)
        pass_total = int((df_all["eval_status"] == "PASS").sum()) if not df_all.empty else 0
        pass_rate = (pass_total / total_records * 100.0) if total_records > 0 else 0.0
        mean_abs_bias = df_all["bias_pct"].abs().mean() if not df_all.empty else 0.0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Batches", f"{total_batches}")
        c2.metric("Total Results", f"{total_records}")
        c3.metric("Pass Rate (|z| ≤ 2.0)", f"{pass_rate:.1f}%")
        c4.metric("Mean Bias %", f"{mean_abs_bias:.3f}%")

        with st.container(border=True):
            st.markdown("#### :material/filter_alt: Filter")
            f1, f2, f3, f4 = st.columns([1.2, 1.4, 1.4, 1.0], vertical_alignment="bottom")

            month_options = ["All"] + sorted(list({b["month_year"] for b in batches}), reverse=True)
            inst_options = ["All"] + sorted(list({b["instrument_name"] for b in batches if b.get("instrument_name")}))

            sel_month = f1.selectbox("Period", month_options, key="ov_month")
            sel_inst = f2.selectbox("Instrument", inst_options, key="ov_inst")
            search_kw = f3.text_input("Search Analyte", placeholder="ALT, AST, GLU...", key="ov_kw").strip().lower()
            view_mode = f4.selectbox("View Mode", ["Compact List", "Table View"], key="ov_view_mode")

        shown_batches = 0
        for b in batches:
            if sel_month != "All" and b["month_year"] != sel_month:
                continue
            if sel_inst != "All" and b["instrument_name"] != sel_inst:
                continue

            b_results = get_results_by_batch(b["id"])
            if search_kw:
                b_results = [
                    r for r in b_results
                    if search_kw in str(r.get("test_code", "")).lower()
                    or search_kw in str(r.get("test_full_name", "")).lower()
                ]
            if not b_results:
                continue

            shown_batches += 1
            expander_title = (
                f"📅 {b['batch_label']} — {b['program_name']} ({b['program_code']}) "
                f"| {b['instrument_name']} | ID: {b['unit_code']}"
            )
            with st.expander(expander_title, expanded=False):
                if view_mode == "Compact List":
                    render_overview_compact_card(b, b_results)
                else:
                    render_batch_meta_bar(b)
                    render_eqa_results_table(b_results, max_height=360)

        if shown_batches == 0:
            render_html('<div class="search-result-pill">No batches match the current filter.</div>')


# ==============================================================================
# TAB 3: IMPORT EQA PDF
# ==============================================================================
elif page == "3. Import PDF":
    render_page_banner("Import EQA PDF")

    with st.container(border=True):
        st.markdown("#### :material/upload_file: 1. Upload PDF")
        uploaded_pdf = st.file_uploader(
            "Select VEQAS PDF file",
            type=["pdf"],
            key="eqa_pdf_uploader",
        )

    if uploaded_pdf is not None:
        file_bytes = uploaded_pdf.getvalue()
        file_sig = f"{uploaded_pdf.name}_{len(file_bytes)}"

        if st.session_state.get("last_parsed_sig") != file_sig:
            with st.spinner("Parsing PDF..."):
                parsed_data = parse_veqas_pdf(file_bytes, filename=uploaded_pdf.name)
                st.session_state["last_parsed_sig"] = file_sig
                st.session_state["parsed_eqa_data"] = parsed_data

        parsed_data = st.session_state.get("parsed_eqa_data")
        if parsed_data:
            meta = parsed_data["metadata"]
            results = parsed_data["results"]

            with st.container(border=True):
                st.markdown("#### :material/tune: 2. Batch Information")
                col1, col2, col3, col4 = st.columns(4, vertical_alignment="bottom")
                batch_no_in = col1.text_input("Batch No", value=meta.get("batch_no", "01"))
                month_year_in = col2.text_input("Period (MM/YYYY)", value=meta.get("month_year", "01/2026"))
                prog_code_in = col3.text_input("Program Code", value=meta.get("program_code", "BC20C"))
                prog_name_in = col4.text_input("Program Name", value=meta.get("program_name", "Biochemistry"))

                col5, col6, col7, col8 = st.columns(4, vertical_alignment="bottom")
                inst_in = col5.text_input("Instrument", value=meta.get("instrument_name", ""))
                unit_code_in = col6.text_input("Unit ID", value=meta.get("unit_code", ""))
                sample_code_in = col7.text_input("Sample ID", value=meta.get("sample_code", ""))
                default_label = f"Batch {batch_no_in.strip()} - {month_year_in.strip()}"
                batch_label_in = col8.text_input("Batch Label", value=default_label)

                notes_in = st.text_input("Notes", placeholder="Optional notes...")

                existing_id = check_batch_exists(
                    program_code=prog_code_in,
                    batch_no=batch_no_in,
                    month_year=month_year_in,
                    instrument_name=inst_in,
                    sample_code=sample_code_in,
                )
                overwrite_flag = False
                if existing_id is not None:
                    render_html(f"""
                    <div class="eval-result-box eval-result-fail" style="margin-bottom:8px;">
                        <span>⚠️ <b>Batch {batch_no_in} - {month_year_in} ({prog_code_in} - {inst_in})</b> already exists (ID #{existing_id}).</span>
                        {format_status_badge_html('DUPLICATE')}
                    </div>
                    """)
                    overwrite_flag = st.checkbox(
                        "Overwrite existing batch",
                        value=True,
                        key="chk_overwrite_batch",
                    )

            with st.container(border=True):
                st.markdown(f"#### :material/assignment: 3. Preview ({len(results)} Analytes)")
                render_eqa_results_table(results, max_height=380)

                btn_col1, _ = st.columns([1.2, 3.8])
                with btn_col1:
                    if st.button(":material/save: Save Batch", type="primary", use_container_width=True):
                        if not results:
                            queue_popup("Empty File", "No analytes found in the uploaded PDF.", "error")
                            st.rerun()
                        elif existing_id is not None and not overwrite_flag:
                            queue_popup(
                                "Duplicate Batch",
                                "Please enable 'Overwrite existing batch' or change the Period/Batch No.",
                                "warning",
                            )
                            st.rerun()
                        else:
                            final_meta = {
                                "batch_label": batch_label_in.strip(),
                                "batch_no": batch_no_in.strip(),
                                "month_year": month_year_in.strip(),
                                "program_name": prog_name_in.strip(),
                                "program_code": prog_code_in.strip(),
                                "unit_code": unit_code_in.strip(),
                                "instrument_name": inst_in.strip(),
                                "sample_code": sample_code_in.strip(),
                                "source_filename": uploaded_pdf.name,
                                "notes": notes_in.strip(),
                            }
                            saved_id = save_eqa_batch(
                                metadata=final_meta,
                                results=results,
                                overwrite_batch_id=existing_id if overwrite_flag else None,
                            )
                            queue_popup(
                                "Saved Successfully",
                                f"Saved '{batch_label_in}' ({len(results)} analytes - {inst_in}) as ID #{saved_id}.",
                                "success",
                            )
                            st.rerun()


# ==============================================================================
# TAB 4: BATCH MANAGER
# ==============================================================================
elif page == "4. Batch Manager":
    render_page_banner("Batch Manager")

    batches = get_all_batches()
    if not batches:
        with st.container(border=True):
            st.markdown("#### :material/storage: Database Empty")
            st.write("Please upload a VEQAS PDF report in **3. Import PDF** first.")
    else:
        with st.container(border=True):
            st.markdown("#### :material/folder_open: Select Batch")
            batch_map = {
                f"[#{b['id']}] {b['batch_label']} | {b['program_code']} - {b['instrument_name']} ({b['total_tests']} Analytes)": b
                for b in batches
            }
            sel_label = st.selectbox("Saved Batches", list(batch_map.keys()), key="hist_sel_batch")
            sel_batch = batch_map[sel_label]
            sel_results = get_results_by_batch(sel_batch["id"])

            render_batch_meta_bar(sel_batch)
            render_eqa_results_table(sel_results, max_height=400)

            df_export = pd.DataFrame(sel_results)
            act1, act2, act3, _ = st.columns([1.2, 1.2, 1.2, 1.4], vertical_alignment="bottom")

            csv_bytes = df_export.to_csv(index=False).encode("utf-8-sig")
            act1.download_button(
                ":material/download: Export CSV",
                data=csv_bytes,
                file_name=f"EQA_{sel_batch['program_code']}_B{sel_batch['batch_no']}_{sel_batch['month_year'].replace('/', '-')}.csv",
                mime="text/csv",
                use_container_width=True,
            )

            excel_buf = io.BytesIO()
            with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
                df_export.to_excel(writer, index=False, sheet_name="EQA_Results")
            act2.download_button(
                ":material/table_view: Export Excel",
                data=excel_buf.getvalue(),
                file_name=f"EQA_{sel_batch['program_code']}_B{sel_batch['batch_no']}_{sel_batch['month_year'].replace('/', '-')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

            if act3.button(":material/delete: Delete Batch", type="secondary", use_container_width=True):
                delete_batch(sel_batch["id"])
                queue_popup(
                    "Batch Deleted",
                    f"Removed '{sel_batch['batch_label']}' from Database.",
                    "error",
                )
                st.rerun()
