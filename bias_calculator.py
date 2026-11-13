import math
from typing import List, Dict, Any, Tuple
import pandas as pd
import streamlit as st

from ui_theme import render_page_banner, render_html, queue_popup, format_status_badge_html
from database import (
    get_all_results_joined,
    save_bias_summary_records,
    get_all_bias_summaries,
    delete_bias_summary_by_test,
)


def _assign_concentration_levels(
    df_test: pd.DataFrame,
    num_levels: int,
    custom_targets: List[float],
) -> Tuple[pd.DataFrame, List[float]]:
    """
    Phân loại từng đợt EQA vào Mức nồng độ (Mức 1, Mức 2, Mức 3) dựa trên:
    - Nồng độ đích do người dùng nhập (nếu > 0)
    - Hoặc tự động chia theo phân vị (quantiles) từ lịch sử Giá trị ấn định.
    """
    df = df_test.copy()
    vals = df["assigned_value"].dropna().astype(float).tolist()
    if not vals:
        df["suggested_level"] = "Mức 1"
        return df, [0.0] * num_levels

    # Xác định nồng độ trung tâm (centers) cho từng mức
    if any(t > 0 for t in custom_targets):
        centers = custom_targets
    else:
        s_vals = sorted(vals)
        if num_levels == 1:
            centers = [float(pd.Series(s_vals).median())]
        elif num_levels == 2:
            q1 = float(pd.Series(s_vals).quantile(0.25))
            q3 = float(pd.Series(s_vals).quantile(0.75))
            centers = [round(q1, 3), round(q3, 3)]
        else:
            q1 = float(pd.Series(s_vals).quantile(0.20))
            q2 = float(pd.Series(s_vals).quantile(0.50))
            q3 = float(pd.Series(s_vals).quantile(0.80))
            centers = [round(q1, 3), round(q2, 3), round(q3, 3)]

    # Nếu tất cả các đợt có cùng 1 giá trị ấn định (chênh lệch không đáng kể)
    min_v, max_v = min(vals), max(vals)
    is_ narrow_spread = (max_v - min_v) <= (0.05 * max(abs(min_v), 1e-6))

    assigned_levels = []
    for _, row in df.iterrows():
        val = row.get("assigned_value")
        if pd.isna(val) or is_narrow_spread:
            assigned_levels.append("Hỗn hợp / Chung")
            continue
        # Tìm mức có khoảng cách gần nhất với Giá trị ấn định
        distances = [abs(float(val) - c) for c in centers]
        min_idx = distances.index(min(distances))
        assigned_levels.append(f"Mức {min_idx + 1}")

    df["suggested_level"] = assigned_levels
    return df, centers


def _auto_select_batches_for_level(
    df_sorted: pd.DataFrame,
    level_label: str,
    min_batches: int = 3,
    strategy: str = "auto",
) -> Tuple[List[bool], str]:
    """
    Trả về danh sách True/False tương ứng với các đợt được chọn cho `level_label`
    cùng chuỗi mô tả quy tắc đã áp dụng.
    df_sorted: DataFrame đã sắp xếp từ đợt mới nhất -> cũ nhất.
    """
    n_total = len(df_sorted)
    if n_total == 0:
        return [], "Không có dữ liệu"

    # Chế độ 1: Lấy tất cả các đợt
    if strategy == "all":
        return [True] * n_total, f"Lấy toàn bộ {n_total} đợt hiện có"

    # Chế độ 2: Luôn lấy N đợt gần nhất không phân biệt nồng độ
    if strategy == "latest_n":
        flags = [i < min_batches for i in range(n_total)]
        return flags, f"Lấy {min(n_total, min_batches)} đợt gần nhất (không chia nồng độ)"

    # Chế độ 3 (Mặc định - Auto thông minh theo quy tắc của lab):
    # Tìm các dòng thuộc đúng `level_label`
    matching_indices = [
        idx for idx, lv in enumerate(df_sorted["suggested_level"].tolist())
        if lv == level_label
    ]

    if len(matching_indices) >= min_batches:
        chosen_set = set(matching_indices[:min_batches])
        flags = [idx in chosen_set for idx in range(n_total)]
        return flags, f"Đủ ≥ {min_batches} đợt ở {level_label} → Lấy {min_batches} đợt gần nhất của {level_label}"
    else:
        # Fallback: Không đủ tối thiểu 3 đợt ở mức nồng độ này -> lấy 3 đợt gần nhất chung
        flags = [idx < min_batches for idx in range(n_total)]
        return (
            flags,
            f"Chỉ có {len(matching_indices)} đợt ở {level_label} (< {min_batches} đợt) → Fallback lấy {min(n_total, min_batches)} đợt gần nhất",
        )


def _calc_bias_metrics(df_sub: pd.DataFrame) -> Dict[str, Any]:
    """Tính các chỉ số %Bias từ những đợt được tick chọn."""
    valid = df_sub.dropna(subset=["bias_pct"])
    n = len(valid)
    if n == 0:
        return {
            "n": 0,
            "mean_abs_bias": 0.0,
            "mean_signed_bias": 0.0,
            "rms_bias": 0.0,
            "mean_conc": 0.0,
            "batches_str": "-",
        }

    abs_vals = valid["bias_pct"].astype(float).abs()
    signed_vals = valid["bias_pct"].astype(float)
    conc_vals = valid["assigned_value"].dropna().astype(float)

    mean_abs = float(abs_vals.mean())
    mean_signed = float(signed_vals.mean())
    rms = math.sqrt(float((signed_vals ** 2).mean()))
    mean_conc = float(conc_vals.mean()) if not conc_vals.empty else 0.0
    batches_list = valid["month_year"].astype(str).tolist()

    return {
        "n": n,
        "mean_abs_bias": round(mean_abs, 2),
        "mean_signed_bias": round(mean_signed, 2),
        "rms_bias": round(rms, 2),
        "mean_conc": round(mean_conc, 3),
        "batches_str": ", ".join(batches_list),
    }


def render_bias_calculator_page():
    """Hàm dựng toàn bộ giao diện Trang Tính toán & Chốt %Bias từ dữ liệu EQA."""
    render_page_banner(
        "Tính toán & Chốt %Bias Ngoại kiểm (EQA) theo Mức Nồng Độ",
        "Tự động phân cụm nồng độ, đề xuất 3 đợt EQA gần nhất (hoặc Fallback khi thiếu đợt) và cho phép tùy chỉnh thủ công từng đợt.",
    )

    df_all = get_all_results_joined()
    if df_all.empty:
        with st.container(border=True):
            st.markdown("#### :material/info: Chưa có dữ liệu Ngoại kiểm trong Database")
            st.write("Vui lòng tải file PDF kết quả ngoại kiểm tại mục **2. Import EQA PDF** trước khi tính %Bias.")
        return

    tab_calc, tab_saved = st.tabs([
        "🧮 1. Phân tích & Chọn đợt tính %Bias",
        "📋 2. Bảng tổng hợp %Bias đã chốt (Đầu vào Six Sigma)",
    ])

    # ==========================================================================
    # TAB 1: PHÂN TÍCH, ĐỀ XUẤT TỰ ĐỘNG & TÙY CHỈNH THỦ CÔNG TRÊN BẢNG
    # ==========================================================================
    with tab_calc:
        with st.container(border=True):
            st.markdown("#### :material/tune: Bước 1: Chọn Xét nghiệm & Cấu hình quy tắc gợi ý đợt EQA")
            c1, c2, c3, c4 = st.columns([1.2, 1.2, 1.0, 1.6])

            inst_list = sorted(df_all["instrument_name"].dropna().unique().tolist())
            sel_inst = c1.selectbox("Thiết bị / Máy xét nghiệm", inst_list, key="bias_inst_sel")

            df_inst = df_all[df_all["instrument_name"] == sel_inst]
            test_list = sorted(df_inst["test_code"].dropna().unique().tolist())
            sel_test = c2.selectbox("Thông số Xét nghiệm", test_list, key="bias_test_sel")

            num_levels = c3.selectbox(
                "Số mức nồng độ (Level)",
                options=[2, 3, 1],
                format_func=lambda x: f"{x} mức nồng độ",
                key="bias_num_levels",
            )

            strategy_map = {
                "auto": "Tự động (3 đợt gần nhất cùng mức, thiếu thì lấy 3 đợt chung)",
                "latest_n": "Lấy 3 đợt gần nhất (Không phân biệt mức nồng độ)",
                "all": "Lấy tất cả các đợt hiện có",
            }
            sel_strategy = c4.selectbox(
                "Quy tắc đề xuất mặc định",
                options=list(strategy_map.keys()),
                format_func=lambda k: strategy_map[k],
                key="bias_strategy_sel",
            )

            # Lọc dữ liệu của xét nghiệm đang chọn, sắp xếp đợt mới nhất lên đầu
            df_test = df_inst[df_inst["test_code"] == sel_test].copy()
            df_test = df_test.sort_values(by=["month_year", "batch_no"], ascending=[False, False]).reset_index(drop=True)
            unit_str = str(df_test["unit"].iloc[0]) if not df_test.empty else ""

            # Cho phép người dùng nhập nồng độ IQC đích (tùy chọn) để phân cụm chính xác hơn
            with st.expander("⚙️ Tùy chọn nâng cao: Nhập nồng độ đích IQC (Để = 0 nếu muốn App tự động chia ngưỡng)", expanded=False):
                t_cols = st.columns(num_levels + 1)
                custom_targets = []
                level_names = ["Mức 1 (Thấp)", "Mức 2 (Cao)"] if num_levels == 2 else (
                    ["Mức 1 (Thấp)", "Mức 2 (TB)", "Mức 3 (Cao)"] if num_levels == 3 else ["Mức 1 (Chung)"]
                )
                for idx in range(num_levels):
                    val_in = t_cols[idx].number_input(
                        f"Nồng độ đích {level_names[idx]} ({unit_str})",
                        min_value=0.0,
                        value=0.0,
                        step=0.1,
                        format="%.3f",
                        key=f"target_conc_{sel_inst}_{sel_test}_{idx}",
                    )
                    custom_targets.append(val_in)
                min_batches_req = int(t_cols[-1].number_input(
                    "Số đợt tối thiểu cần lấy",
                    min_value=1,
                    max_value=12,
                    value=3,
                    step=1,
                    key="bias_min_batches_input",
                ))

        # Thực hiện phân cụm nồng độ và đề xuất dấu tick tự động
        df_clustered, centers = _assign_concentration_levels(df_test, num_levels, custom_targets)

        level_rules_info = {}
        for idx in range(num_levels):
            lv_code = f"Mức {idx + 1}"
            col_flag = f"use_lv{idx + 1}"
            flags, rule_desc = _auto_select_batches_for_level(
                df_clustered,
                level_label=lv_code,
                min_batches=min_batches_req,
                strategy=sel_strategy,
            )
            df_clustered[col_flag] = flags
            level_rules_info[lv_code] = (centers[idx], rule_desc)

        # Khởi tạo bảng tương tác cho người dùng tick/bỏ tick
        with st.container(border=True):
            st.markdown(
                f"#### :material/check_box: Bước 2: Kiểm tra & Tick chọn các đợt EQA cho **{sel_test}** ({len(df_clustered)} đợt trong DB)"
            )

            # Hiển thị giải thích quy tắc mà thuật toán vừa áp dụng cho từng mức
            info_lines = []
            for idx in range(num_levels):
                lv_code = f"Mức {idx + 1}"
                center_val, r_desc = level_rules_info[lv_code]
                info_lines.append(
                    f"<span><b>{level_names[idx]} (~{center_val:.3f} {unit_str}):</b> {r_desc}</span>"
                )
            render_html(f"""
            <div class="history-meta-bar" style="margin-bottom:8px;">
                {" &nbsp;|&nbsp; ".join(info_lines)}
            </div>
            """)

            # Chuẩn bị DataFrame cho st.data_editor
            editor_cols = [f"use_lv{i + 1}" for i in range(num_levels)] + [
                "month_year",
                "batch_label",
                "assigned_value",
                "lab_result",
                "bias_pct",
                "abs_bias_pct",
                "z_score",
                "suggested_level",
            ]
            df_clustered["abs_bias_pct"] = df_clustered["bias_pct"].astype(float).abs().round(2)
            df_editor_in = df_clustered[editor_cols].copy()

            col_cfg = {
                "month_year": st.column_config.TextColumn("Kỳ (Tháng/Năm)", disabled=True),
                "batch_label": st.column_config.TextColumn("Tên đợt EQA", disabled=True),
                "assigned_value": st.column_config.NumberColumn(f"GT Ấn định ({unit_str})", format="%.3f", disabled=True),
                "lab_result": st.column_config.NumberColumn(f"KQ Đơn vị ({unit_str})", format="%.3f", disabled=True),
                "bias_pct": st.column_config.NumberColumn("%Bias (Có dấu)", format="%+.2f%%", disabled=True),
                "abs_bias_pct": st.column_config.NumberColumn("|%Bias| (Tuyệt đối)", format="%.2f%%", disabled=True),
                "z_score": st.column_config.NumberColumn("z-score", format="%+.2f", disabled=True),
                "suggested_level": st.column_config.TextColumn("Nhóm nồng độ gợi ý", disabled=True),
            }
            for idx in range(num_levels):
                col_cfg[f"use_lv{idx + 1}"] = st.column_config.CheckboxColumn(
                    f"☑️ Dùng cho {level_names[idx]}",
                    help=f"Tick chọn để đưa đợt này vào tính %Bias trung bình của {level_names[idx]}",
                    default=True,
                )

            edited_df = st.data_editor(
                df_editor_in,
                column_config=col_cfg,
                use_container_width=True,
                hide_index=True,
                key=f"editor_bias_{sel_inst}_{sel_test}_{num_levels}_{sel_strategy}",
            )

        # Bước 3: Tính toán Real-time từ các dòng đang được tick chọn trong edited_df
        with st.container(border=True):
            st.markdown("#### :material/calculate: Bước 3: Kết quả %Bias trung bình theo từng Mức nồng độ & Lưu Database")

            bias_formula_choice = st.radio(
                "Chọn công thức %Bias đại diện để lưu cho bước tính Six Sigma:",
                options=["mean_abs_bias", "rms_bias", "abs_of_mean_signed"],
                format_func=lambda k: {
                    "mean_abs_bias": "Trung bình |%Bias| tuyệt đối: Mean(|%Bias|) — Chuẩn thông dụng nhất",
                    "rms_bias": "Căn bậc 2 trung bình bình phương: RMS %Bias",
                    "abs_of_mean_signed": "Trị tuyệt đối của Trung bình có dấu: |Mean(%Bias)|",
                }[k],
                horizontal=True,
                key="bias_formula_radio",
            )

            lv_cols = st.columns(num_levels)
            records_to_save = []

            for idx in range(num_levels):
                col_flag = f"use_lv{idx + 1}"
                lv_title = level_names[idx]
                sub_selected = edited_df[edited_df[col_flag] == True]
                metrics = _calc_bias_metrics(sub_selected)

                if bias_formula_choice == "mean_abs_bias":
                    chosen_val = metrics["mean_abs_bias"]
                elif bias_formula_choice == "rms_bias":
                    chosen_val = metrics["rms_bias"]
                else:
                    chosen_val = round(abs(metrics["mean_signed_bias"]), 2)

                with lv_cols[idx]:
                    badge_state = "ĐẠT" if metrics["n"] >= min_batches_req else f"MỚI CHỌN {metrics['n']} ĐỢT"
                    render_html(f"""
                    <div class="eval-result-box {'eval-result-pass' if metrics['n'] > 0 else 'eval-result-fail'}" style="margin-bottom:8px;">
                        <span><b>{lv_title}</b> (Nồng độ TB: <code>{metrics['mean_conc']:.3f} {unit_str}</code>)</span>
                        {format_status_badge_html(badge_state)}
                    </div>
                    """)
                    m_a, m_b, m_c = st.columns(3)
                    m_a.metric("Mean |%Bias|", f"{metrics['mean_abs_bias']:.2f}%")
                    m_b.metric("RMS %Bias", f"{metrics['rms_bias']:.2f}%")
                    m_c.metric("Mean %Bias", f"{metrics['mean_signed_bias']:+.2f}%")

                    render_html(f"""
                    <div class="history-meta-bar">
                        <span><b>Số đợt đã chọn:</b> <code>{metrics['n']} đợt</code> ({metrics['batches_str']})</span>
                        <span><b>%Bias chốt tính Sigma:</b> <span class="date-pill">{chosen_val:.2f}%</span></span>
                    </div>
                    """)

                records_to_save.append({
                    "instrument_name": sel_inst,
                    "test_code": sel_test,
                    "unit": unit_str,
                    "level_no": idx + 1,
                    "level_name": lv_title,
                    "mean_conc": metrics["mean_conc"],
                    "n_batches": metrics["n"],
                    "selected_batches": metrics["batches_str"],
                    "mean_abs_bias_pct": metrics["mean_abs_bias"],
                    "mean_signed_bias_pct": metrics["mean_signed_bias"],
                    "rms_bias_pct": metrics["rms_bias"],
                    "chosen_bias_pct": chosen_val,
                    "formula_type": bias_formula_choice,
                })

            if st.button(":material/save: Lưu kết quả %Bias của xét nghiệm này vào Google Sheets", type="primary"):
                if any(r["n_batches"] == 0 for r in records_to_save):
                    queue_popup(
                        "Chưa chọn đủ đợt!",
                        "Có mức nồng độ chưa được tick chọn đợt EQA nào. Vui lòng tick ít nhất 1 đợt cho mỗi mức.",
                        "warning",
                    )
                    st.rerun()
                else:
                    save_bias_summary_records(sel_inst, sel_test, records_to_save)
                    queue_popup(
                        "Đã chốt %Bias thành công!",
                        f"Đã lưu %Bias của {num_levels} mức nồng độ cho xét nghiệm {sel_test} ({sel_inst}) lên Google Sheets.",
                        "success",
                    )
                    st.rerun()

    # ==========================================================================
    # TAB 2: DANH SÁCH %BIAS ĐÃ CHỐT CỦA CÁC XÉT NGHIỆM (SẴN SÀNG CHO SIX SIGMA)
    # ==========================================================================
    with tab_saved:
        df_saved = get_all_bias_summaries()
        with st.container(border=True):
            st.markdown("#### :material/table_chart: Bảng tổng hợp %Bias đã chốt theo từng Xét nghiệm & Mức nồng độ")
            if df_saved.empty:
                st.write("Chưa có xét nghiệm nào được lưu kết quả %Bias. Hãy thực hiện tại Tab 1 và bấm **Lưu kết quả %Bias**.")
            else:
                st.dataframe(
                    df_saved[[
                        "instrument_name", "test_code", "unit", "level_name",
                        "mean_conc", "n_batches", "selected_batches",
                        "mean_abs_bias_pct", "rms_bias_pct", "chosen_bias_pct", "updated_at"
                    ]].rename(columns={
                        "instrument_name": "Thiết bị",
                        "test_code": "Mã XN",
                        "unit": "Đơn vị",
                        "level_name": "Mức nồng độ",
                        "mean_conc": "Nồng độ TB",
                        "n_batches": "Số đợt",
                        "selected_batches": "Các kỳ EQA đã dùng",
                        "mean_abs_bias_pct": "Mean |%Bias|",
                        "rms_bias_pct": "RMS %Bias",
                        "chosen_bias_pct": "%Bias Chốt (Tính Sigma)",
                        "updated_at": "Cập nhật lúc",
                    }),
                    use_container_width=True,
                    hide_index=True,
                )

                del_c1, del_c2 = st.columns([2.0, 3.0])
                saved_tests = sorted(df_saved["test_code"].unique().tolist())
                del_test = del_c1.selectbox("Chọn xét nghiệm cần xóa kết quả chốt", saved_tests, key="del_bias_test_sel")
                if del_c2.button(":material/delete: Xóa bản ghi %Bias của XN này", type="secondary"):
                    delete_bias_summary_by_test(del_test)
                    queue_popup("Đã xóa!", f"Đã xóa kết quả %Bias đã chốt của {del_test}.", "error")
                    st.rerun()