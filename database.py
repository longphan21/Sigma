import re
import time
import gspread
import streamlit as st
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
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


def normalize_test_info(test_code: str, test_full_name: str = "") -> Tuple[str, str]:
    """Đồng nhất GOT -> AST và GPT -> ALT cho cả dữ liệu mới và dữ liệu đã lưu trong Google Sheets."""
    c_up = str(test_code or "").strip().upper()
    f_up = str(test_full_name or "").strip().upper()
    if c_up in ("GPT", "ALT", "ALAT") or "ALT (GPT)" in f_up or "ALANINE AMINOTRANSFERASE" in f_up:
        return "ALT", "Alanine Aminotransferase (ALT)"
    if c_up in ("GOT", "AST", "ASAT") or "AST (GOT)" in f_up or "ASPARTATE AMINOTRANSFERASE" in f_up:
        return "AST", "Aspartate Aminotransferase (AST)"
    return str(test_code or "").strip(), str(test_full_name or "").strip()


def parse_ym_tuple(ym_str: Any) -> Tuple[int, int]:
    """Chuyển chuỗi kỳ 'MM/YYYY' thành tuple (YYYY, MM) để sắp xếp và lọc đúng thứ tự thời gian qua các năm."""
    s = str(ym_str or "").strip()
    m = re.search(r"(\d{1,2})[-/](\d{4})", s)
    if m:
        return int(m.group(2)), int(m.group(1))
    m2 = re.search(r"(\d{4})[-/](\d{1,2})", s)
    if m2:
        return int(m2.group(1)), int(m2.group(2))
    return (0, 0)


def _normalize_quarter_str(raw_q: Any, updated_at: Any = "") -> str:
    """Chuẩn hóa nhãn Quý (VD: 'Quý 1/2026'). Nếu bản ghi cũ chưa ghi Quý thì tự suy luận từ ngày lưu."""
    s = str(raw_q or "").strip()
    if s.startswith("Quý "):
        return s
    m = re.search(r"(20\d{2})-(\d{2})", str(updated_at or ""))
    if m:
        yr = int(m.group(1))
        mo = int(m.group(2))
        q = (mo - 1) // 3 + 1
        return f"Quý {q}/{yr}"
    now = datetime.now()
    return f"Quý {(now.month - 1) // 3 + 1}/{now.year}"


def _retry_gspread(func, *args, **kwargs):
    """Tự động thử lại tối đa 4 lần nếu Google Sheets API bị quá tải tạm thời (429 / 500 / 503)."""
    delays = [1.2, 2.5, 4.5]
    for delay in delays:
        try:
            return func(*args, **kwargs)
        except gspread.exceptions.APIError as e:
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            err_str = str(e)
            if status_code in (429, 500, 502, 503) or "429" in err_str or "Quota" in err_str or "503" in err_str:
                time.sleep(delay)
            else:
                raise
    return func(*args, **kwargs)


@st.cache_resource(show_spinner=False)
def _get_cached_ws(name: str, headers_tuple: tuple):
    """Lấy và giữ kết nối Worksheet trong bộ nhớ đệm, tự động tạo mới với 5000 dòng nếu chưa có."""
    doc = _retry_gspread(get_spreadsheet)
    try:
        ws = _retry_gspread(doc.worksheet, name)
    except gspread.exceptions.WorksheetNotFound:
        ws = _retry_gspread(doc.add_worksheet, title=name, rows=5000, cols=max(len(headers_tuple), 20))
        _retry_gspread(ws.append_row, list(headers_tuple))
    return ws


def get_ws(name: str, headers: List[str]):
    """Lấy Worksheet trên Google Sheets an toàn, không gọi lại metadata nhiều lần."""
    return _get_cached_ws(name, tuple(headers))


def _ensure_ws_capacity(ws, additional_rows: int):
    """Tự động mở rộng số dòng của Sheet nếu tổng dữ liệu vượt quá giới hạn dòng hiện tại."""
    try:
        current_rows = ws.row_count
        if current_rows < additional_rows + 500:
            _retry_gspread(ws.add_rows, max(2000, additional_rows + 500))
    except Exception:
        pass


def _values_to_records(all_values: List[List[Any]], expected_headers: List[str]) -> List[Dict[str, Any]]:
    """Chuyển mảng 2 chiều từ get_all_values() sang danh sách Dict an toàn, tránh lỗi tràn/lệch cột."""
    if not all_values or len(all_values) < 2:
        return []
    raw_headers = [str(h).strip() for h in all_values[0]]
    headers = raw_headers if any(raw_headers) else expected_headers
    records: List[Dict[str, Any]] = []
    for row in all_values[1:]:
        if not any(str(cell).strip() for cell in row):
            continue
        rec: Dict[str, Any] = {}
        for idx, h in enumerate(headers):
            if not h:
                continue
            rec[h] = row[idx] if idx < len(row) else ""
        records.append(rec)
    return records


def clear_db_cache():
    """Xóa bộ nhớ đệm dữ liệu mỗi khi có thao tác Lưu hoặc Xóa."""
    st.cache_data.clear()


@st.cache_resource(show_spinner=False)
def init_database():
    """Khởi tạo 3 trang tính trên Google Sheets đúng 1 lần khi mở ứng dụng."""
    get_ws("eqa_batches", BATCHES_HEADERS)
    get_ws("eqa_results", RESULTS_HEADERS)
    get_ws("eqa_bias_summary", BIAS_SUMMARY_HEADERS)
    return True


@st.cache_data(ttl=300, show_spinner=False)
def get_all_batches() -> List[Dict[str, Any]]:
    ws = get_ws("eqa_batches", BATCHES_HEADERS)
    all_vals = _retry_gspread(ws.get_all_values)
    records = _values_to_records(all_vals, BATCHES_HEADERS)
    records.sort(
        key=lambda x: (
            parse_ym_tuple(x.get("month_year", "")),
            str(x.get("batch_no", "")),
            int(x.get("id", 0) or 0),
        ),
        reverse=True,
    )
    return records


@st.cache_data(ttl=300, show_spinner=False)
def _get_all_results_raw() -> List[Dict[str, Any]]:
    """Đọc toàn bộ bảng eqa_results đúng 1 lần vào bộ nhớ đệm và tự động gộp GOT/GPT thành AST/ALT."""
    ws = get_ws("eqa_results", RESULTS_HEADERS)
    all_vals = _retry_gspread(ws.get_all_values)
    records = _values_to_records(all_vals, RESULTS_HEADERS)
    for r in records:
        norm_code, norm_name = normalize_test_info(r.get("test_code", ""), r.get("test_full_name", ""))
        r["test_code"] = norm_code
        r["test_full_name"] = norm_name
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
                return int(r["id"]) if str(r.get("id", "")).isdigit() else None
    return None


def save_eqa_batch(metadata: Dict[str, Any], results: List[Dict[str, Any]], overwrite_batch_id: Optional[int] = None) -> int:
    init_database()
    ws_batches = get_ws("eqa_batches", BATCHES_HEADERS)
    ws_results = get_ws("eqa_results", RESULTS_HEADERS)

    if overwrite_batch_id is not None:
        delete_batch(overwrite_batch_id)

    batches_records = get_all_batches()
    batch_id = max([int(r["id"]) for r in batches_records if str(r.get("id", "")).isdigit()], default=0) + 1

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
    _retry_gspread(ws_batches.append_row, batch_row)

    results_records = _get_all_results_raw()
    res_id = max([int(r["id"]) for r in results_records if str(r.get("id", "")).isdigit()], default=0)

    rows_to_append = []
    for item in results:
        res_id += 1
        norm_code, norm_name = normalize_test_info(item.get("test_code", ""), item.get("test_full_name", ""))
        row = [
            res_id, batch_id, norm_code, norm_name, item.get("unit", ""),
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
        _ensure_ws_capacity(ws_results, len(results_records) + len(rows_to_append) + 10)
        _retry_gspread(ws_results.append_rows, rows_to_append)

    clear_db_cache()
    return batch_id


def get_batch_by_id(batch_id: int) -> Optional[Dict[str, Any]]:
    for r in get_all_batches():
        if str(r.get("id")) == str(batch_id):
            return r
    return None


@st.cache_data(ttl=300, show_spinner=False)
def get_results_by_batch(batch_id: int) -> List[Dict[str, Any]]:
    records = _get_all_results_raw()
    filtered = [dict(r) for r in records if str(r.get("batch_id", "")) == str(batch_id)]

    for r in filtered:
        for k, v in list(r.items()):
            if v == "":
                r[k] = None
            elif k in ["lab_result", "assigned_value", "bias_abs", "bias_pct", "sigma_p", "z_score", "peer_sd", "peer_cv"]:
                try:
                    r[k] = float(v)
                except Exception:
                    pass
    filtered.sort(key=lambda x: (int(x.get("page_no") or 999), int(x.get("id") or 0)))
    return filtered


@st.cache_data(ttl=300, show_spinner=False)
def get_all_results_joined() -> pd.DataFrame:
    batches = get_all_batches()
    results = _get_all_results_raw()

    df_b = pd.DataFrame(batches)
    df_r = pd.DataFrame(results)

    if df_b.empty or df_r.empty:
        return pd.DataFrame()

    df_b = df_b.rename(columns={"id": "batch_id"})
    df_r = df_r.rename(columns={"id": "result_id"})

    df_b["batch_id"] = df_b["batch_id"].astype(str)
    df_r["batch_id"] = df_r["batch_id"].astype(str)

    df = pd.merge(df_r, df_b, on="batch_id", how="inner")

    num_cols = ["lab_result", "assigned_value", "bias_abs", "bias_pct", "sigma_p", "z_score", "peer_sd", "peer_cv"]
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    ym_tuples = df["month_year"].apply(parse_ym_tuple)
    df["_ym_year"] = [t[0] for t in ym_tuples]
    df["_ym_month"] = [t[1] for t in ym_tuples]
    df = df.sort_values(by=["_ym_year", "_ym_month", "batch_no", "page_no"], ascending=[False, False, False, True])
    return df.drop(columns=["_ym_year", "_ym_month"]).reset_index(drop=True)


def get_sigma_input_by_test(test_code: Optional[str] = None, instrument_name: Optional[str] = None) -> pd.DataFrame:
    df = get_all_results_joined()
    if df.empty:
        return df
    if test_code:
        norm_c, _ = normalize_test_info(test_code, "")
        df = df[df["test_code"].astype(str).str.upper() == norm_c.upper()]
    if instrument_name:
        df = df[df["instrument_name"].astype(str).str.lower() == str(instrument_name).strip().lower()]
    return df


def delete_batch(batch_id: int) -> bool:
    ws_b = get_ws("eqa_batches", BATCHES_HEADERS)
    ws_r = get_ws("eqa_results", RESULTS_HEADERS)

    b_records = _retry_gspread(ws_b.get_all_values)
    b_deleted = False
    if b_records:
        id_idx = b_records[0].index("id") if "id" in b_records[0] else 0
        for i in range(len(b_records) - 1, 0, -1):
            if str(b_records[i][id_idx]) == str(batch_id):
                _retry_gspread(ws_b.delete_rows, i + 1)
                b_deleted = True
                break

    r_records = _retry_gspread(ws_r.get_all_values)
    if r_records:
        r_batch_id_idx = r_records[0].index("batch_id") if "batch_id" in r_records[0] else 1
        rows_to_delete = [
            i + 1 for i in range(len(r_records) - 1, 0, -1)
            if str(r_records[i][r_batch_id_idx]) == str(batch_id)
        ]
        if rows_to_delete:
            min_r, max_r = min(rows_to_delete), max(rows_to_delete)
            if max_r - min_r + 1 == len(rows_to_delete):
                _retry_gspread(ws_r.delete_rows, min_r, max_r)
            else:
                for row_idx in rows_to_delete:
                    _retry_gspread(ws_r.delete_rows, row_idx)

    clear_db_cache()
    return b_deleted


# ==============================================================================
# CÁC HÀM LƯU & TRUY XUẤT BẢNG TỔNG HỢP %BIAS THEO QUÝ & MỨC NỒNG ĐỘ
# ==============================================================================
def save_bias_summary_records(
    instrument_name: str,
    test_code: str,
    level_records: List[Dict[str, Any]],
    quarter_period: str = "Quý 1/2026",
):
    """Lưu (hoặc ghi đè) kết quả %Bias đã chốt của 1 xét nghiệm theo từng Quý (Quý 1, Quý 2, Quý 3, Quý 4)."""
    ws = get_ws("eqa_bias_summary", BIAS_SUMMARY_HEADERS)
    all_vals = _retry_gspread(ws.get_all_values)
    norm_code, _ = normalize_test_info(test_code, "")
    q_clean = quarter_period.strip()

    if len(all_vals) > 1:
        headers = all_vals[0]
        inst_idx = headers.index("instrument_name") if "instrument_name" in headers else 1
        test_idx = headers.index("test_code") if "test_code" in headers else 2
        q_idx = headers.index("formula_type") if "formula_type" in headers else 13
        upd_idx = headers.index("updated_at") if "updated_at" in headers else 14

        rows_to_del = []
        for i in range(len(all_vals) - 1, 0, -1):
            row_i = all_vals[i]
            r_inst = str(row_i[inst_idx]).strip().lower() if inst_idx < len(row_i) else ""
            r_test, _ = normalize_test_info(row_i[test_idx] if test_idx < len(row_i) else "", "")
            r_q_raw = row_i[q_idx] if q_idx < len(row_i) else ""
            r_upd = row_i[upd_idx] if upd_idx < len(row_i) else ""
            r_q = _normalize_quarter_str(r_q_raw, r_upd)

            if (
                r_inst == instrument_name.strip().lower()
                and r_test.upper() == norm_code.upper()
                and r_q.lower() == q_clean.lower()
            ):
                rows_to_del.append(i + 1)

        if rows_to_del:
            min_r, max_r = min(rows_to_del), max(rows_to_del)
            if max_r - min_r + 1 == len(rows_to_del):
                _retry_gspread(ws.delete_rows, min_r, max_r)
            else:
                for r_idx in rows_to_del:
                    _retry_gspread(ws.delete_rows, r_idx)

    after_vals = _retry_gspread(ws.get_all_values)
    existing = _values_to_records(after_vals, BIAS_SUMMARY_HEADERS)
    next_id = max([int(r["id"]) for r in existing if str(r.get("id", "")).isdigit()], default=0)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    rows_to_add = []
    for rec in level_records:
        next_id += 1
        rows_to_add.append([
            next_id,
            rec.get("instrument_name", instrument_name),
            norm_code,
            rec.get("unit", ""),
            rec.get("level_no", 1),
            rec.get("level_name", "Mức 1 (LOW)"),
            round(float(rec.get("mean_conc", 0.0) or 0.0), 3),
            int(rec.get("n_batches", 0) or 0),
            rec.get("selected_batches", ""),
            round(float(rec.get("mean_abs_bias_pct", 0.0) or 0.0), 3),
            round(float(rec.get("mean_signed_bias_pct", 0.0) or 0.0), 3),
            round(float(rec.get("rms_bias_pct", 0.0) or 0.0), 3),
            round(float(rec.get("chosen_bias_pct", 0.0) or 0.0), 3),
            q_clean,
            now_str,
        ])

    if rows_to_add:
        _ensure_ws_capacity(ws, len(existing) + len(rows_to_add) + 10)
        _retry_gspread(ws.append_rows, rows_to_add)
    clear_db_cache()


@st.cache_data(ttl=300, show_spinner=False)
def get_all_bias_summaries() -> pd.DataFrame:
    """Lấy toàn bộ danh sách %Bias đã chốt của các xét nghiệm kèm cột quarter_period."""
    ws = get_ws("eqa_bias_summary", BIAS_SUMMARY_HEADERS)
    all_vals = _retry_gspread(ws.get_all_values)
    records = _values_to_records(all_vals, BIAS_SUMMARY_HEADERS)
    if not records:
        return pd.DataFrame()

    for r in records:
        norm_c, _ = normalize_test_info(r.get("test_code", ""), "")
        r["test_code"] = norm_c
        r["quarter_period"] = _normalize_quarter_str(r.get("formula_type", ""), r.get("updated_at", ""))

    df = pd.DataFrame(records)
    num_cols = ["level_no", "mean_conc", "n_batches", "mean_abs_bias_pct", "mean_signed_bias_pct", "rms_bias_pct", "chosen_bias_pct"]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values(by=["quarter_period", "instrument_name", "test_code", "level_no"], ascending=[True, True, True, True]).reset_index(drop=True)


def delete_bias_summary_by_test(
    test_code: str,
    instrument_name: Optional[str] = None,
    quarter_period: Optional[str] = None,
):
    """Xóa kết quả %Bias đã chốt của một xét nghiệm theo đúng Dòng máy và Quý."""
    ws = get_ws("eqa_bias_summary", BIAS_SUMMARY_HEADERS)
    all_vals = _retry_gspread(ws.get_all_values)
    norm_code, _ = normalize_test_info(test_code, "")

    if len(all_vals) > 1:
        headers = all_vals[0]
        inst_idx = headers.index("instrument_name") if "instrument_name" in headers else 1
        test_idx = headers.index("test_code") if "test_code" in headers else 2
        q_idx = headers.index("formula_type") if "formula_type" in headers else 13
        upd_idx = headers.index("updated_at") if "updated_at" in headers else 14

        for i in range(len(all_vals) - 1, 0, -1):
            row_i = all_vals[i]
            r_test, _ = normalize_test_info(row_i[test_idx] if test_idx < len(row_i) else "", "")
            match_test = r_test.upper() == norm_code.upper()
            match_inst = (
                True
                if not instrument_name
                else str(row_i[inst_idx]).strip().lower() == instrument_name.strip().lower()
            )
            r_q = _normalize_quarter_str(
                row_i[q_idx] if q_idx < len(row_i) else "",
                row_i[upd_idx] if upd_idx < len(row_i) else "",
            )
            match_q = (
                True
                if not quarter_period
                else r_q.lower() == quarter_period.strip().lower()
            )
            if match_test and match_inst and match_q:
                _retry_gspread(ws.delete_rows, i + 1)
    clear_db_cache()
