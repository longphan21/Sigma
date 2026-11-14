import io
import math
import re
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

# ==============================================================================
# DANH MỤC NỒNG ĐỘ IQC ĐÍCH MẶC ĐỊNH CỦA LAB (TRÍCH XUẤT TỪ FILE SIGMA 30.09.26)
# Thứ tự: [Mức 1 (LOW), Mức 2 (HIGH)] đúng theo thứ tự dòng của bảng SigmaALI & SigmaCobas
# ==============================================================================
LAB_IQC_TARGETS: Dict[str, Dict[str, List[float]]] = {
    "alinity": {
        "AFP": [73.397, 198.590],
        "CA125": [35.286, 71.014],
        "CA15-3": [31.731, 58.622],
        "CA19-9": [56.097, 164.856],
        "CEA": [15.359, 38.459],
        "CK-MB": [11.250, 38.399],
        "CK-MB MASS": [11.250, 38.399],
        "CORTISOL": [14.973, 33.641],
        "FERRITIN": [167.185, 402.869],
        "FT3": [4.267, 8.393],
        "FT4": [1.629, 2.727],
        "PSA": [3.235, 20.032],
        "TROPONIN I": [68.665, 933.533],
        "TSH": [3.924, 19.198],
        "CHLORIDE": [101.035, 114.857],
        "CL": [101.035, 114.857],
        "CL-": [101.035, 114.857],
        "POTASIUM": [3.873, 6.055],
        "POTASSIUM": [3.873, 6.055],
        "K": [3.873, 6.055],
        "K+": [3.873, 6.055],
        "SODIUM NATRI": [141.764, 160.405],
        "SODIUM": [141.764, 160.405],
        "NA": [141.764, 160.405],
        "NA+": [141.764, 160.405],
        "ACIDE URIDE": [5.769, 8.881],
        "ACIDE URIC": [5.769, 8.881],
        "URIC ACID": [5.769, 8.881],
        "UA": [5.769, 8.881],
        "ALBUMIN": [3.929, 2.839],
        "ALB": [3.929, 2.839],
        "CALCIUM TOTAL": [2.074, 2.909],
        "CALCIUM": [2.074, 2.909],
        "CA": [2.074, 2.909],
        "CHOLESTEROL TOTAL": [3.945, 7.708],
        "CHOLESTEROL": [3.945, 7.708],
        "CHOL": [3.945, 7.708],
        "CREATININ": [1.390, 4.099],
        "CREATININE": [1.390, 4.099],
        "CREA": [1.390, 4.099],
        "CRE": [1.390, 4.099],
        "CRP HS": [10.119, 27.861],
        "GLUCOSE": [5.667, 14.935],
        "GLU": [5.667, 14.935],
        "HDL-C": [1.463, 1.867],
        "HDL": [1.463, 1.867],
        "LDL-C": [2.596, 3.721],
        "LDL": [2.596, 3.721],
        "PROTEIN TOTAL": [5.737, 4.594],
        "TOTAL PROTEIN": [5.737, 4.594],
        "TP": [5.737, 4.594],
        "TRIGLYCERIDE": [1.056, 2.765],
        "TRIGLYCERIDES": [1.056, 2.765],
        "TRIG": [1.056, 2.765],
        "UREA": [7.281, 19.061],
        "GGT": [51.468, 159.368],
        "ALT": [32.061, 115.957],
        "GPT": [32.061, 115.957],
        "AMYLASE": [86.053, 288.225],
        "AMY": [86.053, 288.225],
        "AST": [37.784, 149.308],
        "GOT": [37.784, 149.308],
        "MICRO ALBUMIN": [26.534, 139.072],
    },
    "cobas": {
        "FT4": [1.410, 3.339],
        "TSH": [1.246, 7.876],
        "ACIDE URIC": [5.693, 8.670],
        "ACIDE URIDE": [5.693, 8.670],
        "URIC ACID": [5.693, 8.670],
        "UA": [5.693, 8.670],
        "ALBUMIN": [4.064, 3.121],
        "ALB": [4.064, 3.121],
        "BILIRUBIN TOTAL": [1.554, 4.293],
        "BILI-T": [1.554, 4.293],
        "TBIL": [1.554, 4.293],
        "BILIRUBIN DIRECT": [1.205, 2.132],
        "BILI-D": [1.205, 2.132],
        "DBIL": [1.205, 2.132],
        "CALCIUM TOTAL": [2.178, 3.131],
        "CALCIUM": [2.178, 3.131],
        "CA": [2.178, 3.131],
        "CHOLESTEROL TOTAL": [3.900, 7.712],
        "CHOLESTEROL": [3.900, 7.712],
        "CHOL": [3.900, 7.712],
        "CREATININ": [1.448, 4.258],
        "CREATININE": [1.448, 4.258],
        "CREA": [1.448, 4.258],
        "CRE": [1.448, 4.258],
        "CRP HS": [5.444, 52.208],
        "GLUCOSE": [5.796, 15.072],
        "GLU": [5.796, 15.072],
        "HDL-C": [0.752, 1.536],
        "HDL": [0.752, 1.536],
        "LDL-C": [1.583, 2.447],
        "LDL": [1.583, 2.447],
        "PROTEIN TOTAL": [5.591, 4.473],
        "TOTAL PROTEIN": [5.591, 4.473],
        "TP": [5.591, 4.473],
        "SẮT HUYẾT THANH": [113.465, 222.750],
        "IRON": [113.465, 222.750],
        "FE": [113.465, 222.750],
        "TRIGLYCERIDE": [1.078, 2.851],
        "TRIGLYCERIDES": [1.078, 2.851],
        "TRIG": [1.078, 2.851],
        "UREA": [7.374, 18.623],
        "GGT": [56.920, 169.272],
        "ALT": [37.831, 131.680],
        "GPT": [37.831, 131.680],
        "AMYLASE": [84.802, 263.537],
        "AMY": [84.802, 263.537],
        "AST": [44.905, 150.488],
        "GOT": [44.905, 150.488],
    },
}


def _lookup_default_iqc_targets(
    instrument_name: str,
    test_code: str,
    test_full_name: str,
    num_levels: int,
    df_saved: pd.DataFrame,
) -> List[float]:
    """
    Lấy nồng độ IQC đích mặc định của xét nghiệm:
    1. Ưu tiên đọc lại mốc IQC đã lưu trong bảng `eqa_bias_summary` (nếu có ghi trong level_name).
    2. Tra cứu từ bảng `LAB_IQC_TARGETS` của Alinity / Cobas theo mã hoặc tên xét nghiệm.
    3. Nếu chưa có thì trả về [0.0, ...] để thuật toán tự động phân vị.
    """
    if not df_saved.empty:
        sub = df_saved[
            (df_saved["instrument_name"].astype(str).str.strip().str.lower() == instrument_name.strip().lower())
            & (df_saved["test_code"].astype(str).str.strip().str.upper() == test_code.strip().upper())
        ].sort_values(by="level_no")
        if len(sub) == num_levels:
            parsed_targets = []
            for _, r in sub.iterrows():
                lv_name = str(r.get("level_name", ""))
                m = re.search(r"IQC:\s*([0-9.]+)", lv_name)
                if m:
                    try:
                        parsed_targets.append(float(m.group(1)))
                    except ValueError:
                        pass
            if len(parsed_targets) == num_levels:
                return parsed_targets

    if num_levels != 2:
        return [0.0] * num_levels

    inst_low = instrument_name.strip().lower()
    if "cobas" in inst_low or "roche" in inst_low:
        inst_key = "cobas"
    elif "alinity" in inst_low or "abbott" in inst_low:
        inst_key = "alinity"
    else:
        inst_key = "alinity"

    target_dict = LAB_IQC_TARGETS.get(inst_key, {})
    candidates = [
        test_code.strip().upper(),
        test_full_name.strip().upper(),
        re.sub(r"\s*\([^)]*\)", "", test_full_name).strip().upper(),
    ]
    for cand in candidates:
        if cand in target_dict:
            return list(target_dict[cand])
        for k, v in target_dict.items():
            if k == cand or (len(k) >= 3 and k in cand):
                return list(v)

    # Thử tìm ở bảng máy còn lại nếu tên máy trong PDF là tên chung (VD: Sinh hóa)
    other_dict = LAB_IQC_TARGETS["cobas" if inst_key == "alinity" else "alinity"]
    for cand in candidates:
        if cand in other_dict:
            return list(other_dict[cand])

    return [0.0] * num_levels


def _compute_exact_abs_bias_pct(df_test: pd.DataFrame) -> pd.DataFrame:
    """
    Tính chính xác BIAS % từng tháng theo đúng công thức Excel của Lab:
    =(ABS(D - E) * 100 / E), trong đó D là Kết quả đơn vị, E là Giá trị ấn định.
    Giữ nguyên độ chính xác số thực khi đưa vào hàm AVERAGE().
    """
    df = df_test.copy()
    exact_abs = []
    signed_list = []

    for _, row in df.iterrows():
        d_val = row.get("lab_result")
        e_val = row.get("assigned_value")
        b_pct = row.get("bias_pct")

        if pd.notna(d_val) and pd.notna(e_val) and float(e_val) != 0.0:
            d_f = float(d_val)
            e_f = float(e_val)
            exact_abs.append(abs(d_f - e_f) * 100.0 / abs(e_f))
            signed_list.append((d_f - e_f) * 100.0 / abs(e_f))
        elif pd.notna(b_pct):
            b_f = float(b_pct)
            exact_abs.append(abs(b_f))
            signed_list.append(b_f)
        else:
            exact_abs.append(float("nan"))
            signed_list.append(float("nan"))

    df["exact_abs_bias_pct"] = exact_abs
    df["exact_signed_bias_pct"] = signed_list
    return df


def _assign_concentration_levels(
    df_test: pd.DataFrame,
    num_levels: int,
    custom_targets: List[float],
) -> Tuple[pd.DataFrame, List[float], bool]:
    """
    Phân loại từng tháng EQA về Mức nồng độ IQC (Mức 1 - LOW, Mức 2 - HIGH) dựa trên:
    - Khoảng cách từ cả Giá trị ấn định (E) và Kết quả PXN (D) tới từng mốc nồng độ IQC của Lab.
    - Nếu người dùng để nồng độ IQC = 0, tự động ước lượng tâm cụm theo phân vị (quantiles).
    Trả về: (df_đã_gán_nhóm, danh_sách_tâm_nồng_độ, cờ_dải_nồng_độ_hẹp).
    """
    df = _compute_exact_abs_bias_pct(df_test)
    vals = df["assigned_value"].dropna().astype(float).tolist()
    if not vals:
        df["suggested_level"] = "Mức 1"
        df["iqc_distance"] = 0.0
        return df, [0.0] * num_levels, True

    if any(t > 0 for t in custom_targets):
        centers = [float(t) for t in custom_targets]
    else:
        s_vals = sorted(vals)
        if num_levels == 1:
            centers = [round(float(pd.Series(s_vals).median()), 3)]
        elif num_levels == 2:
            q1 = float(pd.Series(s_vals).quantile(0.25))
            q3 = float(pd.Series(s_vals).quantile(0.75))
            centers = [round(q1, 3), round(q3, 3)]
        else:
            q1 = float(pd.Series(s_vals).quantile(0.20))
            q2 = float(pd.Series(s_vals).quantile(0.50))
            q3 = float(pd.Series(s_vals).quantile(0.80))
            centers = [round(q1, 3), round(q2, 3), round(q3, 3)]

    min_v, max_v = min(vals), max(vals)
    is_narrow_spread = (max_v - min_v) <= (0.05 * max(abs(min_v), 1e-6))

    assigned_levels = []
    iqc_distances = []
    for idx_row, row in df.iterrows():
        asg_val = row.get("assigned_value")
        lab_val = row.get("lab_result")
        if pd.isna(asg_val):
            assigned_levels.append("Chưa có KQ")
            iqc_distances.append(float("nan"))
            continue

        asg_f = float(asg_val)
        lab_f = float(lab_val) if pd.notna(lab_val) else asg_f

        # Khoảng cách kết hợp cả Giá trị ấn định và Kết quả PXN tới từng mốc IQC
        distances = [
            (abs(asg_f - c) + abs(lab_f - c)) / 2.0
            for c in centers
        ]
        min_idx = distances.index(min(distances))
        assigned_levels.append(f"Mức {min_idx + 1}")
        iqc_distances.append(round(distances[min_idx], 3))

        # Lưu khoảng cách riêng tới từng mức để phục vụ sắp xếp độ sát IQC
        for lv_i, d_val in enumerate(distances):
            df.loc[idx_row, f"_dist_lv{lv_i + 1}"] = d_val

    df["suggested_level"] = assigned_levels
    df["iqc_distance"] = iqc_distances
    return df, centers, is_narrow_spread


def _auto_select_batches_all_levels(
    df_clustered: pd.DataFrame,
    num_levels: int,
    min_batches: int = 3,
    strategy: str = "iqc_recent",
    saved_batches_by_level: Dict[int, List[str]] = None,
) -> Tuple[pd.DataFrame, Dict[str, str]]:
    """
    Tự động chọn các tháng ngoại kiểm cho từng mức nồng độ theo đúng quy tắc của Lab:
    - 'iqc_recent': Chia các tháng về 2 mức nồng độ gần IQC -> Lấy 3 tháng gần nhất của mỗi mức.
                    Nếu KHÔNG đủ dữ liệu (có mức < 3 tháng), lấy trung bình cộng 3 tháng gần nhất
                    chung cho cả 2 mức nồng độ (cả 2 mức có Bias% bằng nhau).
    - 'iqc_closest': Trong mỗi nhóm nồng độ, ưu tiên lấy 3 tháng có nồng độ sát mốc IQC nhất.
                     Nếu thiếu dữ liệu (< 3 tháng ở bất kỳ mức nào), Fallback lấy 3 tháng gần nhất chung.
    - 'latest_n': Gộp chung 2 mức, lấy 3 tháng gần nhất cho cả 2 mức nồng độ.
    - 'saved': Khôi phục lại đúng các tháng đã được người dùng tick & lưu trong Google Sheets.
    - 'all': Lấy toàn bộ các tháng hợp lệ hiện có.
    """
    df = df_clustered.copy()
    valid_mask = df["exact_abs_bias_pct"].notna()
    valid_indices = [i for i, ok in enumerate(valid_mask.tolist()) if ok]
    n_total = len(df)
    rule_descriptions: Dict[str, str] = {}

    if not valid_indices:
        for idx in range(num_levels):
            df[f"use_lv{idx + 1}"] = [False] * n_total
            rule_descriptions[f"Mức {idx + 1}"] = "Không có dữ liệu hợp lệ"
        return df, rule_descriptions

    # 1. Nếu chọn khôi phục từ Database và đã có bản ghi lưu trước đó
    if strategy == "saved" and saved_batches_by_level:
        for idx in range(num_levels):
            lv_no = idx + 1
            saved_months = set(saved_batches_by_level.get(lv_no, []))
            if saved_months:
                flags = [
                    (i in valid_indices) and (str(df.loc[i, "month_year"]).strip() in saved_months)
                    for i in range(n_total)
                ]
                df[f"use_lv{lv_no}"] = flags
                rule_descriptions[f"Mức {lv_no}"] = f"Khôi phục {sum(flags)} tháng đã chốt lưu trong DB"
            else:
                flags = [i in set(valid_indices[:min_batches]) for i in range(n_total)]
                df[f"use_lv{lv_no}"] = flags
                rule_descriptions[f"Mức {lv_no}"] = f"Lấy {min(len(valid_indices), min_batches)} tháng gần nhất"
        return df, rule_descriptions

    # 2. Chế độ lấy tất cả các tháng hiện có
    if strategy == "all":
        for idx in range(num_levels):
            lv_no = idx + 1
            df[f"use_lv{lv_no}"] = [i in valid_indices for i in range(n_total)]
            rule_descriptions[f"Mức {lv_no}"] = f"Lấy toàn bộ {len(valid_indices)} tháng hiện có"
        return df, rule_descriptions

    # 3. Chế độ gộp chung lấy N tháng gần nhất cho cả 2 mức nồng độ
    if strategy == "latest_n":
        chosen_common = set(valid_indices[:min_batches])
        for idx in range(num_levels):
            lv_no = idx + 1
            df[f"use_lv{lv_no}"] = [i in chosen_common for i in range(n_total)]
            rule_descriptions[f"Mức {lv_no}"] = (
                f"Gộp chung: Lấy {len(chosen_common)} tháng gần nhất (2 mức nồng độ có Bias% bằng nhau)"
            )
        return df, rule_descriptions

    # 4. Kiểm tra từng mức xem có đủ >= min_batches tháng thuộc vùng nồng độ IQC đó không
    level_matches: Dict[int, List[int]] = {}
    for idx in range(num_levels):
        lv_no = idx + 1
        lv_code = f"Mức {lv_no}"
        matching = [
            i for i in valid_indices
            if str(df.loc[i, "suggested_level"]) == lv_code
        ]
        level_matches[lv_no] = matching

    all_levels_have_enough = all(len(level_matches[lv_no]) >= min_batches for lv_no in range(1, num_levels + 1))

    # Nếu KHÔNG đủ dữ liệu để tách đủ min_batches cho mỗi mức -> Fallback lấy 3 tháng gần nhất chung cho cả 2 mức
    if not all_levels_have_enough:
        chosen_common = set(valid_indices[:min_batches])
        counts_str = ", ".join([f"Mức {lv}: {len(level_matches[lv])} tháng" for lv in range(1, num_levels + 1)])
        for idx in range(num_levels):
            lv_no = idx + 1
            df[f"use_lv{lv_no}"] = [i in chosen_common for i in range(n_total)]
            rule_descriptions[f"Mức {lv_no}"] = (
                f"Không đủ {min_batches} tháng/mức ({counts_str}) → Lấy {len(chosen_common)} tháng gần nhất chung (2 mức có Bias% bằng nhau)"
            )
        return df, rule_descriptions

    # Nếu ĐỦ dữ liệu ở cả 2 mức nồng độ
    for idx in range(num_levels):
        lv_no = idx + 1
        lv_code = f"Mức {lv_no}"
        candidates = level_matches[lv_no]

        if strategy == "iqc_closest":
            # Sắp xếp ưu tiên khoảng cách nồng độ sát mốc IQC nhất, nếu bằng nhau ưu tiên tháng gần nhất
            dist_col = f"_dist_lv{lv_no}"
            sorted_cands = sorted(
                candidates,
                key=lambda r_idx: (
                    round(float(df.loc[r_idx, dist_col]), 4) if dist_col in df.columns and pd.notna(df.loc[r_idx, dist_col]) else 999999.0,
                    r_idx,
                ),
            )
            chosen_set = set(sorted_cands[:min_batches])
            rule_descriptions[lv_code] = (
                f"Đủ {len(candidates)} tháng ở {lv_code} → Chọn {min_batches} tháng có nồng độ sát mốc IQC nhất"
            )
        else:
            # Mặc định 'iqc_recent': Lấy 3 tháng gần nhất thuộc vùng nồng độ IQC của mức đó
            chosen_set = set(candidates[:min_batches])
            rule_descriptions[lv_code] = (
                f"Đủ {len(candidates)} tháng ở {lv_code} → Chọn {min_batches} tháng gần nhất sát vùng IQC {lv_code}"
            )

        df[f"use_lv{lv_no}"] = [i in chosen_set for i in range(n_total)]

    return df, rule_descriptions


def _calc_bias_metrics(df_sub: pd.DataFrame) -> Dict[str, Any]:
    """
    Tính trung bình cộng BIAS % từ những tháng được tick chọn theo đúng hàm =AVERAGE(...) trong Excel.
    """
    valid = df_sub.dropna(subset=["exact_abs_bias_pct"])
    n = len(valid)
    if n == 0:
        return {
            "n": 0,
            "mean_abs_bias_exact": 0.0,
            "mean_abs_bias": 0.0,
            "mean_signed_bias": 0.0,
            "rms_bias": 0.0,
            "mean_conc": 0.0,
            "mean_lab_conc": 0.0,
            "batches_str": "-",
            "formula_terms_str": "-",
        }

    abs_vals = valid["exact_abs_bias_pct"].astype(float)
    signed_vals = valid["exact_signed_bias_pct"].astype(float)
    conc_vals = valid["assigned_value"].dropna().astype(float)
    lab_vals = valid["lab_result"].dropna().astype(float)

    mean_abs_exact = float(abs_vals.mean())
    mean_signed = float(signed_vals.mean())
    rms = math.sqrt(float((abs_vals ** 2).mean()))
    mean_conc = float(conc_vals.mean()) if not conc_vals.empty else 0.0
    mean_lab_conc = float(lab_vals.mean()) if not lab_vals.empty else 0.0

    batches_list = valid["month_year"].astype(str).tolist()
    terms_list = [f"{v:.2f}%" for v in abs_vals.tolist()]

    return {
        "n": n,
        "mean_abs_bias_exact": round(mean_abs_exact, 4),
        "mean_abs_bias": round(mean_abs_exact, 2),
        "mean_signed_bias": round(mean_signed, 2),
        "rms_bias": round(rms, 2),
        "mean_conc": round(mean_conc, 3),
        "mean_lab_conc": round(mean_lab_conc, 3),
        "batches_str": ", ".join(batches_list),
        "formula_terms_str": " + ".join(terms_list),
    }


def render_bias_calculator_page():
    """Hàm dựng toàn bộ giao diện Trang Tính toán & Chốt %Bias từ dữ liệu EQA."""
    render_page_banner(
        "Tính toán & Chốt %Bias Ngoại kiểm (EQA) theo Mức Nồng Độ IQC",
        "Tính BIAS% = |KQ đơn vị - GT ấn định| * 100 / GT ấn định cho từng tháng, chia 2 mức theo IQC của Lab và chọn 3 tháng tính AVERAGE.",
    )

    df_all = get_all_results_joined()
    if df_all.empty:
        with st.container(border=True):
            st.markdown("#### :material/info: Chưa có dữ liệu Ngoại kiểm trong Database")
            st.write("Vui lòng tải file PDF kết quả ngoại kiểm tại mục **2. Import EQA PDF** trước khi tính %Bias.")
        return

    df_saved_all = get_all_bias_summaries()

    tab_calc, tab_saved = st.tabs([
        "🧮 1. Phân tích & Chọn tháng tính %Bias theo IQC",
        "📋 2. Bảng tổng hợp %Bias đã chốt (Đầu vào Six Sigma)",
    ])

    with tab_calc:
        with st.container(border=True):
            st.markdown("#### :material/tune: Bước 1: Chọn Thiết bị, Xét nghiệm & Mức nồng độ IQC của Lab")
            c1, c2, c3, c4 = st.columns([1.15, 1.15, 0.85, 1.85])

            inst_list = sorted(df_all["instrument_name"].dropna().unique().tolist())
            sel_inst = c1.selectbox("Thiết bị / Máy xét nghiệm", inst_list, key="bias_inst_sel")

            df_inst = df_all[df_all["instrument_name"] == sel_inst]
            test_list = sorted(df_inst["test_code"].dropna().unique().tolist())
            sel_test = c2.selectbox("Thông số Xét nghiệm", test_list, key="bias_test_sel")

            num_levels = c3.selectbox(
                "Số mức nồng độ IQC",
                options=[2, 3, 1],
                format_func=lambda x: f"{x} mức (LOW/HIGH)" if x == 2 else f"{x} mức nồng độ",
                key="bias_num_levels",
            )

            df_test = df_inst[df_inst["test_code"] == sel_test].copy()
            df_test = df_test.sort_values(by=["month_year", "batch_no"], ascending=[False, False]).reset_index(drop=True)
            unit_str = str(df_test["unit"].iloc[0]) if not df_test.empty else ""
            full_name_str = str(df_test["test_full_name"].iloc[0]) if not df_test.empty else sel_test

            # Kiểm tra xem xét nghiệm này đã có bản ghi lưu trong DB chưa
            saved_batches_by_level: Dict[int, List[str]] = {}
            if not df_saved_all.empty:
                sub_s = df_saved_all[
                    (df_saved_all["instrument_name"].astype(str).str.strip().str.lower() == sel_inst.strip().lower())
                    & (df_saved_all["test_code"].astype(str).str.strip().str.upper() == sel_test.strip().upper())
                ]
                for _, s_row in sub_s.iterrows():
                    lv_no = int(s_row.get("level_no", 1) or 1)
                    b_raw = str(s_row.get("selected_batches", ""))
                    b_items = [x.strip() for x in b_raw.split(",") if x.strip() and x.strip() != "-"]
                    if b_items:
                        saved_batches_by_level[lv_no] = b_items

            strategy_map = {
                "iqc_recent": "Tự động chuẩn Lab (3 tháng gần nhất sát mỗi mức IQC; thiếu thì lấy 3 tháng chung)",
                "iqc_closest": "Ưu tiên sát số IQC nhất (3 tháng có KQ & Ấn định sát mốc IQC nhất; thiếu thì gộp chung)",
                "latest_n": "Gộp chung 2 mức (Lấy 3 tháng gần nhất cho cả 2 mức có Bias% bằng nhau)",
                "all": "Lấy trung bình tất cả các tháng hiện có trong năm",
            }
            if saved_batches_by_level:
                strategy_map = {
                    "saved": "📌 Theo các tháng đã chốt lưu trong Database lần trước",
                    **strategy_map,
                }

            sel_strategy = c4.selectbox(
                "Quy tắc tự động đề xuất các tháng EQA",
                options=list(strategy_map.keys()),
                format_func=lambda k: strategy_map[k],
                key=f"bias_strategy_sel_{sel_inst}_{sel_test}",
            )

            # Hiển thị trực tiếp ô nhập Nồng độ IQC đích của Lab (tự động điền sẵn từ bảng SigmaALI / SigmaCobas)
            default_iqc_list = _lookup_default_iqc_targets(
                instrument_name=sel_inst,
                test_code=sel_test,
                test_full_name=full_name_str,
                num_levels=num_levels,
                df_saved=df_saved_all,
            )

            level_base_names = (
                ["Mức 1 (LOW)", "Mức 2 (HIGH)"]
                if num_levels == 2
                else (["Mức 1 (LOW)", "Mức 2 (MID)", "Mức 3 (HIGH)"] if num_levels == 3 else ["Mức 1 (Chung)"])
            )

            iqc_cols = st.columns(num_levels + 1)
            custom_targets: List[float] = []
            for idx in range(num_levels):
                def_val = float(default_iqc_list[idx]) if idx < len(default_iqc_list) else 0.0
                val_in = iqc_cols[idx].number_input(
                    f"🎯 Nồng độ IQC {level_base_names[idx]} ({unit_str})",
                    min_value=0.0,
                    value=def_val,
                    step=0.1,
                    format="%.3f",
                    help="Nhập Mean IQC tích lũy của Lab (VD: ALT mức 1 ~ 32.061, mức 2 ~ 115.957). Để = 0 nếu muốn App tự động chia phân vị.",
                    key=f"target_conc_{sel_inst}_{sel_test}_{num_levels}_{idx}",
                )
                custom_targets.append(val_in)

            min_batches_req = int(
                iqc_cols[-1].number_input(
                    "Số tháng chọn mỗi mức",
                    min_value=1,
                    max_value=12,
                    value=3,
                    step=1,
                    help="Mặc định lấy 3 tháng ngoại kiểm cho mỗi mức nồng độ IQC.",
                    key="bias_min_batches_input",
                )
            )

        # Phân cụm nồng độ & tự động đề xuất các tháng được tick
        df_clustered, centers, _ = _assign_concentration_levels(df_test, num_levels, custom_targets)
        df_clustered, rule_descriptions = _auto_select_batches_all_levels(
            df_clustered=df_clustered,
            num_levels=num_levels,
            min_batches=min_batches_req,
            strategy=sel_strategy,
            saved_batches_by_level=saved_batches_by_level,
        )

        level_display_names = [
            f"{level_base_names[i]} (IQC: {centers[i]:.3f})" if custom_targets[i] > 0 else f"{level_base_names[i]} (~{centers[i]:.3f})"
            for i in range(num_levels)
        ]

        with st.container(border=True):
            st.markdown(
                f"#### :material/check_box: Bước 2: Kiểm tra & Tự ý chọn/đổi tháng EQA cho **{sel_test} — {full_name_str}** ({len(df_clustered)} tháng trong DB)"
            )

            info_lines = []
            for idx in range(num_levels):
                lv_code = f"Mức {idx + 1}"
                r_desc = rule_descriptions.get(lv_code, "")
                info_lines.append(f"<span><b>{level_display_names[idx]} {unit_str}:</b> {r_desc}</span>")
            render_html(f"""
            <div class="history-meta-bar" style="margin-bottom:8px;">
                {" &nbsp;|&nbsp; ".join(info_lines)}
            </div>
            """)

            editor_cols = [f"use_lv{i + 1}" for i in range(num_levels)] + [
                "month_year",
                "batch_label",
                "lab_result",
                "assigned_value",
                "abs_bias_display",
                "bias_pct",
                "z_score",
                "suggested_level",
                "iqc_distance",
            ]
            df_clustered["abs_bias_display"] = df_clustered["exact_abs_bias_pct"].round(4)
            df_editor_in = df_clustered[editor_cols].copy()

            col_cfg = {
                "month_year": st.column_config.TextColumn("Tháng/Năm", disabled=True),
                "batch_label": st.column_config.TextColumn("Đợt EQA", disabled=True),
                "lab_result": st.column_config.NumberColumn(f"KQ Đơn vị - D ({unit_str})", format="%.3f", disabled=True),
                "assigned_value": st.column_config.NumberColumn(f"GT Ấn định - E ({unit_str})", format="%.3f", disabled=True),
                "abs_bias_display": st.column_config.NumberColumn("BIAS % = |D-E|*100/E", format="%.4f%%", disabled=True),
                "bias_pct": st.column_config.NumberColumn("%Bias (Có dấu)", format="%+.2f%%", disabled=True),
                "z_score": st.column_config.NumberColumn("z-score", format="%+.2f", disabled=True),
                "suggested_level": st.column_config.TextColumn("Nhóm gần IQC", disabled=True),
                "iqc_distance": st.column_config.NumberColumn("Độ lệch Δ so với IQC", format="%.3f", disabled=True),
            }
            for idx in range(num_levels):
                col_cfg[f"use_lv{idx + 1}"] = st.column_config.CheckboxColumn(
                    f"☑️ Chọn cho {level_base_names[idx]}",
                    help=f"Tick hoặc bỏ tick để chủ động chọn các tháng đưa vào hàm AVERAGE tính %Bias cho {level_base_names[idx]}",
                    default=True,
                )

            target_sig = "_".join(f"{t:.3f}" for t in custom_targets)
            edited_df = st.data_editor(
                df_editor_in,
                column_config=col_cfg,
                use_container_width=True,
                hide_index=True,
                key=f"editor_bias_{sel_inst}_{sel_test}_{num_levels}_{sel_strategy}_{min_batches_req}_{target_sig}",
            )

        with st.container(border=True):
            st.markdown("#### :material/calculate: Bước 3: Kết quả BIAS % Trung bình (=AVERAGE) theo từng Mức nồng độ & Chốt Lưu")

            bias_formula_choice = st.radio(
                "Công thức tính %Bias đại diện lưu sang bảng Six Sigma:",
                options=["mean_abs_bias", "rms_bias", "abs_of_mean_signed"],
                format_func=lambda k: {
                    "mean_abs_bias": "Trung bình cộng BIAS% từng tháng: =AVERAGE(|D-E|*100/E) — Chuẩn file Sigma của Lab",
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
                lv_title = level_display_names[idx]
                selected_mask = edited_df[col_flag] == True
                sub_selected = df_clustered.loc[selected_mask.index[selected_mask]]
                metrics = _calc_bias_metrics(sub_selected)

                if bias_formula_choice == "mean_abs_bias":
                    chosen_val = metrics["mean_abs_bias_exact"]
                elif bias_formula_choice == "rms_bias":
                    chosen_val = metrics["rms_bias"]
                else:
                    chosen_val = round(abs(metrics["mean_signed_bias"]), 4)

                with lv_cols[idx]:
                    badge_state = "ĐẠT" if metrics["n"] >= min_batches_req else f"ĐÃ CHỌN {metrics['n']} THÁNG"
                    render_html(f"""
                    <div class="eval-result-box {'eval-result-pass' if metrics['n'] > 0 else 'eval-result-fail'}" style="margin-bottom:8px;">
                        <span><b>{lv_title}</b> (TB tháng chọn: <code>{metrics['mean_conc']:.3f} {unit_str}</code>)</span>
                        {format_status_badge_html(badge_state)}
                    </div>
                    """)
                    m_a, m_b, m_c = st.columns(3)
                    m_a.metric("BIAS % TB (Chuẩn Excel)", f"{metrics['mean_abs_bias_exact']:.4f}%")
                    m_b.metric("BIAS % TB (Làm tròn)", f"{metrics['mean_abs_bias']:.2f}%")
                    m_c.metric("KQ ĐV TB / Ấn định TB", f"{metrics['mean_lab_conc']:.2f} / {metrics['mean_conc']:.2f}")

                    render_html(f"""
                    <div class="history-meta-bar">
                        <span><b>Các tháng đã chọn ({metrics['n']} tháng):</b> <code>{metrics['batches_str']}</code></span>
                        <span><b>Chi tiết:</b> <code>({metrics['formula_terms_str']}) / {metrics['n'] if metrics['n'] > 0 else 1}</code></span>
                        <span><b>%Bias chốt tính Sigma:</b> <span class="date-pill">{chosen_val:.4f}% ({chosen_val:.2f}%)</span></span>
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
                    "mean_abs_bias_pct": metrics["mean_abs_bias_exact"],
                    "mean_signed_bias_pct": metrics["mean_signed_bias"],
                    "rms_bias_pct": metrics["rms_bias"],
                    "chosen_bias_pct": chosen_val,
                    "formula_type": bias_formula_choice,
                })

            if st.button(":material/save: Lưu kết quả %Bias của xét nghiệm này vào Google Sheets", type="primary"):
                if any(r["n_batches"] == 0 for r in records_to_save):
                    queue_popup(
                        "Chưa chọn đủ tháng!",
                        "Có mức nồng độ chưa được tick chọn tháng EQA nào. Vui lòng tick ít nhất 1 tháng cho mỗi mức.",
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

    with tab_saved:
        df_saved = get_all_bias_summaries()
        with st.container(border=True):
            st.markdown("#### :material/table_chart: Bảng tổng hợp %Bias đã chốt theo từng Xét nghiệm & Mức nồng độ IQC")
            if df_saved.empty:
                st.write("Chưa có xét nghiệm nào được lưu kết quả %Bias. Hãy thực hiện tại Tab 1 và bấm **Lưu kết quả %Bias**.")
            else:
                df_display = df_saved[[
                    "instrument_name", "test_code", "unit", "level_name",
                    "mean_conc", "n_batches", "selected_batches",
                    "mean_abs_bias_pct", "rms_bias_pct", "chosen_bias_pct", "updated_at"
                ]].rename(columns={
                    "instrument_name": "Thiết bị",
                    "test_code": "Mã XN",
                    "unit": "Đơn vị",
                    "level_name": "Mức nồng độ IQC",
                    "mean_conc": "Nồng độ EQA TB",
                    "n_batches": "Số tháng",
                    "selected_batches": "Các tháng EQA đã chọn",
                    "mean_abs_bias_pct": "BIAS % TB (=AVERAGE)",
                    "rms_bias_pct": "RMS %Bias",
                    "chosen_bias_pct": "%Bias Chốt (Tính Sigma)",
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
                    ":material/table_view: Xuất Excel bảng %Bias",
                    data=excel_buf.getvalue(),
                    file_name="Bang_Tong_Hop_Bias_EQA.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )

                saved_pairs = [
                    f"{r['instrument_name']} | {r['test_code']}"
                    for _, r in df_saved[["instrument_name", "test_code"]].drop_duplicates().iterrows()
                ]
                del_pair = act_c2.selectbox("Chọn xét nghiệm cần xóa kết quả chốt", saved_pairs, key="del_bias_test_sel")
                if act_c3.button(":material/delete: Xóa bản ghi %Bias của XN này", type="secondary", use_container_width=True):
                    p_inst, p_test = [x.strip() for x in del_pair.split("|", 1)]
                    delete_bias_summary_by_test(p_test, instrument_name=p_inst)
                    queue_popup("Đã xóa!", f"Đã xóa kết quả %Bias đã chốt của {p_test} ({p_inst}).", "error")
                    st.rerun()
