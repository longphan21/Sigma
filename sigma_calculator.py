import io
from datetime import datetime
from typing import List, Dict, Any, Tuple
import pandas as pd
import streamlit as st

from ui_theme import render_page_banner, render_html, queue_popup, format_status_badge_html
from database import (
    get_all_results_joined,
    get_all_bias_summaries,
    get_all_tea_standards,
    get_all_cv_summaries,
    get_all_iqc_lots,
    get_all_sigma_summaries,
    save_sigma_summary_records,
    delete_sigma_summary_by_test,
    parse_ym_tuple,
)

QUARTER_OPTIONS: List[Tuple[int, str, int]] = [
    (1, "Q1 (Mar)", 3),
    (2, "Q2 (Jun)", 6),
    (3, "Q3 (Sep)", 9),
    (4, "Q4 (Dec)", 12),
]


def evaluate_westgard_sigma(sigma_val: float, num_levels: int = 2) -> Dict[str, str]:
    """
    Phân loại mức Sigma và đề xuất Luật nội kiểm Westgard Sigma tương ứng
    với số mức nồng độ QC (2 Levels hoặc 3 Levels).
    """
    is_3lv = (num_levels == 3)

    if sigma_val >= 6.0:
        return {
            "grade": "World Class (≥ 6σ)",
            "status_code": "PASS",
            "box_cls": "eval-result-pass",
            "rules": "1_3s" if not is_3lv else "1_3s",
            "qc_scheme": "N=2, R=1 (1 luật đơn)" if not is_3lv else "N=3, R=1 (1 luật đơn)",
        }
    elif sigma_val >= 5.0:
        return {
            "grade": "Excellent (5σ – <6σ)",
            "status_code": "PASS",
            "box_cls": "eval-result-pass",
            "rules": "1_3s / 2_2s / R_4s" if not is_3lv else "1_3s / 2of3_2s / R_4s",
            "qc_scheme": "N=2, R=1" if not is_3lv else "N=3, R=1",
        }
    elif sigma_val >= 4.0:
        return {
            "grade": "Good (4σ – <5σ)",
            "status_code": "PASS",
            "box_cls": "eval-result-pass",
            "rules": "1_3s / 2_2s / R_4s / 4_1s" if not is_3lv else "1_3s / 2of3_2s / R_4s / 3_1s",
            "qc_scheme": "N=4, R=1 (hoặc N=2, R=2)" if not is_3lv else "N=3, R=1",
        }
    elif sigma_val >= 3.0:
        return {
            "grade": "Marginal (3σ – <4σ)",
            "status_code": "WARN (3σ–4σ)",
            "box_cls": "eval-result-fail",
            "rules": "1_3s / 2_2s / R_4s / 4_1s / 8_x" if not is_3lv else "1_3s / 2of3_2s / R_4s / 3_1s / 6_x",
            "qc_scheme": "N=4, R=2 (hoặc N=2, R=4)" if not is_3lv else "N=6, R=1 (hoặc N=3, R=2)",
        }
    else:
        return {
            "grade": "Unacceptable (< 3σ)",
            "status_code": "FAIL",
            "box_cls": "eval-result-fail",
            "rules": "1_3s / 2_2s / R_4s / 4_1s / 10_x (Max QC)" if not is_3lv else "1_3s / 2of3_2s / R_4s / 3_1s / 9_x (Max QC)",
            "qc_scheme": "Tăng tần suất QC tối đa + Hành động khắc phục (CAPA)",
        }


def _render_sigma_quarter_summary_table(
    df_q: pd.DataFrame,
    quarter_code: str,
    key_suffix: str,
):
    if df_q.empty:
        render_html(f'<div class="search-result-pill">No saved Sigma records for <b>{quarter_code}</b>.</div>')
        return

    df_show = df_q[[
        "quarter_period", "instrument_name", "test_code", "unit", "level_name",
        "tea_source", "tea_pct", "bias_pct", "cv_pct", "sigma_val",
        "sigma_grade", "westgard_rules", "qc_freq_note", "updated_at"
    ]].copy()

    df_show["tea_pct"] = df_show["tea_pct"].round(2)
    df_show["bias_pct"] = df_show["bias_pct"].round(3)
    df_show["cv_pct"] = df_show["cv_pct"].round(3)
    df_show["sigma_val"] = df_show["sigma_val"].round(2)

    df_display = df_show.rename(columns={
        "quarter_period": "Quarter",
        "instrument_name": "Instrument",
        "test_code": "Analyte",
        "unit": "Unit",
        "level_name": "Level",
        "tea_source": "TEa Source",
        "tea_pct": "TEa %",
        "bias_pct": "Bias %",
        "cv_pct": "CV %",
        "sigma_val": "Sigma (σ)",
        "sigma_grade": "Assessment",
        "westgard_rules": "Westgard Rules",
        "qc_freq_note": "QC Run (N, R)",
        "updated_at": "Updated",
    })

    st.dataframe(
        df_display,
        column_config={
            "TEa %": st.column_config.NumberColumn("TEa %", format="%.2f%%"),
            "Bias %": st.column_config.NumberColumn("Bias %", format="%.3f%%"),
            "CV %": st.column_config.NumberColumn("CV %", format="%.3f%%"),
            "Sigma (σ)": st.column_config.NumberColumn("Sigma (σ)", format="%.2f σ"),
        },
        use_container_width=True,
        hide_index=True,
        key=f"df_sigma_saved_table_{key_suffix}",
    )

    act_c1, act_c2, act_c3 = st.columns([1.2, 2.2, 1.2], vertical_alignment="bottom")
    excel_buf = io.BytesIO()
    with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
        df_display.to_excel(writer, index=False, sheet_name="Sigma_Westgard")
    safe_q_fname = quarter_code.replace("/", "_").replace(" ", "_")

    act_c1.download_button(
        f":material/table_view: Export ({quarter_code})",
        data=excel_buf.getvalue(),
        file_name=f"Six_Sigma_Westgard_{safe_q_fname}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        key=f"dl_sigma_btn_{key_suffix}",
    )

    saved_items = [
        f"{r['quarter_period']} | {r['instrument_name']} | {r['test_code']}"
        for _, r in df_q[["quarter_period", "instrument_name", "test_code"]].drop_duplicates().iterrows()
    ]
    del_item = act_c2.selectbox(
        "Record to delete",
        saved_items,
        label_visibility="collapsed",
        key=f"del_sigma_sel_{key_suffix}",
    )
    if act_c3.button(
        ":material/delete: Delete Record",
        type="secondary",
        use_container_width=True,
        key=f"del_sigma_btn_{key_suffix}",
    ):
        p_q, p_inst, p_test = [x.strip() for x in del_item.split("|", 2)]
        delete_sigma_summary_by_test(p_test, instrument_name=p_inst, quarter_period=p_q)
        queue_popup("Deleted", f"Removed Sigma evaluation of {p_test} ({p_inst}) from {p_q}.", "error")
        st.rerun()


def render_sigma_calculator_page():
    render_page_banner("Six Sigma & Westgard Rules Calculator")

    df_eqa = get_all_results_joined()
    df_bias_all = get_all_bias_summaries()
    df_tea_all = get_all_tea_standards()
    df_cv_all = get_all_cv_summaries()
    df_lots_all = get_all_iqc_lots()
    df_sigma_all = get_all_sigma_summaries()

    if df_eqa.empty and df_bias_all.empty and df_cv_all.empty:
        with st.container(border=True):
            st.markdown("#### :material/info: No Database Records Available")
            st.write("Please import EQA PDF reports and configure Bias, TEa%, and Cumulative CV% first.")
        return

    ym_parsed = (
        [parse_ym_tuple(m) for m in df_eqa["month_year"].dropna().unique().tolist()]
        if not df_eqa.empty
        else []
    )
    years_in_db = sorted(list({yr for yr, _ in ym_parsed if yr > 2000} | {datetime.now().year, 2026}), reverse=True)

    tab_calc, tab_saved = st.tabs([
        "🧮 1. Sigma & Westgard Calculator",
        "📋 2. Saved Quarterly Sigma Summary",
    ])

    with tab_calc:
        # ======================================================================
        # STEP 1: CONFIGURATION (QUARTER, INSTRUMENT, ANALYTE, LEVELS)
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
                key="sig_quarter_no_sel",
            )
            sel_year = c_yr.selectbox(
                "Year",
                options=years_in_db,
                index=0,
                key="sig_year_sel",
            )
            active_quarter_period = f"Q{sel_q_no}/{sel_year}"

            inst_set = set()
            for df_src in (df_eqa, df_bias_all, df_cv_all, df_lots_all):
                if not df_src.empty and "instrument_name" in df_src.columns:
                    inst_set.update(df_src["instrument_name"].dropna().unique().tolist())
            inst_list = sorted([x for x in inst_set if str(x).strip()])

            sel_inst = c_inst.selectbox("Instrument", inst_list, key="sig_inst_sel")

            catalog_map: Dict[str, Tuple[str, str, str]] = {}
            if not df_eqa.empty:
                df_inst_eqa = df_eqa[df_eqa["instrument_name"] == sel_inst]
                for t_code, grp in df_inst_eqa.groupby("test_code"):
                    c_str = str(t_code).strip()
                    f_str = str(grp["test_full_name"].iloc[0]).strip() if not grp.empty else c_str
                    u_str = str(grp["unit"].dropna().iloc[0]).strip() if not grp["unit"].dropna().empty else ""
                    catalog_map[c_str.upper()] = (c_str, f_str, u_str)

            for df_src in (df_tea_all, df_lots_all):
                if not df_src.empty:
                    for _, r in df_src.iterrows():
                        c_str = str(r.get("test_code", "")).strip()
                        if c_str and c_str.upper() not in catalog_map:
                            catalog_map[c_str.upper()] = (
                                c_str,
                                str(r.get("test_full_name", "") or c_str).strip(),
                                str(r.get("unit", "") or "").strip(),
                            )

            test_items = sorted(catalog_map.values(), key=lambda x: x[0].upper())
            test_codes_list = [x[0] for x in test_items]

            saved_sigma_in_quarter = set()
            if not df_sigma_all.empty:
                sub_s_q = df_sigma_all[
                    (df_sigma_all["instrument_name"].astype(str).str.strip().str.lower() == sel_inst.strip().lower())
                    & (df_sigma_all["quarter_period"].astype(str).str.strip().str.lower() == active_quarter_period.lower())
                ]
                saved_sigma_in_quarter = set(sub_s_q["test_code"].astype(str).str.strip().str.upper().tolist())

            test_label_map = {x[0]: f"{x[0]} — {x[1]}" for x in test_items}

            sel_test = c_test.selectbox(
                f"Analyte ({len(test_codes_list)})",
                options=test_codes_list,
                format_func=lambda k: ("✅ " if k.strip().upper() in saved_sigma_in_quarter else "") + test_label_map.get(k, k),
                key=f"sig_test_sel_{sel_inst}",
            )

            num_levels = c_lv.selectbox(
                "Levels",
                options=[2, 3, 1],
                format_func=lambda x: f"{x} Levels" if x > 1 else "1 Level",
                key="sig_num_levels",
            )

            cur_test_info = catalog_map.get(sel_test.upper(), (sel_test, sel_test, ""))
            full_name_str = cur_test_info[1]
            unit_str = cur_test_info[2]

            level_names = (
                ["Level 1 (LOW)", "Level 2 (HIGH)"]
                if num_levels == 2
                else (["Level 1 (LOW)", "Level 2 (MID)", "Level 3 (HIGH)"] if num_levels == 3 else ["Level 1"])
            )

            # Tra cứu dữ liệu Bias đã lưu của Quý
            sub_bias = pd.DataFrame()
            if not df_bias_all.empty:
                sub_bias = df_bias_all[
                    (df_bias_all["instrument_name"].astype(str).str.strip().str.lower() == sel_inst.strip().lower())
                    & (df_bias_all["test_code"].astype(str).str.strip().str.upper() == sel_test.strip().upper())
                    & (df_bias_all["quarter_period"].astype(str).str.strip().str.lower() == active_quarter_period.lower())
                ]

            # Tra cứu dữ liệu CV tích lũy đã lưu của Quý
            sub_cv = pd.DataFrame()
            if not df_cv_all.empty:
                sub_cv = df_cv_all[
                    (df_cv_all["instrument_name"].astype(str).str.strip().str.lower() == sel_inst.strip().lower())
                    & (df_cv_all["test_code"].astype(str).str.strip().str.upper() == sel_test.strip().upper())
                    & (df_cv_all["quarter_period"].astype(str).str.strip().str.lower() == active_quarter_period.lower())
                ]

            # Tra cứu tất cả nguồn TEa của xét nghiệm này theo dòng máy đang chọn
            sub_tea = pd.DataFrame()
            if not df_tea_all.empty:
                sub_tea = df_tea_all[
                    (df_tea_all["instrument_name"].astype(str).str.strip().str.lower() == sel_inst.strip().lower())
                    & (df_tea_all["test_code"].astype(str).str.strip().str.upper() == sel_test.strip().upper())
                    ].sort_values(by=["is_default", "tea_pct"], ascending=[False, False]).reset_index(drop=True)

            has_bias_str = f"✓ {len(sub_bias)} Lv" if not sub_bias.empty else "⚠️ Not saved"
            has_cv_str = f"✓ {len(sub_cv)} Lv" if not sub_cv.empty else "⚠️ Not saved"
            has_tea_str = f"✓ {len(sub_tea)} Sources" if not sub_tea.empty else "⚠️ Not configured"

            render_html(f"""
            <div class="history-meta-bar" style="margin-top:4px; margin-bottom:2px;">
                <span>📌 <b>Period:</b> <span class="date-pill">{active_quarter_period}</span></span>
                <span>🔬 <b>Instrument:</b> <code>{sel_inst}</code></span>
                <span>📐 <b>Bias ({active_quarter_period}):</b> <span class="lot-pill">{has_bias_str}</span></span>
                <span>📊 <b>Cumulative CV ({active_quarter_period}):</b> <span class="lot-pill">{has_cv_str}</span></span>
                <span>🎯 <b>TEa Sources:</b> <span class="lot-pill">{has_tea_str}</span></span>
                <span>✅ <b>Evaluated ({active_quarter_period}):</b> <b>{len(saved_sigma_in_quarter)}/{len(test_codes_list)}</b></span>
            </div>
            """)

        # ======================================================================
        # STEP 2: SELECT OPTIMAL TEa% SOURCE FOR THIS ANALYTE
        # ======================================================================
        with st.container(border=True):
            st.markdown(f"#### :material/rule: 2. Select Optimal TEa% — **{sel_test}** ({full_name_str})")

            tea_opts_map: Dict[str, Tuple[str, float]] = {}
            if not sub_tea.empty:
                for _, r in sub_tea.iterrows():
                    src_name = str(r["tea_source"]).strip()
                    val_pct = float(r["tea_pct"])
                    star = "★ " if bool(r.get("is_default")) else ""
                    lbl = f"{star}{src_name} — TEa = {val_pct:.2f}%"
                    tea_opts_map[lbl] = (src_name, val_pct)

            tea_opts_list = list(tea_opts_map.keys()) + ["✏️ Manual / Custom TEa%"]

            t_col1, t_col2, t_col3 = st.columns([2.2, 1.2, 1.6], vertical_alignment="bottom")
            sel_tea_label = t_col1.selectbox(
                "Available TEa% Sources (from Tab 2)",
                options=tea_opts_list,
                key=f"sig_tea_src_sel_{sel_inst}_{sel_test}",
            )

            if sel_tea_label != "✏️ Manual / Custom TEa%":
                chosen_tea_src, default_tea_val = tea_opts_map[sel_tea_label]
            else:
                chosen_tea_src = "Custom"
                default_tea_val = 10.0

            chosen_tea_pct = t_col2.number_input(
                "Applied TEa %",
                min_value=0.01,
                max_value=300.0,
                value=float(default_tea_val),
                step=0.5,
                format="%.2f",
                key=f"sig_tea_val_{sel_inst}_{sel_test}_{sel_tea_label}",
            )

            chosen_tea_src_final = t_col3.text_input(
                "Source Label",
                value=chosen_tea_src,
                key=f"sig_tea_src_txt_{sel_inst}_{sel_test}_{sel_tea_label}",
            )

            # ======================================================================
            # STEP 3: SIGMA CALCULATION & WESTGARD RULES BY LEVEL
            # ======================================================================
            with st.container(border=True):
                hdr_s1, hdr_s2 = st.columns([3.4, 1.6], vertical_alignment="center")
                with hdr_s1:
                    st.markdown(
                        f"#### :material/verified: 3. Sigma Score & Westgard Rules — **{active_quarter_period}**"
                    )
                with hdr_s2:
                    allow_manual_override = st.checkbox(
                        "✏️ Chỉnh tay Bias% / CV%",
                        value=False,
                        key=f"sig_manual_override_{active_quarter_period}_{sel_inst}_{sel_test}",
                    )

                lv_cols = st.columns(num_levels)
                records_to_save = []

                for idx in range(num_levels):
                    lv_no = idx + 1
                    lv_title = level_names[idx]

                    # Lấy đúng Bias% đã chọn của mức nồng độ này từ Tab 1
                    default_bias = 0.0
                    bias_months_info = "Chưa lưu ở Tab 1"
                    if not sub_bias.empty:
                        m_b = sub_bias[sub_bias["level_no"] == lv_no]
                        if not m_b.empty:
                            default_bias = float(m_b["chosen_bias_pct"].iloc[0] or 0.0)
                            bias_months_info = str(m_b["selected_batches"].iloc[0] or "-")

                    # Lấy đúng CV% tích lũy đã chọn của mức nồng độ này từ Tab 3
                    default_cv = 2.0
                    cv_lots_info = "Chưa lưu ở Tab 3"
                    if not sub_cv.empty:
                        m_c = sub_cv[sub_cv["level_no"] == lv_no]
                        if not m_c.empty and pd.notna(m_c["chosen_cv_pct"].iloc[0]) and float(m_c["chosen_cv_pct"].iloc[0]) > 0:
                            default_cv = float(m_c["chosen_cv_pct"].iloc[0])
                            raw_tot_n = m_c["total_points"].iloc[0]
                            n_disp = f"N={int(float(raw_tot_n))}" if pd.notna(raw_tot_n) and str(raw_tot_n).strip() != "" and float(raw_tot_n) > 0 else "N=Null"
                            cv_lots_info = f"{m_c['selected_lots'].iloc[0]} ({n_disp})"

                    with lv_cols[idx]:
                        st.markdown(f"##### 📌 {lv_title}")

                        if allow_manual_override:
                            in_c1, in_c2 = st.columns(2)
                            bias_val = in_c1.number_input(
                                "Chosen |Bias %|",
                                min_value=0.0,
                                max_value=200.0,
                                value=round(float(default_bias), 3),
                                step=0.05,
                                format="%.3f",
                                key=f"sig_bias_in_{active_quarter_period}_{sel_inst}_{sel_test}_lv{lv_no}",
                            )
                            cv_val = in_c2.number_input(
                                "Cumulative CV %",
                                min_value=0.001,
                                max_value=200.0,
                                value=round(max(0.001, float(default_cv)), 3),
                                step=0.05,
                                format="%.3f",
                                key=f"sig_cv_in_{active_quarter_period}_{sel_inst}_{sel_test}_lv{lv_no}",
                            )
                        else:
                            bias_val = round(float(default_bias), 3)
                            cv_val = round(max(0.001, float(default_cv)), 3)
                            top_m1, top_m2 = st.columns(2)
                            top_m1.metric("Chosen |Bias %|", f"{bias_val:.3f}%")
                            top_m2.metric("Cumulative CV %", f"{cv_val:.3f}%")

                        sigma_raw = (float(chosen_tea_pct) - float(bias_val)) / float(cv_val) if float(
                            cv_val) > 0 else 0.0
                        sigma_2dec = round(sigma_raw, 2)
                        wg_info = evaluate_westgard_sigma(sigma_2dec, num_levels=num_levels)

                        badge_html = format_status_badge_html(wg_info["status_code"])
                        render_html(f"""
                            <div class="eval-result-box {wg_info['box_cls']}" style="margin-bottom:8px;">
                                <span><b>{wg_info['grade']}</b></span>
                                {badge_html}
                            </div>
                            """)

                        m_1, m_2 = st.columns([1.0, 1.4])
                        m_1.metric("Sigma (σ)", f"{sigma_2dec:.2f} σ")
                        m_2.metric("Westgard Rules", wg_info["rules"])

                        formula_str = f"({chosen_tea_pct:.2f}% - {bias_val:.3f}%) / {cv_val:.3f}% = {sigma_2dec:.2f}σ"
                        render_html(f"""
                            <div class="history-meta-bar">
                                <span><b>Formula:</b> <code>{formula_str}</code></span>
                                <span><b>QC Scheme:</b> <b>{wg_info['qc_scheme']}</b></span>
                                <span><b>Bias Months:</b> <code>{bias_months_info}</code></span>
                                <span><b>IQC Lots:</b> <code>{cv_lots_info}</code></span>
                            </div>
                            """)

                        records_to_save.append({
                            "instrument_name": sel_inst,
                            "test_code": sel_test,
                            "test_full_name": full_name_str,
                            "unit": unit_str,
                            "level_no": lv_no,
                            "level_name": lv_title,
                            "tea_source": str(chosen_tea_src_final).strip() or "Custom",
                            "tea_pct": float(chosen_tea_pct),
                            "bias_pct": float(bias_val),
                            "cv_pct": float(cv_val),
                            "sigma_val": sigma_2dec,
                            "sigma_grade": wg_info["grade"],
                            "westgard_rules": wg_info["rules"],
                            "qc_freq_note": wg_info["qc_scheme"],
                        })

                btn_col, _ = st.columns([1.6, 3.4])
                with btn_col:
                    if st.button(
                            f":material/save: Save Sigma & Westgard to {active_quarter_period}",
                            type="primary",
                            use_container_width=True,
                    ):
                        save_sigma_summary_records(
                            instrument_name=sel_inst,
                            test_code=sel_test,
                            level_records=records_to_save,
                            quarter_period=active_quarter_period,
                        )
                        queue_popup(
                            "Saved Successfully",
                            f"Saved Sigma & Westgard evaluation for {sel_test} ({sel_inst}) to {active_quarter_period}.",
                            "success",
                        )
                        st.rerun()

    # ==========================================================================
    # TAB 2: SAVED QUARTERLY SIGMA & WESTGARD SUMMARY (Q1, Q2, Q3, Q4)
    # ==========================================================================
    with tab_saved:
        df_saved = get_all_sigma_summaries()
        with st.container(border=True):
            st.markdown("#### :material/table_chart: Quarterly Six Sigma & Westgard Summary")

            if df_saved.empty:
                st.write("No saved Sigma evaluations yet.")
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
                    key="sig_saved_view_year_sel",
                )

                saved_inst_opts = ["All Instruments"] + sorted(df_saved["instrument_name"].dropna().unique().tolist())
                sel_view_inst = f_col2.selectbox(
                    "Instrument",
                    options=saved_inst_opts,
                    key="sig_saved_view_inst_sel",
                )

                df_filtered_saved = df_saved.copy()
                if sel_view_inst != "All Instruments":
                    df_filtered_saved = df_filtered_saved[df_filtered_saved["instrument_name"] == sel_view_inst]

                # Thống kê nhanh phân bố Sigma của các bản ghi đang lọc
                total_lv_evals = len(df_filtered_saved)
                cnt_6s = int((df_filtered_saved["sigma_val"] >= 6.0).sum())
                cnt_4to6 = int(((df_filtered_saved["sigma_val"] >= 4.0) & (df_filtered_saved["sigma_val"] < 6.0)).sum())
                cnt_3to4 = int(((df_filtered_saved["sigma_val"] >= 3.0) & (df_filtered_saved["sigma_val"] < 4.0)).sum())
                cnt_lt3 = int((df_filtered_saved["sigma_val"] < 3.0).sum())

                mc1, mc2, mc3, mc4 = st.columns(4)
                mc1.metric("≥ 6.0 Sigma (World Class)", f"{cnt_6s}/{total_lv_evals}")
                mc2.metric("4.0 – <6.0 Sigma (Good/Exc)", f"{cnt_4to6}/{total_lv_evals}")
                mc3.metric("3.0 – <4.0 Sigma (Marginal)", f"{cnt_3to4}/{total_lv_evals}")
                mc4.metric("< 3.0 Sigma (Unacceptable)", f"{cnt_lt3}/{total_lv_evals}")

                full_year_buf = io.BytesIO()
                with pd.ExcelWriter(full_year_buf, engine="openpyxl") as writer:
                    for q_i in [1, 2, 3, 4]:
                        q_code_i = f"Q{q_i}/{sel_view_year}"
                        sub_q_i = df_filtered_saved[
                            df_filtered_saved["quarter_period"].astype(str).str.lower() == q_code_i.lower()
                        ]
                        sheet_df = sub_q_i[[
                            "quarter_period", "instrument_name", "test_code", "unit", "level_name",
                            "tea_source", "tea_pct", "bias_pct", "cv_pct", "sigma_val",
                            "sigma_grade", "westgard_rules", "qc_freq_note", "updated_at"
                        ]].copy()
                        sheet_df["tea_pct"] = sheet_df["tea_pct"].round(2)
                        sheet_df["bias_pct"] = sheet_df["bias_pct"].round(3)
                        sheet_df["cv_pct"] = sheet_df["cv_pct"].round(3)
                        sheet_df["sigma_val"] = sheet_df["sigma_val"].round(2)
                        sheet_df = sheet_df.rename(columns={
                            "quarter_period": "Quarter",
                            "instrument_name": "Instrument",
                            "test_code": "Analyte",
                            "unit": "Unit",
                            "level_name": "Level",
                            "tea_source": "TEa Source",
                            "tea_pct": "TEa %",
                            "bias_pct": "Bias %",
                            "cv_pct": "CV %",
                            "sigma_val": "Sigma (σ)",
                            "sigma_grade": "Assessment",
                            "westgard_rules": "Westgard Rules",
                            "qc_freq_note": "QC Run (N, R)",
                            "updated_at": "Updated",
                        })
                        sheet_df.to_excel(writer, index=False, sheet_name=f"Q{q_i}_{sel_view_year}")

                f_col3.download_button(
                    f":material/download: Export All (Q1–Q4 {sel_view_year})",
                    data=full_year_buf.getvalue(),
                    file_name=f"Six_Sigma_Westgard_All_Quarters_{sel_view_year}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    key="dl_sigma_full_year_quarters_btn",
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
                        _render_sigma_quarter_summary_table(
                            df_q=sub_df,
                            quarter_code=q_code,
                            key_suffix=f"sig_q{q_no}_{sel_view_year}",
                        )

                with q_tabs[4]:
                    _render_sigma_quarter_summary_table(
                        df_q=df_filtered_saved,
                        quarter_code=f"All_{sel_view_year}",
                        key_suffix=f"sig_all_q_{sel_view_year}",
                    )