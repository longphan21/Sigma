import streamlit as st
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any, Optional
from connection import get_spreadsheet

BATCHES_HEADERS = [
    "id", "batch_label", "batch_no", "month_year", "program_name", "program_code",
    "unit_code", "instrument_name", "sample_code", "provider_name", "source_filename",
    "total_tests", "pass_count", "warn_count", "fail_count", "created_at", "notes"
]
RESULTS_HEADERS = [
    "id", "batch_id", "test_code", "test_full_name", "unit", "lab_result", "assigned_value",
    "sigma_p", "z_score", "bias_abs", "bias_pct", "eval_status", "all_n", "all_mean", "all_sd",
    "all_cv", "all_excluded", "method_name", "method_n", "method_mean", "method_sd",
    "method_cv", "method_excluded", "peer_name", "peer_n", "peer_mean", "peer_sd",
    "peer_cv", "peer_excluded", "page_no"
]
BIAS_SUMMARY_HEADERS = [
    "id", "instrument_name", "test_code", "unit", "level_no", "level_name",
    "mean_conc", "n_batches", "selected_batches", "mean_abs_bias_pct",
    "mean_signed_bias_pct", "rms_bias_pct", "chosen_bias_pct", "formula_type", "updated_at"
]


def get_ws(name: str, headers: List[str]):
    """Lấy Worksheet trên Google Sheets, nếu chưa có thì tự động tạo kèm dòng Header."""
    doc = get_spreadsheet()
    try:
        return doc.worksheet(name)
    except Exception:
        ws = doc.add_worksheet(title=name, rows=200, cols=len(headers))
        ws.append_row(headers)
        return ws


def clear_db_cache():
    """Xóa bộ nhớ đệm mỗi khi có thao tác Lưu hoặc Xóa dữ liệu."""
    st.cache_data.clear()


def init_database():
    """Khởi tạo 3 trang tính trên Google Sheets nếu chưa tồn tại."""
    get_ws("eqa_batches", BATCHES_HEADERS)
    get_ws("eqa_results", RESULTS_HEADERS)
    get_ws("eqa_bias_summary", BIAS_SUMMARY_HEADERS)


@st.cache_data(ttl=120, show_spinner=False)
def get_all_batches() -> List[Dict[str, Any]]:
    ws = get_ws("eqa_batches", BATCHES_HEADERS)
    records = ws.get_all_records()
    records.sort(
        key=lambda x: (str(x.get("month_year", "")), str(x.get("batch_no", "")), int(x.get("id", 0) or 0)),
        reverse=True,
    )
    return records


def check_batch_exists(program_code: str, batch_no: str, month_year: str, instrument_name: str, sample_code: str = "") -> Optional[int]:
    records = get_all_batches()
    for r in records:
        if (
            str(r.get("program_code", "")).strip() == program_code.strip()
            and str(r.get("batch_no", "")).strip() == batch_no.strip()
            and str(r.get("month_year", "")).strip() == month_year.strip()
            and str(r.get("instrument_name", "")).strip() == instrument_name.strip()
        ):
            if not sample_code or str(r.get("sample_code", "")).strip() == sample_code.strip():
                return int(r["id"]) if r.get("id") else None
    return None


def save_eqa_batch(metadata: Dict[str, Any], results: List[Dict[str, Any]], overwrite_batch_id: Optional[int] = None) -> int:
    init_database()
    ws_batches = get_ws("eqa_batches", BATCHES_HEADERS)
    ws_results = get_ws("eqa_results", RESULTS_HEADERS)

    if overwrite_batch_id is not None:
        delete_batch(overwrite_batch_id)

    batches_records = ws_batches.get_all_records()
    batch_id = max([int(r["id"]) for r in batches_records if str(r.get("id")).isdigit()], default=0) + 1

    total_tests = len(results)
    pass_count = sum(1 for r in results if r.get("eval_status") == "PASS")
    warn_count = sum(1 for r in results if r.get("eval_status") == "WARN")
    fail_count = sum(1 for r in results if r.get("eval_status") == "FAIL")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    batch_row = [
        batch_id, metadata.get("batch_label", ""), metadata.get("batch_no", "01"), metadata.get("month_year", ""),
        metadata.get("program_name", "Sinh hóa"), metadata.get("program_code", "BC20C"), metadata.get("unit_code", ""),
        metadata.get("instrument_name", ""), metadata.get("sample_code", ""), metadata.get("provider_name", "VEQAS - TT Kiểm chuẩn XN TP.HCM"),
        metadata.get("source_filename", ""), total_tests, pass_count, warn_count, fail_count, now_str, metadata.get("notes", "")
    ]
    ws_batches.append_row(batch_row)

    results_records = ws_results.get_all_records()
    res_id = max([int(r["id"]) for r in results_records if str(r.get("id")).isdigit()], default=0)

    rows_to_append = []
    for item in results:
        res_id += 1
        row = [
            res_id, batch_id, item.get("test_code", ""), item.get("test_full_name", ""), item.get("unit", ""),
            item.get("lab_result", ""), item.get("assigned_value", ""), item.get("sigma_p", ""), item.get("z_score", ""),
            item.get("bias_abs", ""), item.get("bias_pct", ""), item.get("eval_status", "PASS"),
            item.get("all_n", ""), item.get("all_mean", ""), item.get("all_sd", ""), item.get("all_cv", ""), item.get("all_excluded", ""),
            item.get("method_name", ""), item.get("method_n", ""), item.get("method_mean", ""), item.get("method_sd", ""), item.get("method_cv", ""), item.get("method_excluded", ""),
            item.get("peer_name", ""), item.get("peer_n", ""), item.get("peer_mean", ""), item.get("peer_sd", ""), item.get("peer_cv", ""), item.get("peer_excluded", ""),
            item.get("page_no", "")
        ]
        row = ["" if x is None else x for x in row]
        rows_to_append.append(row)

    if rows_to_append:
        ws_results.append_rows(rows_to_append)

    clear_db_cache()
    return batch_id


def get_batch_by_id(batch_id: int) -> Optional[Dict[str, Any]]:
    for r in get_all_batches():
        if str(r.get("id")) == str(batch_id):
            return r
    return None


@st.cache_data(ttl=120, show_spinner=False)
def get_results_by_batch(batch_id: int) -> List[Dict[str, Any]]:
    ws = get_ws("eqa_results", RESULTS_HEADERS)
    records = ws.get_all_records()
    filtered = [r for r in records if str(r.get("batch_id", "")) == str(batch_id)]

    for r in filtered:
        for k, v in list(r.items()):
            if v == "":
                r[k] = None
            elif k in ["lab_result", "assigned_value", "bias_abs", "bias_pct", "sigma_p", "z_score", "peer_sd", "peer_cv"]:
                try:
                    r[k] = float(v)
                except Exception:
                    pass
    filtered.sort(key=lambda x: (x.get("page_no", 999), x.get("id", 0)))
    return filtered


@st.cache_data(ttl=120, show_spinner=False)
def get_all_results_joined() -> pd.DataFrame:
    batches = get_ws("eqa_batches", BATCHES_HEADERS).get_all_records()
    results = get_ws("eqa_results", RESULTS_HEADERS).get_all_records()

    df_b = pd.DataFrame(batches)
    df_r = pd.DataFrame(results)

    if df_b.empty or df_r.empty:
        return pd.DataFrame()

    df_b = df_b.rename(columns={"id": "batch_id"})
    df_r = df_r.rename(columns={"id": "result_id"})

    df = pd.merge(df_r, df_b, on="batch_id", how="inner")

    num_cols = ["lab_result", "assigned_value", "bias_abs", "bias_pct", "sigma_p", "z_score", "peer_sd", "peer_cv"]
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values(by=["month_year", "batch_no", "page_no"], ascending=[False, False, True])
    return df


def get_sigma_input_by_test(test_code: Optional[str] = None, instrument_name: Optional[str] = None) -> pd.DataFrame:
    df = get_all_results_joined()
    if df.empty:
        return df
    if test_code:
        df = df[df["test_code"].astype(str).str.upper() == str(test_code).strip().upper()]
    if instrument_name:
        df = df[df["instrument_name"].astype(str).str.lower() == str(instrument_name).strip().lower()]
    return df


def delete_batch(batch_id: int) -> bool:
    ws_b = get_ws("eqa_batches", BATCHES_HEADERS)
    ws_r = get_ws("eqa_results", RESULTS_HEADERS)

    b_records = ws_b.get_all_values()
    b_deleted = False
    if b_records:
        id_idx = b_records[0].index("id") if "id" in b_records[0] else 0
        for i in range(len(b_records) - 1, 0, -1):
            if str(b_records[i][id_idx]) == str(batch_id):
                ws_b.delete_rows(i + 1)
                b_deleted = True
                break

    r_records = ws_r.get_all_values()
    if r_records:
        r_batch_id_idx = r_records[0].index("batch_id") if "batch_id" in r_records[0] else 1
        rows_to_delete = []
        for i in range(len(r_records) - 1, 0, -1):
            if str(r_records[i][r_batch_id_idx]) == str(batch_id):
                rows_to_delete.append(i + 1)
        for row_idx in rows_to_delete:
            ws_r.delete_rows(row_idx)

    clear_db_cache()
    return b_deleted


# ==============================================================================
# CÁC HÀM LƯU & TRUY XUẤT BẢNG TỔNG HỢP %BIAS THEO MỨC NỒNG ĐỘ (eqa_bias_summary)
# ==============================================================================
def save_bias_summary_records(instrument_name: str, test_code: str, level_records: List[Dict[str, Any]]):
    """Lưu (hoặc ghi đè) kết quả %Bias đã chốt của 1 xét nghiệm theo từng mức nồng độ."""
    ws = get_ws("eqa_bias_summary", BIAS_SUMMARY_HEADERS)
    all_vals = ws.get_all_values()

    # Xóa các dòng cũ của cùng (instrument_name, test_code) nếu đã tồn tại
    if len(all_vals) > 1:
        headers = all_vals[0]
        inst_idx = headers.index("instrument_name") if "instrument_name" in headers else 1
        test_idx = headers.index("test_code") if "test_code" in headers else 2
        for i in range(len(all_vals) - 1, 0, -1):
            if (
                str(all_vals[i][inst_idx]).strip().lower() == instrument_name.strip().lower()
                and str(all_vals[i][test_idx]).strip().upper() == test_code.strip().upper()
            ):
                ws.delete_rows(i + 1)

    existing = ws.get_all_records()
    next_id = max([int(r["id"]) for r in existing if str(r.get("id")).isdigit()], default=0)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    rows_to_add = []
    for rec in level_records:
        next_id += 1
        rows_to_add.append([
            next_id,
            rec.get("instrument_name", instrument_name),
            rec.get("test_code", test_code),
            rec.get("unit", ""),
            rec.get("level_no", 1),
            rec.get("level_name", "Mức 1"),
            rec.get("mean_conc", 0.0),
            rec.get("n_batches", 0),
            rec.get("selected_batches", ""),
            rec.get("mean_abs_bias_pct", 0.0),
            rec.get("mean_signed_bias_pct", 0.0),
            rec.get("rms_bias_pct", 0.0),
            rec.get("chosen_bias_pct", 0.0),
            rec.get("formula_type", "mean_abs_bias"),
            now_str,
        ])

    if rows_to_add:
        ws.append_rows(rows_to_add)
    clear_db_cache()


@st.cache_data(ttl=120, show_spinner=False)
def get_all_bias_summaries() -> pd.DataFrame:
    """Lấy toàn bộ danh sách %Bias đã chốt của các xét nghiệm."""
    ws = get_ws("eqa_bias_summary", BIAS_SUMMARY_HEADERS)
    records = ws.get_all_records()
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    num_cols = ["mean_conc", "n_batches", "mean_abs_bias_pct", "mean_signed_bias_pct", "rms_bias_pct", "chosen_bias_pct"]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values(by=["instrument_name", "test_code", "level_no"], ascending=[True, True, True])


def delete_bias_summary_by_test(test_code: str, instrument_name: Optional[str] = None):
    """Xóa kết quả %Bias đã chốt của một xét nghiệm (có thể lọc kèm tên máy)."""
    ws = get_ws("eqa_bias_summary", BIAS_SUMMARY_HEADERS)
    all_vals = ws.get_all_values()
    if len(all_vals) > 1:
        headers = all_vals[0]
        inst_idx = headers.index("instrument_name") if "instrument_name" in headers else 1
        test_idx = headers.index("test_code") if "test_code" in headers else 2
        for i in range(len(all_vals) - 1, 0, -1):
            match_test = str(all_vals[i][test_idx]).strip().upper() == test_code.strip().upper()
            match_inst = (
                True
                if not instrument_name
                else str(all_vals[i][inst_idx]).strip().lower() == instrument_name.strip().lower()
            )
            if match_test and match_inst:
                ws.delete_rows(i + 1)
    clear_db_cache()
