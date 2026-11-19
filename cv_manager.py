import io
from datetime import datetime, date
from typing import List, Dict, Any, Tuple, Optional
import pandas as pd
import streamlit as st
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from ui_theme import render_page_banner, render_html, queue_popup, format_status_badge_html
from database import (
    get_all_results_joined,
    get_all_iqc_lots,
    save_iqc_lot,
    delete_iqc_lot,
    get_all_cv_summaries,
    save_cv_summary_records,
    delete_cv_summary_by_test,
    parse_ym_tuple,
)

QUARTER_OPTIONS: List[Tuple[int, str, int]] = [
    (1, "Q1 (Mar)", 3),
    (2, "Q2 (Jun)", 6),
    (3, "Q3 (Sep)", 9),
    (4, "Q4 (Dec)", 12),
]

HEMATOLOGY_NULL_DEFAULT_TESTS = {
    "HB", "HGB", "RBC", "RBC-OPT", "RBC-IMP",
    "WBC", "WBC-OPT", "WBC-IMP",
    "PLT", "PLT-OPT", "PLT-IMP",
    "HCT", "MCV", "MCH", "MCHC", "RDW", "MPV",
}

MIN_PICK_DATE = date(2020, 1, 1)
MAX_PICK_DATE = date(2035, 12, 31)


def _format_lot_period(start_d: Any, end_d: Any) -> str:
    s = str(start_d or "").strip()
    e = str(end_d or "").strip()
    if s and e:
        return f"{s} – {e}"
    return s or e or "-"


def _parse_date_safe(val: Any, fallback: date) -> date:
    """Chuyển chuỗi ngày (DD/MM/YYYY, MM/YYYY, YYYY-MM-DD) sang đối tượng date an toàn cho lịch."""
    if isinstance(val, datetime):
        d = val.date()
    elif isinstance(val, date):
        d = val
    else:
        s = str(val or "").strip()
        d = None
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%m/%Y"):
            try:
                parsed = datetime.strptime(s, fmt)
                d = date(parsed.year, parsed.month, 1) if fmt == "%m/%Y" else parsed.date()
                break
            except ValueError:
                continue
        if d is None:
            d = fallback

    if d < MIN_PICK_DATE:
        return MIN_PICK_DATE
    if d > MAX_PICK_DATE:
        return MAX_PICK_DATE
    return d


def _is_valid_pos_num(val: Any) -> bool:
    if val is None or pd.isna(val):
        return False
    try:
        return float(val) > 0
    except (ValueError, TypeError):
        return False


def _style_cv_worksheet(ws, df_sheet: pd.DataFrame):
    """Định dạng bảng Excel cho báo cáo CV% tích lũy."""
    header_fill = PatternFill(start_color="1B5E20", end_color="1B5E20", fill_type="solid")
    zebra_fill = PatternFill(start_color="F4FAF6", end_color="F4FAF6", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    body_font = Font(name="Calibri", size=10, color="0A2540")
    thin_side = Side(style="thin", color="D0D7DE")
    border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

    n_cols = len(df_sheet.columns)
    n_rows = len(df_sheet) + 1

    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = 24
    if n_cols > 0:
        ws.auto_filter.ref = f"A1:{get_column_letter(n_cols)}{max(n_rows, 1)}"

    col_names = list(df_sheet.columns)
    for c_idx in range(1, n_cols + 1):
        cell = ws.cell(row=1, column=c_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border

    for r_idx in range(2, n_rows + 1):
        ws.row_dimensions[r_idx].height = 20
        is_zebra = (r_idx % 2 == 1)
        for c_idx in range(1, n_cols + 1):
            cell = ws.cell(row=r_idx, column=c_idx)
            col_name = col_names[c_idx - 1]
            cell.font = body_font
            cell.border = border
            if is_zebra:
                cell.fill = zebra_fill

            if col_name in ("Pooled Mean", "Cumulative CV %"):
                cell.alignment = Alignment(horizontal="right", vertical="center")
                if cell.value is not None and cell.value != "":
                    cell.number_format = "0.000"
            elif col_name in ("Lots", "Total Points (N)"):
                cell.alignment = Alignment(horizontal="center", vertical="center")
                if cell.value is not None and cell.value != "":
                    cell.number_format = "0"
            elif col_name in ("Quarter", "Analyte", "Unit"):
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

    for c_idx, col_name in enumerate(col_names, start=1):
        max_len = len(str(col_name))
        if not df_sheet.empty:
            for val in df_sheet[col_name]:
                if pd.notna(val):
                    max_len = max(max_len, len(str(val)))
        ws.column_dimensions[get_column_letter(c_idx)].width = min(max(max_len + 4, 11), 42)


def _calc_pooled_cv(df_sub: pd.DataFrame) -> Dict[str, Any]:
    """
    Tính CV cộng dồn:
    - Nếu các Lot đều có số điểm n > 0: CV_cộng_dồn = Σ(CV_i * n_i) / Σ(n_i)
    - Nếu Lot thuộc nhóm Huyết học (Mean, SD, n = Null): lấy trực tiếp CV% (1 lot) hoặc trung bình cộng CV% (nhiều lot).
    """
    if df_sub.empty:
        return {
            "n_lots": 0,
            "total_points": 0,
            "pooled_cv_3dec": 0.0,
            "pooled_mean_3dec": None,
            "lots_str": "-",
            "formula_detail": "-",
        }

    valid = df_sub.dropna(subset=["cv_pct"]).copy()
    valid = valid[valid["cv_pct"] > 0]
    if valid.empty:
        return {
            "n_lots": 0,
            "total_points": 0,
            "pooled_cv_3dec": 0.0,
            "pooled_mean_3dec": None,
            "lots_str": "-",
            "formula_detail": "-",
        }

    cv_vals = valid["cv_pct"].astype(float).tolist()
    n_raw_list = valid["n_points"].tolist()
    mean_raw_list = valid["mean_val"].tolist()

    lot_with_period = []
    for _, r in valid.iterrows():
        l_no = str(r.get("lot_no", "")).strip()
        p_str = _format_lot_period(r.get("start_date", ""), r.get("cutoff_date", ""))
        lot_with_period.append(f"{l_no} ({p_str})" if p_str != "-" else l_no)

    all_have_n = all(_is_valid_pos_num(n_v) for n_v in n_raw_list)

    if all_have_n:
        n_vals = [int(float(n_v)) for n_v in n_raw_list]
        total_n: Optional[int] = sum(n_vals)
        weighted_cv_sum = sum(c * n for c, n in zip(cv_vals, n_vals))
        pooled_cv = round(weighted_cv_sum / total_n, 3) if total_n and total_n > 0 else 0.0

        valid_means = [(float(m), n) for m, n in zip(mean_raw_list, n_vals) if _is_valid_pos_num(m)]
        if valid_means:
            m_sum = sum(m * n for m, n in valid_means)
            n_m_sum = sum(n for _, n in valid_means)
            pooled_mean: Optional[float] = round(m_sum / n_m_sum, 3) if n_m_sum > 0 else None
        else:
            pooled_mean = None

        if len(cv_vals) == 1:
            formula_str = f"{cv_vals[0]:.3f}% (n={n_vals[0]})"
        else:
            num_terms = " + ".join([f"({c:.3f}% × {n})" for c, n in zip(cv_vals, n_vals)])
            den_terms = " + ".join([str(n) for n in n_vals])
            formula_str = f"[{num_terms}] / ({den_terms}) = {pooled_cv:.3f}%"
    else:
        total_n = None
        pooled_cv = round(sum(cv_vals) / len(cv_vals), 3)
        valid_m_only = [float(m) for m in mean_raw_list if _is_valid_pos_num(m)]
        pooled_mean = round(sum(valid_m_only) / len(valid_m_only), 3) if valid_m_only else None

        if len(cv_vals) == 1:
            formula_str = f"{cv_vals[0]:.3f}% (Mean/SD/n = Null)"
        else:
            terms = " + ".join([f"{c:.3f}%" for c in cv_vals])
            formula_str = f"({terms}) / {len(cv_vals)} = {pooled_cv:.3f}% (n = Null)"

    return {
        "n_lots": len(valid),
        "total_points": total_n,
        "pooled_cv_3dec": pooled_cv,
        "pooled_mean_3dec": pooled_mean,
        "lots_str": ", ".join(lot_with_period),
        "formula_detail": formula_str,
    }


def _render_cv_quarter_summary_table(
    df_q: pd.DataFrame,
    quarter_code: str,
    key_suffix: str,
):
    if df_q.empty:
        render_html(f'<div class="search-result-pill">No saved CV% records for <b>{quarter_code}</b>.</div>')
        return

    df_show = df_q[[
        "quarter_period", "instrument_name", "test_code", "unit", "level_name",
        "pooled_mean", "n_lots", "selected_lots", "total_points", "chosen_cv_pct", "updated_at"
    ]].copy()
    df_show["pooled_mean"] = pd.to_numeric(df_show["pooled_mean"], errors="coerce").round(3)
    df_show["total_points"] = pd.to_numeric(df_show["total_points"], errors="coerce")
    df_show["chosen_cv_pct"] = pd.to_numeric(df_show["chosen_cv_pct"], errors="coerce").round(3)

    df_display = df_show.rename(columns={
        "quarter_period": "Quarter",
        "instrument_name": "Instrument",
        "test_code": "Analyte",
        "unit": "Unit",
        "level_name": "Level",
        "pooled_mean": "Pooled Mean",
        "n_lots": "Lots",
        "selected_lots": "Selected Lots (From – To)",
        "total_points": "Total Points (N)",
        "chosen_cv_pct": "Cumulative CV %",
        "updated_at": "Updated",
    })

    st.dataframe(
        df_display,
        column_config={
            "Pooled Mean": st.column_config.NumberColumn("Pooled Mean", format="%.3f"),
            "Total Points (N)": st.column_config.NumberColumn("Total Points (N)", format="%d"),
            "Cumulative CV %": st.column_config.NumberColumn("Cumulative CV %", format="%.3f%%"),
        },
        use_container_width=True,
        hide_index=True,
        key=f"df_cv_saved_table_{key_suffix}",
    )

    act_c1, act_c2, act_c3 = st.columns([1.2, 2.2, 1.2], vertical_alignment="bottom")
    excel_buf = io.BytesIO()
    with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
        df_display.to_excel(writer, index=False, sheet_name="CV_Summary")
        _style_cv_worksheet(writer.sheets["CV_Summary"], df_display)
    safe_q_fname = quarter_code.replace("/", "_").replace(" ", "_")

    act_c1.download_button(
        f":material/table_view: Export Excel ({quarter_code})",
        data=excel_buf.getvalue(),
        file_name=f"IQC_CV_{safe_q_fname}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        key=f"dl_cv_btn_{key_suffix}",
    )

    saved_items = [
        f"{r['quarter_period']} | {r['instrument_name']} | {r['test_code']}"
        for _, r in df_q[["quarter_period", "instrument_name", "test_code"]].drop_duplicates().iterrows()
    ]
    del_item = act_c2.selectbox(
        "Record to delete",
        saved_items,
        label_visibility="collapsed",
        key=f"del_cv_sel_{key_suffix}",
    )
    if act_c3.button(
        ":material/delete: Delete Record",
        type="secondary",
        use_container_width=True,
        key=f"del_cv_btn_{key_suffix}",
    ):
        p_q, p_inst, p_test = [x.strip() for x in del_item.split("|", 2)]
        delete_cv_summary_by_test(p_test, instrument_name=p_inst, quarter_period=p_q)
        queue_popup("Deleted", f"Removed CV% summary of {p_test} ({p_inst}) from {p_q}.", "error")
        st.rerun()


def render_cv_manager_page():
    render_page_banner("IQC Lot & Cumulative CV% Manager")

    df_eqa = get_all_results_joined()
    df_lots = get_all_iqc_lots()
    df_saved_all = get_all_cv_summaries()

    if df_eqa.empty and df_lots.empty:
        with st.container(border=True):
            st.markdown("#### :material/info: No Instrument / Analyte Data Available")
            st.write("Please upload a VEQAS PDF report in **1. Bias Calculator → Import PDF** first.")
        return

    ym_parsed = (
        [parse_ym_tuple(m) for m in df_eqa["month_year"].dropna().unique().tolist()]
        if not df_eqa.empty
        else []
    )
    years_in_db = sorted(list({yr for yr, _ in ym_parsed if yr > 2000} | {datetime.now().year, 2026}), reverse=True)

    tab_calc, tab_saved = st.tabs([
        "🧮 1. Lot Manager & Cumulative CV%",
        "📋 2. Saved Quarterly CV Summary",
    ])

    with tab_calc:
        # ======================================================================
        # STEP 1: CONFIGURATION (QUARTER, INSTRUMENT, ANALYTE, LEVELS)
        # ======================================================================
        with st.container(border=True):
            st.markdown("#### :material/tune: 1. Configuration")
            c_q, c_yr, c_inst, c_test, c_lv = st.columns([0.85, 0.65, 1.70, 1.80, 0.80], vertical_alignment="bottom")

            q_idx_map = {q_no: label for q_no, label, _ in QUARTER_OPTIONS}
            sel_q_no = c_q.selectbox(
                "Quarter",
                options=[1, 2, 3, 4],
                format_func=lambda x: q_idx_map[x],
                index=2,
                key="cv_quarter_no_sel",
            )
            sel_year = c_yr.selectbox(
                "Year",
                options=years_in_db,
                index=0,
                key="cv_year_sel",
            )
            active_quarter_period = f"Q{sel_q_no}/{sel_year}"

            inst_set = set()
            if not df_eqa.empty:
                inst_set.update(df_eqa["instrument_name"].dropna().unique().tolist())
            if not df_lots.empty:
                inst_set.update(df_lots["instrument_name"].dropna().unique().tolist())
            inst_list = sorted([x for x in inst_set if str(x).strip()])

            sel_inst = c_inst.selectbox("Instrument", inst_list, key="cv_inst_sel")

            if st.session_state.get("cv_prev_inst") != sel_inst:
                st.session_state["cv_prev_inst"] = sel_inst
                st.session_state["cv_lot_edit_mode"] = "+ New Lot"

            catalog_map: Dict[str, Tuple[str, str, str]] = {}
            if not df_eqa.empty:
                df_inst_eqa = df_eqa[df_eqa["instrument_name"] == sel_inst]
                for t_code, grp in df_inst_eqa.groupby("test_code"):
                    c_str = str(t_code).strip()
                    f_str = str(grp["test_full_name"].iloc[0]).strip() if not grp.empty else c_str
                    u_str = str(grp["unit"].dropna().iloc[0]).strip() if not grp["unit"].dropna().empty else ""
                    catalog_map[c_str.upper()] = (c_str, f_str, u_str)

            if not df_lots.empty:
                df_inst_lots = df_lots[df_lots["instrument_name"] == sel_inst]
                for _, r in df_inst_lots.iterrows():
                    c_str = str(r.get("test_code", "")).strip()
                    if c_str and c_str.upper() not in catalog_map:
                        catalog_map[c_str.upper()] = (
                            c_str,
                            str(r.get("test_full_name", "") or c_str).strip(),
                            str(r.get("unit", "") or "").strip(),
                        )

            test_items = sorted(catalog_map.values(), key=lambda x: x[0].upper())
            test_codes_list = [x[0] for x in test_items]

            lot_cnt_by_test = {}
            if not df_lots.empty:
                sub_l_inst = df_lots[df_lots["instrument_name"] == sel_inst]
                for tc, grp in sub_l_inst.groupby("test_code"):
                    lot_cnt_by_test[str(tc).upper()] = len(grp)

            test_label_map = {
                x[0]: f"{x[0]} — {x[1]} ({lot_cnt_by_test.get(x[0].upper(), 0)} lots)"
                for x in test_items
            }

            saved_tests_in_quarter = set()
            if not df_saved_all.empty:
                sub_q_saved = df_saved_all[
                    (df_saved_all["instrument_name"].astype(str).str.strip().str.lower() == sel_inst.strip().lower())
                    & (df_saved_all["quarter_period"].astype(str).str.strip().str.lower() == active_quarter_period.lower())
                ]
                saved_tests_in_quarter = set(sub_q_saved["test_code"].astype(str).str.strip().str.upper().tolist())

            # Khóa cứng trạng thái Analyte theo từng máy, không reset về index 0 khi nhãn (lots / ✅) thay đổi
            if "cv_persisted_test_by_inst" not in st.session_state:
                st.session_state["cv_persisted_test_by_inst"] = {}

            test_widget_key = f"cv_test_sel_{sel_inst}"

            def _on_test_change(inst_name: str, w_key: str):
                picked_t = st.session_state.get(w_key)
                if picked_t:
                    st.session_state["cv_persisted_test_by_inst"][inst_name] = picked_t
                st.session_state["cv_lot_edit_mode"] = "+ New Lot"

            persisted_test = st.session_state["cv_persisted_test_by_inst"].get(sel_inst)
            if persisted_test not in test_codes_list:
                persisted_test = test_codes_list[0]
                st.session_state["cv_persisted_test_by_inst"][sel_inst] = persisted_test

            default_test_idx = test_codes_list.index(persisted_test)

            sel_test = c_test.selectbox(
                f"Analyte ({len(test_codes_list)})",
                options=test_codes_list,
                index=default_test_idx,
                format_func=lambda k: ("✅ " if k.strip().upper() in saved_tests_in_quarter else "") + test_label_map.get(k, k),
                key=test_widget_key,
                on_change=_on_test_change,
                args=(sel_inst, test_widget_key),
            )
            st.session_state["cv_persisted_test_by_inst"][sel_inst] = sel_test

            num_levels = c_lv.selectbox(
                "Levels",
                options=[2, 3, 1],
                format_func=lambda x: f"{x} Levels" if x > 1 else "1 Level",
                key="cv_num_levels",
            )

            cur_test_info = catalog_map.get(sel_test.upper(), (sel_test, sel_test, ""))
            full_name_str = cur_test_info[1]
            unit_str = cur_test_info[2]

            level_names = (
                ["Level 1 (LOW)", "Level 2 (HIGH)"]
                if num_levels == 2
                else (["Level 1 (LOW)", "Level 2 (MID)", "Level 3 (HIGH)"] if num_levels == 3 else ["Level 1"])
            )

            df_test_lots = (
                df_lots[
                    (df_lots["instrument_name"].astype(str).str.lower() == sel_inst.lower())
                    & (df_lots["test_code"].astype(str).str.upper() == sel_test.upper())
                ].copy()
                if not df_lots.empty
                else pd.DataFrame(columns=df_lots.columns if not df_lots.empty else [])
            )

            active_lots_cnt = (
                int((df_test_lots["lot_status"].astype(str).str.lower() == "active").sum())
                if not df_test_lots.empty
                else 0
            )

            render_html(f"""
            <div class="history-meta-bar" style="margin-top:4px; margin-bottom:2px;">
                <span>📌 <b>Period:</b> <span class="date-pill">{active_quarter_period}</span></span>
                <span>🔬 <b>Instrument:</b> <code>{sel_inst}</code></span>
                <span>🧪 <b>Analyte:</b> <b>{sel_test}</b> ({unit_str or '-'})</span>
                <span>📦 <b>Saved Lots ({sel_test}):</b> <span class="lot-pill">{len(df_test_lots)} ({active_lots_cnt} Active)</span></span>
                <span>✅ <b>Saved ({active_quarter_period}):</b> <b>{len(saved_tests_in_quarter)}/{len(test_codes_list)}</b></span>
            </div>
            """)

        # ======================================================================
        # STEP 2: ADD / UPDATE IQC LOT (GIỮ NGUYÊN HIỆN TRẠNG KHI ĐỔI LEVEL/TEST/SAVE)
        # ======================================================================
        with st.container(border=True):
            st.markdown(f"#### :material/inventory_2: 2. Add / Update IQC Lot — **{sel_test}** ({full_name_str})")

            existing_lot_opts = ["+ New Lot"]
            lot_lookup: Dict[str, Dict[str, Any]] = {}
            if not df_test_lots.empty:
                for _, r in df_test_lots.iterrows():
                    p_txt = _format_lot_period(r.get("start_date", ""), r.get("cutoff_date", ""))
                    n_txt = f"n={int(r['n_points'])}" if _is_valid_pos_num(r.get("n_points")) else "n=Null"
                    lbl = f"[L{int(r['level_no'])}] Lot {r['lot_no']} ({p_txt} | {r['lot_status']} | {n_txt})"
                    existing_lot_opts.append(lbl)
                    lot_lookup[lbl] = r.to_dict()

            mode_options = [
                "Auto (SD/Mean)",
                "Manual CV%",
                "CV% Only (Null Mean/SD/n)",
            ]

            # Tự động bật chế độ Null khi chuyển qua lại giữa nhóm Huyết học và Sinh hóa, không reset nếu cùng nhóm
            cur_is_heme = sel_test.strip().upper() in HEMATOLOGY_NULL_DEFAULT_TESTS
            if (
                "cv_in_calc_mode" not in st.session_state
                or st.session_state.get("cv_prev_is_heme") != cur_is_heme
            ):
                st.session_state["cv_prev_is_heme"] = cur_is_heme
                st.session_state["cv_in_calc_mode"] = (
                    "CV% Only (Null Mean/SD/n)" if cur_is_heme else "Auto (SD/Mean)"
                )

            # Khởi tạo 1 lần duy nhất các trường nhập liệu Bước 2 để không bị mất khi đổi Level/Analyte hoặc bấm Save
            if "cv_lot_edit_mode" not in st.session_state or st.session_state["cv_lot_edit_mode"] not in existing_lot_opts:
                st.session_state["cv_lot_edit_mode"] = "+ New Lot"
            if "cv_in_lv" not in st.session_state:
                st.session_state["cv_in_lv"] = 1
            if int(st.session_state["cv_in_lv"]) > num_levels:
                st.session_state["cv_in_lv"] = num_levels
            if "cv_in_lotno" not in st.session_state:
                st.session_state["cv_in_lotno"] = ""
            if "cv_in_status" not in st.session_state:
                st.session_state["cv_in_status"] = "Active"
            if "cv_in_sdate" not in st.session_state:
                st.session_state["cv_in_sdate"] = _parse_date_safe(f"01/01/{sel_year}", date(2026, 1, 1))
            if "cv_in_cdate" not in st.session_state:
                st.session_state["cv_in_cdate"] = _parse_date_safe(date.today(), date.today())
            if "cv_in_mean" not in st.session_state:
                st.session_state["cv_in_mean"] = 100.0
            if "cv_in_sd" not in st.session_state:
                st.session_state["cv_in_sd"] = 2.0
            if "cv_in_cv_man" not in st.session_state:
                st.session_state["cv_in_cv_man"] = 2.0
            if "cv_in_n" not in st.session_state:
                st.session_state["cv_in_n"] = 20

            def _on_edit_lot_change(lot_map: Dict[str, Dict[str, Any]], max_lv: int):
                chosen = st.session_state.get("cv_lot_edit_mode", "+ New Lot")
                pre = lot_map.get(chosen)
                if not pre:
                    return

                lv_val = int(pre.get("level_no", 1) or 1)
                st.session_state["cv_in_lv"] = min(max(1, lv_val), max_lv)
                st.session_state["cv_in_lotno"] = str(pre.get("lot_no", "")).strip()
                st.session_state["cv_in_status"] = (
                    "Closed" if str(pre.get("lot_status", "Active")).strip().lower() == "closed" else "Active"
                )
                st.session_state["cv_in_sdate"] = _parse_date_safe(
                    pre.get("start_date"), date(int(sel_year), 1, 1)
                )
                st.session_state["cv_in_cdate"] = _parse_date_safe(
                    pre.get("cutoff_date"), date.today()
                )

                if not _is_valid_pos_num(pre.get("n_points")):
                    st.session_state["cv_in_calc_mode"] = "CV% Only (Null Mean/SD/n)"
                    st.session_state["cv_in_cv_man"] = (
                        max(0.001, float(pre.get("cv_pct")))
                        if _is_valid_pos_num(pre.get("cv_pct"))
                        else 2.0
                    )
                else:
                    st.session_state["cv_in_calc_mode"] = "Auto (SD/Mean)"
                    st.session_state["cv_in_mean"] = (
                        float(pre.get("mean_val")) if _is_valid_pos_num(pre.get("mean_val")) else 100.0
                    )
                    st.session_state["cv_in_sd"] = (
                        float(pre.get("sd_val")) if _is_valid_pos_num(pre.get("sd_val")) else 2.0
                    )
                    st.session_state["cv_in_cv_man"] = (
                        max(0.001, float(pre.get("cv_pct")))
                        if _is_valid_pos_num(pre.get("cv_pct"))
                        else 2.0
                    )
                    st.session_state["cv_in_n"] = max(1, int(float(pre.get("n_points"))))

            r1_c1, r1_c2, r1_c3, r1_c4, r1_c5, r1_c6 = st.columns(
                [1.25, 0.95, 0.85, 0.85, 1.25, 1.25], vertical_alignment="bottom"
            )

            r1_c1.selectbox(
                "Edit Existing / New",
                options=existing_lot_opts,
                key="cv_lot_edit_mode",
                on_change=_on_edit_lot_change,
                args=(lot_lookup, num_levels),
            )

            sel_lv_no = r1_c2.selectbox(
                "QC Level",
                options=list(range(1, num_levels + 1)),
                format_func=lambda idx: level_names[idx - 1],
                key="cv_in_lv",
            )

            lot_no_in = r1_c3.text_input(
                "Lot No",
                placeholder="e.g., 62159",
                key="cv_in_lotno",
            )

            status_in = r1_c4.selectbox(
                "Lot Status",
                options=["Active", "Closed"],
                format_func=lambda s: "🟢 Active" if s == "Active" else "🔒 Closed",
                key="cv_in_status",
            )

            from_date_in = r1_c5.date_input(
                "From Date (Từ ngày)",
                min_value=MIN_PICK_DATE,
                max_value=MAX_PICK_DATE,
                format="DD/MM/YYYY",
                key="cv_in_sdate",
            )

            to_date_in = r1_c6.date_input(
                "To Date (Đến ngày)",
                min_value=MIN_PICK_DATE,
                max_value=MAX_PICK_DATE,
                format="DD/MM/YYYY",
                key="cv_in_cdate",
            )

            r2_c1, r2_c2, r2_c3, r2_c4, r2_c5, r2_c6 = st.columns(
                [1.25, 0.95, 0.95, 0.95, 1.2, 1.2], vertical_alignment="bottom"
            )

            calc_mode = r2_c1.selectbox(
                "CV% Input Mode",
                options=mode_options,
                key="cv_in_calc_mode",
            )

            is_null_mode = (calc_mode == "CV% Only (Null Mean/SD/n)")

            if is_null_mode:
                r2_c2.text_input(
                    f"Mean ({unit_str or 'val'})",
                    value="Null",
                    disabled=True,
                    key="cv_null_mean_disp",
                )
                r2_c3.text_input(
                    f"SD ({unit_str or 'val'})",
                    value="Null",
                    disabled=True,
                    key="cv_null_sd_disp",
                )
                cv_in = r2_c4.number_input(
                    "CV % (Manual)",
                    min_value=0.001,
                    max_value=200.0,
                    step=0.05,
                    format="%.3f",
                    key="cv_in_cv_man",
                )
                r2_c5.text_input(
                    "Total QC Points (n)",
                    value="Null",
                    disabled=True,
                    key="cv_null_n_disp",
                )
                mean_to_save: Optional[float] = None
                sd_to_save: Optional[float] = None
                n_to_save: Optional[int] = None
            else:
                mean_in = r2_c2.number_input(
                    f"Mean ({unit_str or 'val'})",
                    min_value=0.0,
                    max_value=1000000.0,
                    step=0.1,
                    format="%.3f",
                    key="cv_in_mean",
                )

                sd_in = r2_c3.number_input(
                    f"SD ({unit_str or 'val'})",
                    min_value=0.0,
                    max_value=100000.0,
                    step=0.01,
                    format="%.4f",
                    key="cv_in_sd",
                )

                auto_cv = round((sd_in / mean_in) * 100.0, 3) if mean_in > 0 else 0.0

                if calc_mode == "Auto (SD/Mean)":
                    cv_in = r2_c4.number_input(
                        "CV % (Auto)",
                        value=float(auto_cv),
                        format="%.3f",
                        disabled=True,
                        key=f"cv_in_cv_auto_{auto_cv}",
                    )
                else:
                    cv_in = r2_c4.number_input(
                        "CV % (Manual)",
                        min_value=0.001,
                        max_value=200.0,
                        step=0.05,
                        format="%.3f",
                        key="cv_in_cv_man",
                    )

                n_points_in = r2_c5.number_input(
                    "Total QC Points (n)",
                    min_value=1,
                    max_value=10000,
                    step=1,
                    key="cv_in_n",
                )
                mean_to_save = float(mean_in)
                sd_to_save = float(sd_in)
                n_to_save = int(n_points_in)

            if r2_c6.button(":material/save: Save Lot Data", type="primary", use_container_width=True):
                if not str(lot_no_in).strip():
                    queue_popup("Missing Lot No", "Please enter a Lot Number before saving.", "warning")
                    st.session_state["cv_persisted_test_by_inst"][sel_inst] = sel_test
                    st.session_state.pop(test_widget_key, None)
                    st.rerun()
                elif float(cv_in) <= 0:
                    queue_popup("Invalid CV%", "CV% must be greater than 0.", "warning")
                    st.session_state["cv_persisted_test_by_inst"][sel_inst] = sel_test
                    st.session_state.pop(test_widget_key, None)
                    st.rerun()
                else:
                    from_date_str = from_date_in.strftime("%d/%m/%Y") if isinstance(from_date_in, date) else ""
                    to_date_str = to_date_in.strftime("%d/%m/%Y") if isinstance(to_date_in, date) else ""

                    save_iqc_lot(
                        instrument_name=sel_inst,
                        test_code=sel_test,
                        test_full_name=full_name_str,
                        unit=unit_str,
                        level_no=int(sel_lv_no),
                        level_name=level_names[int(sel_lv_no) - 1],
                        lot_no=str(lot_no_in).strip(),
                        start_date=from_date_str,
                        cutoff_date=to_date_str,
                        lot_status=status_in,
                        mean_val=mean_to_save,
                        sd_val=sd_to_save,
                        cv_pct=float(cv_in),
                        n_points=n_to_save,
                        notes="Null Mean/SD/n" if is_null_mode else "",
                    )
                    period_saved = _format_lot_period(from_date_str, to_date_str)
                    n_msg = "n=Null" if n_to_save is None else f"n={n_to_save}"
                    queue_popup(
                        "Saved Lot Successfully",
                        f"Saved Lot {lot_no_in} ({period_saved} | {level_names[int(sel_lv_no) - 1]}: CV = {float(cv_in):.3f}%, {n_msg}).",
                        "success",
                    )
                    st.session_state["cv_persisted_test_by_inst"][sel_inst] = sel_test
                    st.session_state.pop(test_widget_key, None)
                    st.rerun()

        # ======================================================================
        # STEP 3: SELECT LOTS BY LEVEL & CALCULATE CUMULATIVE CV%
        # ======================================================================
        saved_lots_by_lv: Dict[int, set] = {}
        if not df_saved_all.empty:
            sub_s = df_saved_all[
                (df_saved_all["instrument_name"].astype(str).str.strip().str.lower() == sel_inst.strip().lower())
                & (df_saved_all["test_code"].astype(str).str.strip().str.upper() == sel_test.strip().upper())
                & (df_saved_all["quarter_period"].astype(str).str.strip().str.lower() == active_quarter_period.lower())
            ]
            for _, s_row in sub_s.iterrows():
                lv_no = int(s_row.get("level_no", 1) or 1)
                l_raw = str(s_row.get("selected_lots", ""))
                l_items = {
                    x.split("(")[0].strip()
                    for x in l_raw.split(",")
                    if x.strip() and x.strip() != "-"
                }
                if l_items:
                    saved_lots_by_lv[lv_no] = l_items

        with st.container(border=True):
            st.markdown(f"#### :material/calculate: 3. Select Lots & Cumulative CV% — **{active_quarter_period}**")

            if df_test_lots.empty:
                render_html(f'<div class="search-result-pill">No IQC Lots recorded for <b>{sel_test}</b> ({sel_inst}). Please add a lot in Step 2 above.</div>')
            else:
                lv_cols = st.columns(num_levels)
                records_to_save = []

                for idx in range(num_levels):
                    lv_no = idx + 1
                    lv_title = level_names[idx]
                    df_lv_lots = df_test_lots[df_test_lots["level_no"] == lv_no].copy().reset_index(drop=True)

                    with lv_cols[idx]:
                        st.markdown(f"##### 📌 {lv_title}")
                        if df_lv_lots.empty:
                            render_html(f'<div class="search-result-pill">No lots for {lv_title}.</div>')
                            records_to_save.append({
                                "instrument_name": sel_inst,
                                "test_code": sel_test,
                                "unit": unit_str,
                                "level_no": lv_no,
                                "level_name": lv_title,
                                "n_lots": 0,
                                "selected_lots": "-",
                                "total_points": None,
                                "pooled_mean": None,
                                "chosen_cv_pct": 0.0,
                            })
                        else:
                            df_lv_lots["usage_period"] = [
                                _format_lot_period(r.get("start_date", ""), r.get("cutoff_date", ""))
                                for _, r in df_lv_lots.iterrows()
                            ]
                            saved_set = saved_lots_by_lv.get(lv_no, set())
                            if saved_set:
                                df_lv_lots["use_lot"] = [
                                    str(l_no).strip() in saved_set for l_no in df_lv_lots["lot_no"].tolist()
                                ]
                            else:
                                df_lv_lots["use_lot"] = [i == 0 for i in range(len(df_lv_lots))]

                            editor_cols = [
                                "use_lot", "lot_no", "usage_period", "lot_status",
                                "mean_val", "sd_val", "cv_pct", "n_points"
                            ]
                            edited_lv_df = st.data_editor(
                                df_lv_lots[editor_cols],
                                column_config={
                                    "use_lot": st.column_config.CheckboxColumn("☑️ Use", width="small", default=False),
                                    "lot_no": st.column_config.TextColumn("Lot No", width="small", disabled=True),
                                    "usage_period": st.column_config.TextColumn("Period (From – To)", width="medium", disabled=True),
                                    "lot_status": st.column_config.TextColumn("Status", width="small", disabled=True),
                                    "mean_val": st.column_config.NumberColumn("Mean", format="%.2f", width="small", disabled=True),
                                    "sd_val": st.column_config.NumberColumn("SD", format="%.3f", width="small", disabled=True),
                                    "cv_pct": st.column_config.NumberColumn("CV %", format="%.3f%%", width="small", disabled=True),
                                    "n_points": st.column_config.NumberColumn("n", format="%d", width="small", disabled=True),
                                },
                                use_container_width=True,
                                hide_index=True,
                                key=f"cv_lot_editor_{active_quarter_period}_{sel_inst}_{sel_test}_lv{lv_no}",
                            )

                            sel_mask = edited_lv_df["use_lot"] == True
                            sub_selected = df_lv_lots.loc[sel_mask.index[sel_mask]]
                            metrics = _calc_pooled_cv(sub_selected)

                            tot_n = metrics["total_points"]
                            p_mean = metrics["pooled_mean_3dec"]
                            mean_disp = f"{p_mean:.3f} {unit_str}" if p_mean is not None else "Null"

                            if metrics["n_lots"] == 0:
                                badge_html = format_status_badge_html("EMPTY")
                                box_cls = "eval-result-fail"
                            elif tot_n is None or tot_n >= 20:
                                badge_html = format_status_badge_html("PASS")
                                box_cls = "eval-result-pass"
                            else:
                                badge_html = format_status_badge_html(f"WARN (N={tot_n}<20)")
                                box_cls = "eval-result-fail"

                            render_html(f"""
                            <div class="eval-result-box {box_cls}" style="margin-bottom:8px;">
                                <span><b>{lv_title}</b> (Mean: <code>{mean_disp}</code> | Lots: <code>{metrics['n_lots']}</code>)</span>
                                {badge_html}
                            </div>
                            """)

                            m_a, m_b = st.columns(2)
                            m_a.metric("Cumulative CV %", f"{metrics['pooled_cv_3dec']:.3f}%")
                            m_b.metric("Total Points (N)", "Null" if tot_n is None else f"{tot_n} pts")

                            render_html(f"""
                            <div class="history-meta-bar">
                                <span><b>Lots (From – To):</b> <code>{metrics['lots_str']}</code></span>
                                <span><b>Formula:</b> <code>{metrics['formula_detail']}</code></span>
                            </div>
                            """)

                            records_to_save.append({
                                "instrument_name": sel_inst,
                                "test_code": sel_test,
                                "unit": unit_str,
                                "level_no": lv_no,
                                "level_name": lv_title,
                                "n_lots": metrics["n_lots"],
                                "selected_lots": metrics["lots_str"],
                                "total_points": tot_n,
                                "pooled_mean": p_mean,
                                "chosen_cv_pct": metrics["pooled_cv_3dec"],
                            })

                act_b1, act_b2, act_b3 = st.columns([1.5, 2.3, 1.2], vertical_alignment="bottom")
                if act_b1.button(
                    f":material/save: Save CV% to {active_quarter_period}",
                    type="primary",
                    use_container_width=True,
                ):
                    valid_records = [r for r in records_to_save if r["n_lots"] > 0]
                    if not valid_records:
                        queue_popup(
                            "Incomplete Lot Selection",
                            "Please select at least 1 lot before saving.",
                            "warning",
                        )
                    else:
                        save_cv_summary_records(
                            instrument_name=sel_inst,
                            test_code=sel_test,
                            level_records=valid_records,
                            quarter_period=active_quarter_period,
                        )
                        queue_popup(
                            "Saved Successfully",
                            f"Saved Cumulative CV% for {sel_test} ({sel_inst}) to {active_quarter_period}.",
                            "success",
                        )
                    st.session_state["cv_persisted_test_by_inst"][sel_inst] = sel_test
                    st.session_state.pop(test_widget_key, None)
                    st.rerun()

                del_lot_map = {
                    f"[#{int(r['id'])}] {r['level_name']} — Lot {r['lot_no']} ({_format_lot_period(r.get('start_date', ''), r.get('cutoff_date', ''))} | CV={r['cv_pct']:.3f}%)": int(r["id"])
                    for _, r in df_test_lots.iterrows()
                }
                sel_del_lot = act_b2.selectbox(
                    "Select Lot to delete",
                    options=list(del_lot_map.keys()),
                    label_visibility="collapsed",
                    key=f"del_lot_sel_{sel_inst}_{sel_test}",
                )
                if act_b3.button(":material/delete: Delete Lot", type="secondary", use_container_width=True):
                    delete_iqc_lot(del_lot_map[sel_del_lot])
                    queue_popup("Deleted Lot", f"Removed {sel_del_lot}.", "error")
                    st.session_state["cv_persisted_test_by_inst"][sel_inst] = sel_test
                    st.session_state.pop(test_widget_key, None)
                    st.rerun()

    # ==========================================================================
    # TAB 2: QUARTERLY CUMULATIVE CV SUMMARY TABLE (Q1, Q2, Q3, Q4)
    # ==========================================================================
    with tab_saved:
        df_saved = get_all_cv_summaries()
        with st.container(border=True):
            st.markdown("#### :material/table_chart: Quarterly Cumulative CV% Summary")

            if df_saved.empty:
                st.write("No saved Cumulative CV% records yet.")
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
                    key="cv_saved_view_year_sel",
                )

                saved_inst_opts = ["All Instruments"] + sorted(df_saved["instrument_name"].dropna().unique().tolist())
                sel_view_inst = f_col2.selectbox(
                    "Instrument",
                    options=saved_inst_opts,
                    key="cv_saved_view_inst_sel",
                )

                df_filtered_saved = df_saved.copy()
                if sel_view_inst != "All Instruments":
                    df_filtered_saved = df_filtered_saved[df_filtered_saved["instrument_name"] == sel_view_inst]

                full_year_buf = io.BytesIO()
                with pd.ExcelWriter(full_year_buf, engine="openpyxl") as writer:
                    for q_i in [1, 2, 3, 4]:
                        q_code_i = f"Q{q_i}/{sel_view_year}"
                        sub_q_i = df_filtered_saved[
                            df_filtered_saved["quarter_period"].astype(str).str.lower() == q_code_i.lower()
                        ]
                        sheet_df = sub_q_i[[
                            "quarter_period", "instrument_name", "test_code", "unit", "level_name",
                            "pooled_mean", "n_lots", "selected_lots", "total_points", "chosen_cv_pct", "updated_at"
                        ]].copy()
                        sheet_df["pooled_mean"] = pd.to_numeric(sheet_df["pooled_mean"], errors="coerce").round(3)
                        sheet_df["chosen_cv_pct"] = pd.to_numeric(sheet_df["chosen_cv_pct"], errors="coerce").round(3)
                        sheet_df = sheet_df.rename(columns={
                            "quarter_period": "Quarter",
                            "instrument_name": "Instrument",
                            "test_code": "Analyte",
                            "unit": "Unit",
                            "level_name": "Level",
                            "pooled_mean": "Pooled Mean",
                            "n_lots": "Lots",
                            "selected_lots": "Selected Lots (From – To)",
                            "total_points": "Total Points (N)",
                            "chosen_cv_pct": "Cumulative CV %",
                            "updated_at": "Updated",
                        })
                        sheet_name = f"Q{q_i}_{sel_view_year}"
                        sheet_df.to_excel(writer, index=False, sheet_name=sheet_name)
                        _style_cv_worksheet(writer.sheets[sheet_name], sheet_df)

                f_col3.download_button(
                    f":material/download: Export Excel All (Q1–Q4 {sel_view_year})",
                    data=full_year_buf.getvalue(),
                    file_name=f"IQC_CV_All_Quarters_{sel_view_year}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    key="dl_cv_full_year_quarters_btn",
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
                        _render_cv_quarter_summary_table(
                            df_q=sub_df,
                            quarter_code=q_code,
                            key_suffix=f"cv_q{q_no}_{sel_view_year}",
                        )

                with q_tabs[4]:
                    _render_cv_quarter_summary_table(
                        df_q=df_filtered_saved,
                        quarter_code=f"All_{sel_view_year}",
                        key_suffix=f"cv_all_q_{sel_view_year}",
                    )
