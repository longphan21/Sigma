import io
from typing import List, Dict, Any
import pandas as pd
import streamlit as st

from ui_theme import render_page_banner, render_html, queue_popup, format_status_badge_html
from database import (
    get_all_results_joined,
    save_bias_summary_records,
    get_all_bias_summaries,
    delete_bias_summary_by_test,
)


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
    Tính trung bình cộng BIAS % (=AVERAGE) của các tháng được người dùng tick chọn.
    """
    valid = df_sub.dropna(subset=["exact_bias_pct"])
    n = len(valid)
    if n == 0:
        return {
            "n": 0,
            "avg_bias_exact": 0.0,
            "avg_bias_round": 0.0,
            "mean_assigned": 0.0,
            "mean_lab": 0.0,
            "months_str": "-",
            "formula_detail": "Chưa chọn tháng nào",
        }

    bias_vals = valid["exact_bias_pct"].astype(float)
    asg_vals = valid["assigned_value"].dropna().astype(float)
    lab_vals = valid["lab_result"].dropna().astype(float)

    avg_exact = float(bias_vals.mean())
    mean_asg = float(asg_vals.mean()) if not asg_vals.empty else 0.0
    mean_lab = float(lab_vals.mean()) if not lab_vals.empty else 0.0

    months_list = valid["month_year"].astype(str).tolist()
    terms_str = " + ".join([f"{v:.4f}%" for v in bias_vals.tolist()])

    return {
        "n": n,
        "avg_bias_exact": round(avg_exact, 4),
        "avg_bias_round": round(avg_exact, 2),
        "mean_assigned": round(mean_asg, 3),
        "mean_lab": round(mean_lab, 3),
        "months_str": ", ".join(months_list),
        "formula_detail": f"({terms_str}) / {n} = {avg_exact:.4f}%",
    }


def render_bias_calculator_page():
    """Giao diện chọn xét nghiệm, liệt kê kết quả các tháng EQA và tự chọn tháng tính BIAS % trung bình."""
    render_page_banner(
        "Tính BIAS % Trung Bình theo Mức Nồng Độ (Tự chọn tháng EQA)",
        "Công thức cố định: BIAS % từng tháng = (|KQ đơn vị - GT ấn định| * 100) / GT ấn định  →  BIAS % mỗi mức = AVERAGE(các tháng đã chọn).",
    )

    df_all = get_all_results_joined()
    if df_all.empty:
        with st.container(border=True):
            st.markdown("#### :material/info: Chưa có dữ liệu Ngoại kiểm trong Database")
            st.write("Vui lòng tải file PDF kết quả ngoại kiểm tại mục **2. Import EQA PDF** trước khi tính %Bias.")
        return

    df_saved_all = get_all_bias_summaries()

    tab_calc, tab_saved = st.tabs([
        "🧮 1. Chọn Xét nghiệm & Tự chọn tháng tính BIAS %",
        "📋 2. Bảng tổng hợp BIAS % đã lưu",
    ])

    with tab_calc:
        # ======================================================================
        # BƯỚC 1: CHỌN DÒNG MÁY -> HIỂN THỊ SỐ XÉT NGHIỆM & SỐ THÁNG -> CHỌN TEST
        # ======================================================================
        with st.container(border=True):
            st.markdown("#### :material/science: Bước 1: Chọn Dòng máy & Xét nghiệm cần tính BIAS %")
            c1, c2, c3 = st.columns([1.3, 1.9, 1.0])

            inst_list = sorted(df_all["instrument_name"].dropna().unique().tolist())
            sel_inst = c1.selectbox("1. Chọn Dòng máy / Thiết bị", inst_list, key="bias_inst_sel")

            df_inst = df_all[df_all["instrument_name"] == sel_inst].copy()
            all_months_inst = sorted(df_inst["month_year"].dropna().unique().tolist())

            # Thống kê danh sách xét nghiệm và số tháng có kết quả trên dòng máy đang chọn
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

            # Kiểm tra số xét nghiệm đã lưu %Bias trên dòng máy này
            saved_tests_on_inst = set()
            if not df_saved_all.empty:
                sub_inst_saved = df_saved_all[
                    df_saved_all["instrument_name"].astype(str).str.strip().str.lower() == sel_inst.strip().lower()
                ]
                saved_tests_on_inst = set(sub_inst_saved["test_code"].astype(str).str.strip().str.upper().tolist())

            sel_test = c2.selectbox(
                f"2. Chọn Xét nghiệm trên máy ({len(test_codes_list)} xét nghiệm)",
                options=test_codes_list,
                format_func=lambda k: ("✅ " if k.strip().upper() in saved_tests_on_inst else "") + test_label_map.get(k, k),
                key=f"bias_test_sel_{sel_inst}",
            )

            num_levels = c3.selectbox(
                "3. Số mức nồng độ",
                options=[2, 3, 1],
                format_func=lambda x: "2 mức: Mức 1 (LOW) & Mức 2 (HIGH)" if x == 2 else f"{x} mức nồng độ",
                key="bias_num_levels",
            )

            # Thanh tóm tắt tổng quan dòng máy đang chọn
            months_preview = ", ".join(all_months_inst) if all_months_inst else "-"
            render_html(f"""
            <div class="history-meta-bar" style="margin-top:4px; margin-bottom:2px;">
                <span>🔬 <b>Dòng máy:</b> <code>{sel_inst}</code></span>
                <span>📊 <b>Tổng số xét nghiệm trên máy:</b> <span class="date-pill">{len(test_codes_list)} xét nghiệm</span></span>
                <span>📅 <b>Số đợt/tháng EQA đã import:</b> <span class="lot-pill">{len(all_months_inst)} tháng ({months_preview})</span></span>
                <span>💾 <b>Đã chốt BIAS %:</b> <code>{len(saved_tests_on_inst)}/{len(test_codes_list)} xét nghiệm</code></span>
            </div>
            """)

        # ======================================================================
        # BƯỚC 2: LIỆT KÊ KẾT QUẢ CÁC THÁNG CỦA XÉT NGHIỆM & TỰ TICK CHỌN
        # ======================================================================
        df_test = df_inst[df_inst["test_code"] == sel_test].copy()
        # Sắp xếp từ Tháng 1 -> Tháng 12 đúng theo thứ tự bảng Excel của Lab
        df_test = df_test.sort_values(by=["month_year", "batch_no"], ascending=[True, True]).reset_index(drop=True)
        df_test = _compute_exact_monthly_bias(df_test)

        unit_str = str(df_test["unit"].iloc[0]) if not df_test.empty else ""
        full_name_str = str(df_test["test_full_name"].iloc[0]) if not df_test.empty else sel_test

        level_names = (
            ["Mức 1 (LOW)", "Mức 2 (HIGH)"]
            if num_levels == 2
            else (["Mức 1 (LOW)", "Mức 2 (MID)", "Mức 3 (HIGH)"] if num_levels == 3 else ["Mức 1 (Chung)"])
        )

        # Kiểm tra nếu xét nghiệm này đã từng được lưu trước đó thì nạp lại các tháng đã chọn
        saved_months_by_lv: Dict[int, set] = {}
        if not df_saved_all.empty:
            sub_s = df_saved_all[
                (df_saved_all["instrument_name"].astype(str).str.strip().str.lower() == sel_inst.strip().lower())
                & (df_saved_all["test_code"].astype(str).str.strip().str.upper() == sel_test.strip().upper())
            ]
            for _, s_row in sub_s.iterrows():
                lv_no = int(s_row.get("level_no", 1) or 1)
                b_raw = str(s_row.get("selected_batches", ""))
                b_items = {x.strip() for x in b_raw.split(",") if x.strip() and x.strip() != "-"}
                if b_items:
                    saved_months_by_lv[lv_no] = b_items

        reset_counter_key = f"reset_cnt_{sel_inst}_{sel_test}"
        if reset_counter_key not in st.session_state:
            st.session_state[reset_counter_key] = 0

        for idx in range(num_levels):
            lv_no = idx + 1
            saved_set = saved_months_by_lv.get(lv_no, set())
            if st.session_state.get(f"force_empty_{sel_inst}_{sel_test}", False):
                df_test[f"use_lv{lv_no}"] = False
            else:
                df_test[f"use_lv{lv_no}"] = [
                    str(m).strip() in saved_set for m in df_test["month_year"].tolist()
                ]

        with st.container(border=True):
            hdr_c1, hdr_c2 = st.columns([3.6, 1.4])
            with hdr_c1:
                st.markdown(
                    f"#### :material/check_box: Bước 2: Kết quả {len(df_test)} tháng của **{sel_test} ({full_name_str})** — Tự chọn tháng tính BIAS %"
                )
            with hdr_c2:
                if st.button(":material/restart_alt: Bỏ chọn tất cả các tháng", type="secondary", use_container_width=True):
                    st.session_state[f"force_empty_{sel_inst}_{sel_test}"] = True
                    st.session_state[reset_counter_key] += 1
                    st.rerun()

            df_test["bias_exact_display"] = df_test["exact_bias_pct"].round(4)
            editor_cols = [f"use_lv{i + 1}" for i in range(num_levels)] + [
                "month_year",
                "batch_label",
                "unit",
                "lab_result",
                "assigned_value",
                "bias_exact_display",
                "z_score",
            ]
            df_editor_in = df_test[editor_cols].copy()

            col_cfg = {
                "month_year": st.column_config.TextColumn("Tháng/Năm", disabled=True),
                "batch_label": st.column_config.TextColumn("Đợt EQA", disabled=True),
                "unit": st.column_config.TextColumn("Đơn vị", disabled=True),
                "lab_result": st.column_config.NumberColumn(f"Kết quả đơn vị - D ({unit_str})", format="%.3f", disabled=True),
                "assigned_value": st.column_config.NumberColumn(f"Giá trị ấn định - E ({unit_str})", format="%.3f", disabled=True),
                "bias_exact_display": st.column_config.NumberColumn("BIAS % = |D-E|*100/E", format="%.4f%%", disabled=True),
                "z_score": st.column_config.NumberColumn("z-score", format="%+.2f", disabled=True),
            }
            for idx in range(num_levels):
                col_cfg[f"use_lv{idx + 1}"] = st.column_config.CheckboxColumn(
                    f"☑️ Chọn cho {level_names[idx]}",
                    help=f"Tick chọn các tháng bạn muốn đưa vào tính trung bình cộng BIAS % của {level_names[idx]}",
                    default=False,
                )

            edited_df = st.data_editor(
                df_editor_in,
                column_config=col_cfg,
                use_container_width=True,
                hide_index=True,
                key=f"editor_manual_bias_{sel_inst}_{sel_test}_{num_levels}_{st.session_state[reset_counter_key]}",
            )

        # ======================================================================
        # BƯỚC 3: KẾT QUẢ BIAS % TRUNG BÌNH (=AVERAGE) & LƯU DATABASE
        # ======================================================================
        with st.container(border=True):
            st.markdown("#### :material/calculate: Bước 3: Kết quả BIAS % Trung bình (=AVERAGE) & Lưu Database")

            copy_lv1_to_lv2 = False
            if num_levels == 2:
                copy_lv1_to_lv2 = st.checkbox(
                    "🔗 Cho Mức 2 (HIGH) lấy bằng kết quả của Mức 1 (LOW) (Dùng khi cả 2 mức nồng độ lấy chung 1 giá trị BIAS %)",
                    value=False,
                    key=f"chk_same_bias_{sel_inst}_{sel_test}",
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
                    m_a, m_b, m_c = st.columns(3)
                    m_a.metric("BIAS % trung bình (Excel)", f"{metrics['avg_bias_exact']:.4f}%")
                    m_b.metric("BIAS % (Làm tròn 2 số)", f"{metrics['avg_bias_round']:.2f}%")
                    m_c.metric("Số tháng đã chọn", f"{metrics['n']} tháng")

                    render_html(f"""
                    <div class="history-meta-bar">
                        <span><b>Tháng đã chọn:</b> <code>{metrics['months_str']}</code></span>
                        <span><b>Phép tính AVERAGE:</b> <code>{metrics['formula_detail']}</code></span>
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
                    "mean_abs_bias_pct": metrics["avg_bias_exact"],
                    "mean_signed_bias_pct": metrics["avg_bias_exact"],
                    "rms_bias_pct": metrics["avg_bias_exact"],
                    "chosen_bias_pct": metrics["avg_bias_exact"],
                    "formula_type": "AVERAGE(|D-E|*100/E)",
                })

            if st.button(":material/save: Lưu kết quả BIAS % của xét nghiệm này vào Database", type="primary"):
                if any(r["n_batches"] == 0 for r in records_to_save):
                    queue_popup(
                        "Chưa chọn đủ tháng!",
                        "Vui lòng tick chọn ít nhất 1 tháng cho mỗi mức nồng độ (hoặc tích chọn 'Cho Mức 2 lấy bằng Mức 1') trước khi lưu.",
                        "warning",
                    )
                    st.rerun()
                else:
                    st.session_state[f"force_empty_{sel_inst}_{sel_test}"] = False
                    save_bias_summary_records(sel_inst, sel_test, records_to_save)
                    queue_popup(
                        "Đã lưu BIAS % thành công!",
                        f"Đã lưu BIAS % trung bình của {sel_test} ({sel_inst}) vào Google Sheets.",
                        "success",
                    )
                    st.rerun()

    # ==========================================================================
    # TAB 2: BẢNG TỔNG HỢP BIAS % ĐÃ LƯU
    # ==========================================================================
    with tab_saved:
        df_saved = get_all_bias_summaries()
        with st.container(border=True):
            st.markdown("#### :material/table_chart: Bảng tổng hợp BIAS % trung bình đã chốt theo từng Dòng máy & Xét nghiệm")
            if df_saved.empty:
                st.write("Chưa có xét nghiệm nào được lưu kết quả BIAS %. Hãy tick chọn tháng tại Tab 1 và bấm **Lưu kết quả**.")
            else:
                df_display = df_saved[[
                    "instrument_name", "test_code", "unit", "level_name",
                    "mean_conc", "n_batches", "selected_batches",
                    "chosen_bias_pct", "updated_at"
                ]].rename(columns={
                    "instrument_name": "Thiết bị / Máy",
                    "test_code": "Mã XN",
                    "unit": "Đơn vị",
                    "level_name": "Mức nồng độ",
                    "mean_conc": "GT Ấn định TB",
                    "n_batches": "Số tháng chọn",
                    "selected_batches": "Các tháng EQA đã chọn",
                    "chosen_bias_pct": "BIAS % trung bình (=AVERAGE)",
                    "updated_at": "Cập nhật lúc",
                })
                st.dataframe(
                    df_display,
                    use_container_width=True,
                    hide_index=True,
                )

                act_c1, act_c2, act_c3 = st.columns([1.4, 1.8, 1.8])
                excel_buf = io.BytesIO()
                with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
                    df_display.to_excel(writer, index=False, sheet_name="Bias_Summary")
                act_c1.download_button(
                    ":material/table_view: Xuất Excel bảng BIAS %",
                    data=excel_buf.getvalue(),
                    file_name="Bang_Tong_Hop_Bias_EQA.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )

                saved_pairs = [
                    f"{r['instrument_name']} | {r['test_code']}"
                    for _, r in df_saved[["instrument_name", "test_code"]].drop_duplicates().iterrows()
                ]
                del_pair = act_c2.selectbox("Chọn xét nghiệm cần xóa kết quả lưu", saved_pairs, key="del_bias_test_sel")
                if act_c3.button(":material/delete: Xóa bản ghi BIAS % của XN này", type="secondary", use_container_width=True):
                    p_inst, p_test = [x.strip() for x in del_pair.split("|", 1)]
                    delete_bias_summary_by_test(p_test, instrument_name=p_inst)
                    queue_popup("Đã xóa!", f"Đã xóa kết quả BIAS % đã lưu của {p_test} ({p_inst}).", "error")
                    st.rerun()
