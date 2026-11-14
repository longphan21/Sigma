import io
from datetime import datetime
from typing import List, Dict, Any, Tuple
import pandas as pd
import streamlit as st

from ui_theme import render_page_banner, render_html, queue_popup, format_status_badge_html
from database import (
    get_all_results_joined,
    save_bias_summary_records,
    get_all_bias_summaries,
    delete_bias_summary_by_test,
    parse_ym_tuple,
)

QUARTER_OPTIONS: List[Tuple[int, str, int]] = [
    (1, "Q1 (Mar)", 3),
    (2, "Q2 (Jun)", 6),
    (3, "Q3 (Sep)", 9),
    (4, "Q4 (Dec)", 12),
]


def _compute_exact_monthly_bias(df_test: pd.DataFrame) -> pd.DataFrame:
    df = df_test.copy()
    exact_bias_list = []

    for _, row in df.iterrows():
        d_val = row.get("lab_result")
        e_val = row.get("assigned_value")
        b_pct = row.get("bias_pct")

        if pd.notna(d_val) and pd.notna(e_val) and float(e_val) != 0.0:
            d_f = float(d_val)
            e_f = float(e_val)
            exact_bias_list.append(abs(d_f - e_f) * 100.0 / abs(e_f))
        elif pd.notna(b_pct):
            exact_bias_list.append(abs(float(b_pct)))
        else:
            exact_bias_list.append(float("nan"))

    df["exact_bias_pct"] = exact_bias_list
    return df


def _calc_level_average_bias(df_sub: pd.DataFrame) -> Dict[str, Any]:
    valid = df_sub.dropna(subset=["exact_bias_pct"])
    n = len(valid)
    if n == 0:
        return {
            "n": 0,
            "avg_bias_3dec": 0.0,
            "mean_assigned": 0.0,
            "mean_lab": 0.0,
            "months_str": "-",
            "formula_detail": "-",
        }

    bias_vals = valid["exact_bias_pct"].astype(float)
    asg_vals = valid["assigned_value"].dropna().astype(float)
    lab_vals = valid["lab_result"].dropna().astype(float)

    avg_val = float(bias_vals.mean())
    avg_3dec = round(avg_val, 3)
    mean_asg = float(asg_vals.mean()) if not asg_vals.empty else 0.0
    mean_lab = float(lab_vals.mean()) if not lab_vals.empty else 0.0

    months_list = valid["month_year"].astype(str).tolist()
    terms_str = " + ".join([f"{v:.3f}%" for v in bias_vals.tolist()])

    return {
        "n": n,
        "avg_bias_3dec": avg_3dec,
        "mean_assigned": round(mean_asg, 3),
        "mean_lab": round(mean_lab, 3),
        "months_str": ", ".join(months_list),
        "formula_detail": f"({terms_str}) / {n} = {avg_3dec:.3f}%",
    }


def _render_quarter_summary_table(
    df_q: pd.DataFrame,
    quarter_code: str,
    key_suffix: str,
):
    if df_q.empty:
        render_html(f'<div class="search-result-pill">No saved records for <b>{quarter_code}</b>.</div>')
        return

    df_show = df_q[[
        "quarter_period", "instrument_name", "test_code", "unit", "level_name",
        "mean_conc", "n_batches", "selected_batches", "chosen_bias_pct", "updated_at"
    ]].copy()
    df_show["mean_conc"] = df_show["mean_conc"].round(3)
    df_show["chosen_bias_pct"] = df_show["chosen_bias_pct"].round(3)

    df_display = df_show.rename(columns={
        "quarter_period": "Quarter",
        "instrument_name": "Instrument",
        "test_code": "Analyte",
        "unit": "Unit",
        "level_name": "Level",
        "mean_conc": "Mean Assigned",
        "n_batches": "Months",
        "selected_batches": "Selected Months",
        "chosen_bias_pct": "Mean Bias %",
        "updated_at": "Updated",
    })

    st.dataframe(
        df_display,
        column_config={
            "Mean Assigned": st.column_config.NumberColumn("Mean Assigned", format="%.3f"),
            "Mean Bias %": st.column_config.NumberColumn("Mean Bias %", format="%.3f%%"),
        },
        use_container_width=True,
        hide_index=True,
        key=f"df_saved_table_{key_suffix}",
    )

    act_c1, act_c2, act_c3 = st.columns([1.2, 2.2, 1.2], vertical_alignment="bottom")
    excel_buf = io.BytesIO()
    with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
        df_display.to_excel(writer, index=False, sheet_name="Bias_Summary")
    safe_q_fname = quarter_code.replace("/", "_").replace(" ", "_")

    act_c1.download_button(
        f":material/table_view: Export ({quarter_code})",
        data=excel_buf.getvalue(),
        file_name=f"EQA_Bias_{safe_q_fname}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        key=f"dl_btn_{key_suffix}",
    )

    saved_items = [
        f"{r['quarter_period']} | {r['instrument_name']} | {r['test_code']}"
        for _, r in df_q[["quarter_period", "instrument_name", "test_code"]].drop_duplicates().iterrows()
    ]
    del_item = act_c2.selectbox(
        "Record to delete",
        saved_items,
        label_visibility="collapsed",
        key=f"del_sel_{key_suffix}",
    )
    if act_c3.button(
        ":material/delete: Delete Record",
        type="secondary",
        use_container_width=True,
        key=f"del_btn_{key_suffix}",
    ):
        p_q, p_inst, p_test = [x.strip() for x in del_item.split("|", 2)]
        delete_bias_summary_by_test(p_test, instrument_name=p_inst, quarter_period=p_q)
        queue_popup("Deleted", f"Removed {p_test} ({p_inst}) from {p_q}.", "error")
        st.rerun()


def render_bias_calculator_page():
    render_page_banner("EQA Bias Calculator")

    df_all = get_all_results_joined()
    if df_all.empty:
        with st.container(border=True):
            st.markdown("#### :material/info: No EQA Data Available")
            st.write("Please upload a VEQAS PDF report in **3. Import PDF** first.")
        return

    df_saved_all = get_all_bias_summaries()

    ym_parsed = [parse_ym_tuple(m) for m in df_all["month_year"].dropna().unique().tolist()]
    years_in_db = sorted(list({yr for yr, _ in ym_parsed if yr > 2000} | {datetime.now().year, 2026}), reverse=True)

    tab_calc, tab_saved = st.tabs([
        "🧮 1. Bias Calculator",
        "📋 2. Saved Summary",
    ])

    with tab_calc:
        # ======================================================================
        # STEP 1: QUARTER, INSTRUMENT & ANALYTE SELECTION (UNIFORM ROW)
        # ======================================================================
        with st.container(border=True):
            st.markdown("#### :material/tune: 1. Configuration")
            c_q, c_yr, c_inst, c_test, c_lv = st.columns([0.95, 0.75, 1.35, 1.85, 0.9], vertical_alignment="bottom")

            q_idx_map = {q_no: label for q_no, label, _ in QUARTER_OPTIONS}
            sel_q_no = c_q.selectbox(
                "Quarter",
                options=[1, 2, 3, 4],
                format_func=lambda x: q_idx_map[x],
                index=2,
                key="bias_quarter_no_sel",
            )
            sel_year = c_yr.selectbox(
                "Year",
                options=years_in_db,
                index=0,
                key="bias_year_sel",
            )

            cutoff_month = sel_q_no * 3
            active_quarter_period = f"Q{sel_q_no}/{sel_year}"

            inst_list = sorted(df_all["instrument_name"].dropna().unique().tolist())
            sel_inst = c_inst.selectbox("Instrument", inst_list, key="bias_inst_sel")

            df_inst_all = df_all[df_all["instrument_name"] == sel_inst].copy()

            filter_by_quarter_cutoff = st.checkbox(
                f"Filter up to {cutoff_month:02d}/{sel_year} ({active_quarter_period})",
                value=True,
                key="chk_filter_cutoff_quarter",
            )

            if filter_by_quarter_cutoff:
                df_inst = df_inst_all[
                    df_inst_all["month_year"].apply(lambda m: parse_ym_tuple(m) <= (int(sel_year), int(cutoff_month)))
                ].copy()
                if df_inst.empty:
                    df_inst = df_inst_all.copy()
            else:
                df_inst = df_inst_all.copy()

            all_months_inst = sorted(
                df_inst["month_year"].dropna().unique().tolist(),
                key=parse_ym_tuple,
            )

            test_stats = []
            for t_code, grp in df_inst.groupby("test_code"):
                t_full = str(grp["test_full_name"].iloc[0]) if not grp.empty else str(t_code)
                n_months = grp["month_year"].nunique()
                test_stats.append((str(t_code), t_full, n_months))
            test_stats.sort(key=lambda x: x[0].upper())

            test_codes_list = [x[0] for x in test_stats]
            test_label_map = {
                x[0]: f"{x[0]} — {x[1]} ({x[2]}m)"
                for x in test_stats
            }

            saved_tests_in_quarter = set()
            if not df_saved_all.empty:
                sub_q_saved = df_saved_all[
                    (df_saved_all["instrument_name"].astype(str).str.strip().str.lower() == sel_inst.strip().lower())
                    & (df_saved_all["quarter_period"].astype(str).str.strip().str.lower() == active_quarter_period.lower())
                ]
                saved_tests_in_quarter = set(sub_q_saved["test_code"].astype(str).str.strip().str.upper().tolist())

            sel_test = c_test.selectbox(
                f"Analyte ({len(test_codes_list)})",
                options=test_codes_list,
                format_func=lambda k: ("✅ " if k.strip().upper() in saved_tests_in_quarter else "") + test_label_map.get(k, k),
                key=f"bias_test_sel_{sel_inst}",
            )

            num_levels = c_lv.selectbox(
                "Levels",
                options=[2, 3, 1],
                format_func=lambda x: f"{x} Levels" if x > 1 else "1 Level",
                key="bias_num_levels",
            )

            months_preview = ", ".join(all_months_inst) if all_months_inst else "-"
            render_html(f"""
            <div class="history-meta-bar" style="margin-top:4px; margin-bottom:2px;">
                <span>📌 <b>Period:</b> <span class="date-pill">{active_quarter_period}</span></span>
                <span>🔬 <b>Instrument:</b> <code>{sel_inst}</code></span>
                <span>📊 <b>Analytes:</b> <span class="lot-pill">{len(test_codes_list)}</span></span>
                <span>📅 <b>Months ({len(all_months_inst)}):</b> <code>{months_preview}</code></span>
                <span>✅ <b>Saved ({active_quarter_period}):</b> <b>{len(saved_tests_in_quarter)}/{len(test_codes_list)}</b></span>
            </div>
            """)

        # ======================================================================
        # STEP 2: MONTH SELECTION TABLE
        # ======================================================================
        df_test = df_inst[df_inst["test_code"] == sel_test].copy()
        df_test["_ym_sort"] = df_test["month_year"].apply(parse_ym_tuple)
        df_test = df_test.sort_values(by=["_ym_sort", "batch_no"], ascending=[True, True]).drop(columns=["_ym_sort"]).reset_index(drop=True)
        df_test = _compute_exact_monthly_bias(df_test)

        unit_str = str(df_test["unit"].iloc[0]) if not df_test.empty else ""
        full_name_str = str(df_test["test_full_name"].iloc[0]) if not df_test.empty else sel_test

        level_names = (
            ["Level 1 (LOW)", "Level 2 (HIGH)"]
            if num_levels == 2
            else (["Level 1 (LOW)", "Level 2 (MID)", "Level 3 (HIGH)"] if num_levels == 3 else ["Level 1"])
        )
        short_check_labels = (
            ["☑️ Level 1 (LOW)", "☑️ Level 2 (HIGH)"]
            if num_levels == 2
            else (["☑️ Level 1 (LOW)", "☑️ Level 2 (MID)", "☑️ Level 3 (HIGH)"] if num_levels == 3 else ["☑️ Select"])
        )

        saved_months_by_lv: Dict[int, set] = {}
        if not df_saved_all.empty:
            sub_s = df_saved_all[
                (df_saved_all["instrument_name"].astype(str).str.strip().str.lower() == sel_inst.strip().lower())
                & (df_saved_all["test_code"].astype(str).str.strip().str.upper() == sel_test.strip().upper())
                & (df_saved_all["quarter_period"].astype(str).str.strip().str.lower() == active_quarter_period.lower())
            ]
            for _, s_row in sub_s.iterrows():
                lv_no = int(s_row.get("level_no", 1) or 1)
                b_raw = str(s_row.get("selected_batches", ""))
                b_items = {x.strip() for x in b_raw.split(",") if x.strip() and x.strip() != "-"}
                if b_items:
                    saved_months_by_lv[lv_no] = b_items

        state_sig = f"{active_quarter_period}_{sel_inst}_{sel_test}"
        reset_counter_key = f"reset_cnt_{state_sig}"
        if reset_counter_key not in st.session_state:
            st.session_state[reset_counter_key] = 0

        for idx in range(num_levels):
            lv_no = idx + 1
            saved_set = saved_months_by_lv.get(lv_no, set())
            if st.session_state.get(f"force_empty_{state_sig}", False):
                df_test[f"use_lv{lv_no}"] = False
            else:
                df_test[f"use_lv{lv_no}"] = [
                    str(m).strip() in saved_set for m in df_test["month_year"].tolist()
                ]

        with st.container(border=True):
            hdr_c1, hdr_c2 = st.columns([3.8, 1.2], vertical_alignment="center")
            with hdr_c1:
                st.markdown(
                    f"#### :material/check_box: 2. Select Months — **{sel_test}** ({full_name_str})"
                )
            with hdr_c2:
                if st.button(":material/restart_alt: Clear Selection", type="secondary", use_container_width=True):
                    st.session_state[f"force_empty_{state_sig}"] = True
                    st.session_state[reset_counter_key] += 1
                    st.rerun()

            df_test["bias_3dec_display"] = df_test["exact_bias_pct"].round(3)
            editor_cols = (
                ["month_year"]
                + [f"use_lv{i + 1}" for i in range(num_levels)]
                + [
                    "lab_result",
                    "assigned_value",
                    "bias_3dec_display",
                    "unit",
                    "z_score",
                    "batch_label",
                ]
            )
            df_editor_in = df_test[editor_cols].copy()

            col_cfg = {
                "month_year": st.column_config.TextColumn("Month", width="small", disabled=True),
                "lab_result": st.column_config.NumberColumn(f"Lab Result ({unit_str})", format="%.3f", width="small", disabled=True),
                "assigned_value": st.column_config.NumberColumn(f"Assigned ({unit_str})", format="%.3f", width="small", disabled=True),
                "bias_3dec_display": st.column_config.NumberColumn("Bias %", format="%.3f%%", width="small", disabled=True),
                "unit": st.column_config.TextColumn("Unit", width="small", disabled=True),
                "z_score": st.column_config.NumberColumn("z-score", format="%+.2f", width="small", disabled=True),
                "batch_label": st.column_config.TextColumn("Batch", width="medium", disabled=True),
            }
            for idx in range(num_levels):
                col_cfg[f"use_lv{idx + 1}"] = st.column_config.CheckboxColumn(
                    short_check_labels[idx],
                    width="small",
                    default=False,
                )

            edited_df = st.data_editor(
                df_editor_in,
                column_config=col_cfg,
                use_container_width=True,
                hide_index=True,
                key=f"editor_manual_bias_{state_sig}_{num_levels}_{filter_by_quarter_cutoff}_{st.session_state[reset_counter_key]}",
            )

        # ======================================================================
        # STEP 3: RESULTS & SAVE TO QUARTER
        # ======================================================================
        with st.container(border=True):
            st.markdown(f"#### :material/calculate: 3. Mean Bias % — **{active_quarter_period}**")

            copy_lv1_to_lv2 = False
            if num_levels == 2:
                copy_lv1_to_lv2 = st.checkbox(
                    "🔗 Copy Level 1 (LOW) to Level 2 (HIGH)",
                    value=False,
                    key=f"chk_same_bias_{state_sig}",
                )

            lv_cols = st.columns(num_levels)
            records_to_save = []

            for idx in range(num_levels):
                if copy_lv1_to_lv2 and idx == 1:
                    col_flag = "use_lv1"
                else:
                    col_flag = f"use_lv{idx + 1}"

                lv_title = level_names[idx]
                selected_mask = edited_df[col_flag] == True
                sub_selected = df_test.loc[selected_mask.index[selected_mask]]
                metrics = _calc_level_average_bias(sub_selected)

                with lv_cols[idx]:
                    badge_state = f"{metrics['n']} MONTHS" if metrics["n"] > 0 else "EMPTY"
                    render_html(f"""
                    <div class="eval-result-box {'eval-result-pass' if metrics['n'] > 0 else 'eval-result-fail'}" style="margin-bottom:8px;">
                        <span><b>{lv_title}</b> (Lab: <code>{metrics['mean_lab']:.3f}</code> | Asg: <code>{metrics['mean_assigned']:.3f} {unit_str}</code>)</span>
                        {format_status_badge_html('PASS' if metrics['n'] >= 3 else badge_state)}
                    </div>
                    """)
                    m_a, m_b = st.columns(2)
                    m_a.metric("Mean Bias %", f"{metrics['avg_bias_3dec']:.3f}%")
                    m_b.metric("Selected", f"{metrics['n']} months")

                    render_html(f"""
                    <div class="history-meta-bar">
                        <span><b>Months:</b> <code>{metrics['months_str']}</code></span>
                        <span><b>Average:</b> <code>{metrics['formula_detail']}</code></span>
                    </div>
                    """)

                records_to_save.append({
                    "instrument_name": sel_inst,
                    "test_code": sel_test,
                    "unit": unit_str,
                    "level_no": idx + 1,
                    "level_name": lv_title,
                    "mean_conc": metrics["mean_assigned"],
                    "n_batches": metrics["n"],
                    "selected_batches": metrics["months_str"],
                    "mean_abs_bias_pct": metrics["avg_bias_3dec"],
                    "mean_signed_bias_pct": metrics["avg_bias_3dec"],
                    "rms_bias_pct": metrics["avg_bias_3dec"],
                    "chosen_bias_pct": metrics["avg_bias_3dec"],
                    "formula_type": active_quarter_period,
                })

            btn_c1, _ = st.columns([1.4, 3.6])
            with btn_c1:
                if st.button(
                    f":material/save: Save to {active_quarter_period}",
                    type="primary",
                    use_container_width=True,
                ):
                    if any(r["n_batches"] == 0 for r in records_to_save):
                        queue_popup(
                            "Incomplete Selection",
                            "Please select at least 1 month for each level before saving.",
                            "warning",
                        )
                        st.rerun()
                    else:
                        st.session_state[f"force_empty_{state_sig}"] = False
                        save_bias_summary_records(
                            instrument_name=sel_inst,
                            test_code=sel_test,
                            level_records=records_to_save,
                            quarter_period=active_quarter_period,
                        )
                        queue_popup(
                            "Saved Successfully",
                            f"Saved {sel_test} ({sel_inst}) to {active_quarter_period}.",
                            "success",
                        )
                        st.rerun()

    # ==========================================================================
    # TAB 2: QUARTERLY SUMMARY TABLE (Q1, Q2, Q3, Q4)
    # ==========================================================================
    with tab_saved:
        df_saved = get_all_bias_summaries()
        with st.container(border=True):
            st.markdown("#### :material/table_chart: Quarterly Bias Summary")

            if df_saved.empty:
                st.write("No saved records yet.")
            else:
                f_col1, f_col2, f_col3 = st.columns([1.0, 1.8, 1.4], vertical_alignment="bottom")

                saved_years = sorted(
                    list({
                        int(q.split("/")[-1])
                        for q in df_saved["quarter_period"].dropna().unique().tolist()
                        if "/" in str(q) and str(q).split("/")[-1].isdigit()
                    } | {int(sel_year)}),
                    reverse=True,
                )
                sel_view_year = f_col1.selectbox(
                    "Year",
                    options=saved_years,
                    index=0,
                    key="saved_view_year_sel",
                )

                saved_inst_opts = ["All Instruments"] + sorted(df_saved["instrument_name"].dropna().unique().tolist())
                sel_view_inst = f_col2.selectbox(
                    "Instrument",
                    options=saved_inst_opts,
                    key="saved_view_inst_sel",
                )

                df_filtered_saved = df_saved.copy()
                if sel_view_inst != "All Instruments":
                    df_filtered_saved = df_filtered_saved[df_filtered_saved["instrument_name"] == sel_view_inst]

                full_year_buf = io.BytesIO()
                with pd.ExcelWriter(full_year_buf, engine="openpyxl") as writer:
                    wrote_any = False
                    for q_i in [1, 2, 3, 4]:
                        q_code_i = f"Q{q_i}/{sel_view_year}"
                        sub_q_i = df_filtered_saved[
                            df_filtered_saved["quarter_period"].astype(str).str.lower() == q_code_i.lower()
                        ]
                        sheet_df = sub_q_i[[
                            "quarter_period", "instrument_name", "test_code", "unit", "level_name",
                            "mean_conc", "n_batches", "selected_batches", "chosen_bias_pct", "updated_at"
                        ]].copy()
                        sheet_df["mean_conc"] = sheet_df["mean_conc"].round(3)
                        sheet_df["chosen_bias_pct"] = sheet_df["chosen_bias_pct"].round(3)
                        sheet_df = sheet_df.rename(columns={
                            "quarter_period": "Quarter",
                            "instrument_name": "Instrument",
                            "test_code": "Analyte",
                            "unit": "Unit",
                            "level_name": "Level",
                            "mean_conc": "Mean Assigned",
                            "n_batches": "Months",
                            "selected_batches": "Selected Months",
                            "chosen_bias_pct": "Mean Bias %",
                            "updated_at": "Updated",
                        })
                        sheet_df.to_excel(writer, index=False, sheet_name=f"Q{q_i}_{sel_view_year}")
                        wrote_any = True
                    if not wrote_any:
                        pd.DataFrame().to_excel(writer, index=False, sheet_name="Empty")

                f_col3.download_button(
                    f":material/download: Export All (Q1–Q4 {sel_view_year})",
                    data=full_year_buf.getvalue(),
                    file_name=f"EQA_Bias_All_Quarters_{sel_view_year}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    key="dl_full_year_quarters_btn",
                )

                q_counts = {}
                for q_i in [1, 2, 3, 4]:
                    q_code_i = f"Q{q_i}/{sel_view_year}"
                    sub_i = df_filtered_saved[
                        df_filtered_saved["quarter_period"].astype(str).str.lower() == q_code_i.lower()
                    ]
                    q_counts[q_i] = sub_i["test_code"].nunique()

                q_tabs = st.tabs([
                    f"📅 Q1 ({q_counts[1]})",
                    f"📅 Q2 ({q_counts[2]})",
                    f"📅 Q3 ({q_counts[3]})",
                    f"📅 Q4 ({q_counts[4]})",
                    f"📑 All ({len(df_filtered_saved)})",
                ])

                for idx_q, q_no in enumerate([1, 2, 3, 4]):
                    q_code = f"Q{q_no}/{sel_view_year}"
                    sub_df = df_filtered_saved[
                        df_filtered_saved["quarter_period"].astype(str).str.lower() == q_code.lower()
                    ]
                    with q_tabs[idx_q]:
                        _render_quarter_summary_table(
                            df_q=sub_df,
                            quarter_code=q_code,
                            key_suffix=f"q{q_no}_{sel_view_year}",
                        )

                with q_tabs[4]:
                    _render_quarter_summary_table(
                        df_q=df_filtered_saved,
                        quarter_code=f"All_{sel_view_year}",
                        key_suffix=f"all_q_{sel_view_year}",
                    )
