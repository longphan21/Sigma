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
    (1, "Quý 1 (Tháng 3)", 3),
    (2, "Quý 2 (Tháng 6)", 6),
    (3, "Quý 3 (Tháng 9)", 9),
    (4, "Quý 4 (Tháng 12)", 12),
]


def _compute_exact_monthly_bias(df_test: pd.DataFrame) -> pd.DataFrame:
    """
    Tính chính xác BIAS % của từng tháng theo công thức cố định của Lab:
    BIAS % = (|Kết quả đơn vị - Giá trị ấn định| * 100) / Giá trị ấn định
    tương đương công thức Excel: =(ABS(D - E) * 100 / E)
    """
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
    """
    Tính trung bình cộng BIAS % (=AVERAGE) của các tháng được chọn, làm tròn tới chữ số thập phân thứ 3.
    """
    valid = df_sub.dropna(subset=["exact_bias_pct"])
    n = len(valid)
    if n == 0:
        return {
            "n": 0,
            "avg_bias_3dec": 0.0,
            "mean_assigned": 0.0,
            "mean_lab": 0.0,
            "months_str": "-",
            "formula_detail": "Chưa chọn tháng nào",
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
    quarter_title: str,
    quarter_code: str,
    key_suffix: str,
):
    """Hiển thị bảng tổng hợp các xét nghiệm đã chốt BIAS % trong 1 Quý kèm nút xuất Excel và xóa."""
    if df_q.empty:
        render_html(f"""
        <div class="search-result-pill" style="margin-top:4px;">
            Chưa có xét nghiệm nào được chốt BIAS % trong <b>{quarter_title}</b>.
        </div>
        """)
        return

    df_show = df_q[[
        "quarter_period", "instrument_name", "test_code", "unit", "level_name",
        "mean_conc", "n_batches", "selected_batches", "chosen_bias_pct", "updated_at"
    ]].copy()
    df_show["mean_conc"] = df_show["mean_conc"].round(3)
    df_show["chosen_bias_pct"] = df_show["chosen_bias_pct"].round(3)

    df_display = df_show.rename(columns={
        "quarter_period": "Kỳ Quý",
        "instrument_name": "Thiết bị / Máy",
        "test_code": "Mã XN",
        "unit": "Đơn vị",
        "level_name": "Mức nồng độ",
        "mean_conc": "GT Ấn định TB",
        "n_batches": "Số tháng chọn",
        "selected_batches": "Các tháng EQA đã chọn",
        "chosen_bias_pct": "BIAS % trung bình",
        "updated_at": "Cập nhật lúc",
    })

    st.dataframe(
        df_display,
        column_config={
            "GT Ấn định TB": st.column_config.NumberColumn("GT Ấn định TB", format="%.3f"),
            "BIAS % trung bình": st.column_config.NumberColumn("BIAS % trung bình", format="%.3f%%"),
        },
        use_container_width=True,
        hide_index=True,
        key=f"df_saved_table_{key_suffix}",
    )

    act_c1, act_c2, act_c3 = st.columns([1.4, 2.0, 1.6])
    excel_buf = io.BytesIO()
    with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
        df_display.to_excel(writer, index=False, sheet_name="Bias_Summary")
    safe_q_fname = quarter_code.replace("/", "_").replace(" ", "_")
    act_c1.download_button(
        f":material/table_view: Xuất Excel ({quarter_code})",
        data=excel_buf.getvalue(),
        file_name=f"Bang_Bias_EQA_{safe_q_fname}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        key=f"dl_btn_{key_suffix}",
    )

    saved_items = [
        f"{r['quarter_period']} | {r['instrument_name']} | {r['test_code']}"
        for _, r in df_q[["quarter_period", "instrument_name", "test_code"]].drop_duplicates().iterrows()
    ]
    del_item = act_c2.selectbox(
        "Chọn xét nghiệm cần xóa khỏi Quý này",
        saved_items,
        key=f"del_sel_{key_suffix}",
    )
    if act_c3.button(
        ":material/delete: Xóa bản ghi BIAS % này",
        type="secondary",
        use_container_width=True,
        key=f"del_btn_{key_suffix}",
    ):
        p_q, p_inst, p_test = [x.strip() for x in del_item.split("|", 2)]
        delete_bias_summary_by_test(p_test, instrument_name=p_inst, quarter_period=p_q)
        queue_popup("Đã xóa!", f"Đã xóa kết quả BIAS % của {p_test} ({p_inst}) trong {p_q}.", "error")
        st.rerun()


def render_bias_calculator_page():
    """Giao diện chọn Quý, chọn Xét nghiệm, tự chọn tháng EQA và tổng hợp BIAS % theo từng Quý."""
    render_page_banner(
        "Tính BIAS % Trung Bình theo Quý & Mức Nồng Độ (Tự chọn tháng EQA)",
        "Chốt BIAS % định kỳ theo Quý 1 (T3), Quý 2 (T6), Quý 3 (T9), Quý 4 (T12) — làm tròn tới chữ số thập phân thứ 3.",
    )

    df_all = get_all_results_joined()
    if df_all.empty:
        with st.container(border=True):
            st.markdown("#### :material/info: Chưa có dữ liệu Ngoại kiểm trong Database")
            st.write("Vui lòng tải file PDF kết quả ngoại kiểm tại mục **2. Import EQA PDF** trước khi tính %Bias.")
        return

    df_saved_all = get_all_bias_summaries()

    # Tự động lấy danh sách các năm có trong dữ liệu EQA (và năm hiện tại)
    ym_parsed = [parse_ym_tuple(m) for m in df_all["month_year"].dropna().unique().tolist()]
    years_in_db = sorted(list({yr for yr, _ in ym_parsed if yr > 2000} | {datetime.now().year, 2026}), reverse=True)

    tab_calc, tab_saved = st.tabs([
        "🧮 1. Chọn Quý, Xét nghiệm & Tự chọn tháng tính BIAS %",
        "📋 2. Bảng tổng hợp BIAS % đã lưu theo từng Quý",
    ])

    with tab_calc:
        # ======================================================================
        # BƯỚC 1: CHỌN KỲ QUÝ CHỐT BIAS, DÒNG MÁY & XÉT NGHIỆM
        # ======================================================================
        with st.container(border=True):
            st.markdown("#### :material/science: Bước 1: Chọn Kỳ Quý chốt BIAS %, Dòng máy & Xét nghiệm")
            c_q, c_yr, c_inst, c_test, c_lv = st.columns([1.15, 0.75, 1.25, 1.75, 0.95])

            q_idx_map = {q_no: f"Quý {q_no} (Tháng {q_mo})" for q_no, _, q_mo in QUARTER_OPTIONS}
            sel_q_no = c_q.selectbox(
                "1. Chọn Quý chốt Bias",
                options=[1, 2, 3, 4],
                format_func=lambda x: q_idx_map[x],
                index=2,  # Mặc định Quý 3 (Tháng 9) hoặc người dùng đổi sang Quý 1, 2, 4
                key="bias_quarter_no_sel",
            )
            sel_year = c_yr.selectbox(
                "Năm chốt",
                options=years_in_db,
                index=0,
                key="bias_year_sel",
            )

            cutoff_month = sel_q_no * 3
            active_quarter_period = f"Quý {sel_q_no}/{sel_year}"

            inst_list = sorted(df_all["instrument_name"].dropna().unique().tolist())
            sel_inst = c_inst.selectbox("2. Dòng máy / Thiết bị", inst_list, key="bias_inst_sel")

            df_inst_all = df_all[df_all["instrument_name"] == sel_inst].copy()

            filter_by_quarter_cutoff = st.checkbox(
                f"📅 Chỉ liệt kê dữ liệu tính đến hết {active_quarter_period} (Từ năm {sel_year - 1} trở về trước + các tháng đến hết Tháng {cutoff_month:02d}/{sel_year})",
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

            # Sắp xếp các tháng từ cũ đến mới theo đúng trình tự thời gian (năm 2025 -> tháng 1, 2, 3 năm 2026)
            all_months_inst = sorted(
                df_inst["month_year"].dropna().unique().tolist(),
                key=parse_ym_tuple,
            )

            # Thống kê danh sách xét nghiệm trên dòng máy (AST/ALT đã được đồng nhất tự động)
            test_stats = []
            for t_code, grp in df_inst.groupby("test_code"):
                t_full = str(grp["test_full_name"].iloc[0]) if not grp.empty else str(t_code)
                n_months = grp["month_year"].nunique()
                test_stats.append((str(t_code), t_full, n_months))
            test_stats.sort(key=lambda x: x[0].upper())

            test_codes_list = [x[0] for x in test_stats]
            test_label_map = {
                x[0]: f"{x[0]} — {x[1]} ({x[2]} tháng)"
                for x in test_stats
            }

            # Kiểm tra những xét nghiệm nào đã chốt BIAS % trong đúng Quý đang chọn
            saved_tests_in_quarter = set()
            if not df_saved_all.empty:
                sub_q_saved = df_saved_all[
                    (df_saved_all["instrument_name"].astype(str).str.strip().str.lower() == sel_inst.strip().lower())
                    & (df_saved_all["quarter_period"].astype(str).str.strip().str.lower() == active_quarter_period.lower())
                ]
                saved_tests_in_quarter = set(sub_q_saved["test_code"].astype(str).str.strip().str.upper().tolist())

            sel_test = c_test.selectbox(
                f"3. Chọn Xét nghiệm ({len(test_codes_list)} XN)",
                options=test_codes_list,
                format_func=lambda k: ("✅ " if k.strip().upper() in saved_tests_in_quarter else "") + test_label_map.get(k, k),
                key=f"bias_test_sel_{sel_inst}",
            )

            num_levels = c_lv.selectbox(
                "4. Số mức nồng độ",
                options=[2, 3, 1],
                format_func=lambda x: "2 mức (LOW / HIGH)" if x == 2 else f"{x} mức nồng độ",
                key="bias_num_levels",
            )

            months_preview = ", ".join(all_months_inst) if all_months_inst else "-"
            render_html(f"""
            <div class="history-meta-bar" style="margin-top:4px; margin-bottom:2px;">
                <span>📌 <b>Đang chốt cho kỳ:</b> <span class="date-pill">{active_quarter_period} (Đợt Tháng {cutoff_month:02d}/{sel_year})</span></span>
                <span>🔬 <b>Dòng máy:</b> <code>{sel_inst}</code></span>
                <span>📊 <b>Số XN trên máy:</b> <span class="lot-pill">{len(test_codes_list)} xét nghiệm</span></span>
                <span>📅 <b>Dữ liệu tháng EQA ({len(all_months_inst)} tháng):</b> <code>{months_preview}</code></span>
                <span>✅ <b>Đã chốt trong {active_quarter_period}:</b> <b>{len(saved_tests_in_quarter)}/{len(test_codes_list)} XN</b></span>
            </div>
            """)

        # ======================================================================
        # BƯỚC 2: BẢNG CHỌN THÁNG (CỘT KQ ĐƠN VỊ, ẤN ĐỊNH & BIAS SÁT CỘT TICK CHỌN)
        # ======================================================================
        df_test = df_inst[df_inst["test_code"] == sel_test].copy()
        df_test["_ym_sort"] = df_test["month_year"].apply(parse_ym_tuple)
        df_test = df_test.sort_values(by=["_ym_sort", "batch_no"], ascending=[True, True]).drop(columns=["_ym_sort"]).reset_index(drop=True)
        df_test = _compute_exact_monthly_bias(df_test)

        unit_str = str(df_test["unit"].iloc[0]) if not df_test.empty else ""
        full_name_str = str(df_test["test_full_name"].iloc[0]) if not df_test.empty else sel_test

        level_names = (
            ["Mức 1 (LOW)", "Mức 2 (HIGH)"]
            if num_levels == 2
            else (["Mức 1 (LOW)", "Mức 2 (MID)", "Mức 3 (HIGH)"] if num_levels == 3 else ["Mức 1 (Chung)"])
        )
        short_check_labels = (
            ["☑️ Mức 1 (LOW)", "☑️ Mức 2 (HIGH)"]
            if num_levels == 2
            else (["☑️ Mức 1 (LOW)", "☑️ Mức 2 (MID)", "☑️ Mức 3 (HIGH)"] if num_levels == 3 else ["☑️ Chọn tháng"])
        )

        # Khôi phục các tháng đã lưu của xét nghiệm này trong đúng Quý đang chọn (nếu có)
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
            hdr_c1, hdr_c2 = st.columns([3.6, 1.4])
            with hdr_c1:
                st.markdown(
                    f"#### :material/check_box: Bước 2: Chọn tháng tính BIAS % cho **{sel_test} ({full_name_str})** — Kỳ **{active_quarter_period}**"
                )
            with hdr_c2:
                if st.button(":material/restart_alt: Bỏ chọn tất cả các tháng", type="secondary", use_container_width=True):
                    st.session_state[f"force_empty_{state_sig}"] = True
                    st.session_state[reset_counter_key] += 1
                    st.rerun()

            # Sắp xếp cột hợp lý: Tháng/Năm -> Checkbox chọn mức -> KQ Đơn vị -> GT Ấn định -> BIAS % nằm sát nhau
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
                "month_year": st.column_config.TextColumn("Tháng/Năm", width="small", disabled=True),
                "lab_result": st.column_config.NumberColumn(f"KQ Đơn vị ({unit_str})", format="%.3f", width="small", disabled=True),
                "assigned_value": st.column_config.NumberColumn(f"GT Ấn định ({unit_str})", format="%.3f", width="small", disabled=True),
                "bias_3dec_display": st.column_config.NumberColumn("BIAS %", format="%.3f%%", width="small", disabled=True),
                "unit": st.column_config.TextColumn("Đơn vị", width="small", disabled=True),
                "z_score": st.column_config.NumberColumn("z-score", format="%+.2f", width="small", disabled=True),
                "batch_label": st.column_config.TextColumn("Đợt EQA", width="medium", disabled=True),
            }
            for idx in range(num_levels):
                col_cfg[f"use_lv{idx + 1}"] = st.column_config.CheckboxColumn(
                    short_check_labels[idx],
                    help=f"Tick chọn tháng này cho {level_names[idx]}",
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
        # BƯỚC 3: KẾT QUẢ BIAS % TRUNG BÌNH (LÀM TRÒN 3 SỐ THẬP PHÂN) & LƯU THEO QUÝ
        # ======================================================================
        with st.container(border=True):
            st.markdown(f"#### :material/calculate: Bước 3: Kết quả BIAS % Trung bình & Chốt lưu vào **{active_quarter_period}**")

            copy_lv1_to_lv2 = False
            if num_levels == 2:
                copy_lv1_to_lv2 = st.checkbox(
                    "🔗 Cho Mức 2 (HIGH) lấy bằng kết quả của Mức 1 (LOW) (Dùng khi cả 2 mức nồng độ lấy chung 1 giá trị BIAS %)",
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
                    badge_state = f"ĐÃ CHỌN {metrics['n']} THÁNG" if metrics["n"] > 0 else "CHƯA CHỌN THÁNG"
                    render_html(f"""
                    <div class="eval-result-box {'eval-result-pass' if metrics['n'] > 0 else 'eval-result-fail'}" style="margin-bottom:8px;">
                        <span><b>{lv_title}</b> (KQ TB: <code>{metrics['mean_lab']:.3f}</code> | Ấn định TB: <code>{metrics['mean_assigned']:.3f} {unit_str}</code>)</span>
                        {format_status_badge_html('ĐẠT' if metrics['n'] >= 3 else badge_state)}
                    </div>
                    """)
                    m_a, m_b = st.columns(2)
                    m_a.metric("BIAS % trung bình", f"{metrics['avg_bias_3dec']:.3f}%")
                    m_b.metric("Số tháng đã chọn", f"{metrics['n']} tháng")

                    render_html(f"""
                    <div class="history-meta-bar">
                        <span><b>Tháng đã chọn:</b> <code>{metrics['months_str']}</code></span>
                        <span><b>Trung bình cộng:</b> <code>{metrics['formula_detail']}</code></span>
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

            if st.button(
                f":material/save: Lưu kết quả BIAS % của {sel_test} vào {active_quarter_period}",
                type="primary",
            ):
                if any(r["n_batches"] == 0 for r in records_to_save):
                    queue_popup(
                        "Chưa chọn đủ tháng!",
                        "Vui lòng tick chọn ít nhất 1 tháng cho mỗi mức nồng độ (hoặc tích chọn 'Cho Mức 2 lấy bằng Mức 1') trước khi lưu.",
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
                        f"Đã chốt BIAS % cho {active_quarter_period}!",
                        f"Đã lưu BIAS % trung bình của {sel_test} ({sel_inst}) vào bảng tổng hợp {active_quarter_period}.",
                        "success",
                    )
                    st.rerun()

    # ==========================================================================
    # TAB 2: BẢNG TỔNG HỢP BIAS % ĐÃ LƯU CHIA THEO TỪNG QUÝ (QUÝ 1, 2, 3, 4)
    # ==========================================================================
    with tab_saved:
        df_saved = get_all_bias_summaries()
        with st.container(border=True):
            st.markdown("#### :material/table_chart: Bảng tổng hợp BIAS % đã chốt chia theo từng Quý (Quý 1, Quý 2, Quý 3, Quý 4)")

            if df_saved.empty:
                st.write("Chưa có xét nghiệm nào được lưu kết quả BIAS %. Hãy chọn Quý và tick chọn tháng tại Tab 1 rồi bấm **Lưu kết quả**.")
            else:
                f_col1, f_col2, f_col3 = st.columns([1.1, 1.5, 1.8])

                # Lấy danh sách năm từ các bản ghi đã lưu
                saved_years = sorted(
                    list({
                        int(q.split("/")[-1])
                        for q in df_saved["quarter_period"].dropna().unique().tolist()
                        if "/" in str(q) and str(q).split("/")[-1].isdigit()
                    } | {int(sel_year)}),
                    reverse=True,
                )
                sel_view_year = f_col1.selectbox(
                    "Năm tổng hợp",
                    options=saved_years,
                    index=0,
                    key="saved_view_year_sel",
                )

                saved_inst_opts = ["Tất cả dòng máy"] + sorted(df_saved["instrument_name"].dropna().unique().tolist())
                sel_view_inst = f_col2.selectbox(
                    "Lọc theo Dòng máy",
                    options=saved_inst_opts,
                    key="saved_view_inst_sel",
                )

                df_filtered_saved = df_saved.copy()
                if sel_view_inst != "Tất cả dòng máy":
                    df_filtered_saved = df_filtered_saved[df_filtered_saved["instrument_name"] == sel_view_inst]

                # Nút xuất 1 file Excel gồm 4 Sheet riêng biệt cho Quý 1, Quý 2, Quý 3, Quý 4 của năm đang chọn
                full_year_buf = io.BytesIO()
                with pd.ExcelWriter(full_year_buf, engine="openpyxl") as writer:
                    wrote_any = False
                    for q_i in [1, 2, 3, 4]:
                        q_code_i = f"Quý {q_i}/{sel_view_year}"
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
                            "quarter_period": "Kỳ Quý",
                            "instrument_name": "Thiết bị / Máy",
                            "test_code": "Mã XN",
                            "unit": "Đơn vị",
                            "level_name": "Mức nồng độ",
                            "mean_conc": "GT Ấn định TB",
                            "n_batches": "Số tháng chọn",
                            "selected_batches": "Các tháng EQA đã chọn",
                            "chosen_bias_pct": "BIAS % trung bình",
                            "updated_at": "Cập nhật lúc",
                        })
                        sheet_df.to_excel(writer, index=False, sheet_name=f"Quy_{q_i}_{sel_view_year}")
                        wrote_any = True
                    if not wrote_any:
                        pd.DataFrame().to_excel(writer, index=False, sheet_name="Empty")

                with f_col3:
                    st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
                    st.download_button(
                        f":material/download: Xuất Excel Cả Năm {sel_view_year} (4 Sheet Quý 1-4)",
                        data=full_year_buf.getvalue(),
                        file_name=f"Tong_Hop_Bias_EQA_Nam_{sel_view_year}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                        key="dl_full_year_quarters_btn",
                    )

                # Đếm số xét nghiệm đã chốt ở từng Quý để hiển thị ngay trên tiêu đề Sub-tab
                q_counts = {}
                for q_i in [1, 2, 3, 4]:
                    q_code_i = f"Quý {q_i}/{sel_view_year}"
                    sub_i = df_filtered_saved[
                        df_filtered_saved["quarter_period"].astype(str).str.lower() == q_code_i.lower()
                    ]
                    q_counts[q_i] = sub_i["test_code"].nunique()

                q_tabs = st.tabs([
                    f"📅 Quý 1 - Tháng 3 ({q_counts[1]} XN)",
                    f"📅 Quý 2 - Tháng 6 ({q_counts[2]} XN)",
                    f"📅 Quý 3 - Tháng 9 ({q_counts[3]} XN)",
                    f"📅 Quý 4 - Tháng 12 ({q_counts[4]} XN)",
                    f"📑 Tất cả các Quý ({len(df_filtered_saved)} dòng)",
                ])

                for idx_q, q_no in enumerate([1, 2, 3, 4]):
                    q_code = f"Quý {q_no}/{sel_view_year}"
                    q_title = f"Quý {q_no}/{sel_view_year} (Đợt chốt Tháng {q_no * 3:02d}/{sel_view_year})"
                    sub_df = df_filtered_saved[
                        df_filtered_saved["quarter_period"].astype(str).str.lower() == q_code.lower()
                    ]
                    with q_tabs[idx_q]:
                        _render_quarter_summary_table(
                            df_q=sub_df,
                            quarter_title=q_title,
                            quarter_code=q_code,
                            key_suffix=f"q{q_no}_{sel_view_year}",
                        )

                with q_tabs[4]:
                    _render_quarter_summary_table(
                        df_q=df_filtered_saved,
                        quarter_title="Tất cả các Quý",
                        quarter_code=f"Tat_Ca_Cac_Quy_{sel_view_year}",
                        key_suffix=f"all_q_{sel_view_year}",
                    )
