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

TEA_HEADERS = [
    "id", "instrument_name", "test_code", "test_full_name", "unit",
    "tea_source", "tea_pct", "is_default", "notes", "updated_at"
]

IQC_LOTS_HEADERS = [
    "id", "instrument_name", "test_code", "test_full_name", "unit",
    "level_no", "level_name", "lot_no", "start_date", "cutoff_date",
    "lot_status", "mean_val", "sd_val", "cv_pct", "n_points", "notes", "updated_at"
]
CV_SUMMARY_HEADERS = [
    "id", "quarter_period", "instrument_name", "test_code", "unit",
    "level_no", "level_name", "n_lots", "selected_lots", "total_points",
    "pooled_mean", "chosen_cv_pct", "updated_at"
]

SIGMA_SUMMARY_HEADERS = [
    "id", "quarter_period", "instrument_name", "test_code", "test_full_name", "unit",
    "level_no", "level_name", "tea_source", "tea_pct", "bias_pct", "cv_pct",
    "sigma_val", "sigma_grade", "westgard_rules", "qc_freq_note", "updated_at"
]

def normalize_test_info(test_code: str, test_full_name: str = "") -> Tuple[str, str]:
    """Unify GOT -> AST and GPT -> ALT across both new and existing records."""
    c_up = str(test_code or "").strip().upper()
    f_up = str(test_full_name or "").strip().upper()
    if c_up in ("GPT", "ALT", "ALAT") or "ALT (GPT)" in f_up or "ALANINE AMINOTRANSFERASE" in f_up:
        return "ALT", "Alanine Aminotransferase (ALT)"
    if c_up in ("GOT", "AST", "ASAT") or "AST (GOT)" in f_up or "ASPARTATE AMINOTRANSFERASE" in f_up:
        return "AST", "Aspartate Aminotransferase (AST)"
    return str(test_code or "").strip(), str(test_full_name or "").strip()


def parse_ym_tuple(ym_str: Any) -> Tuple[int, int]:
    """Convert 'MM/YYYY' into (YYYY, MM) for chronological sorting and filtering."""
    s = str(ym_str or "").strip()
    m = re.search(r"(\d{1,2})[-/](\d{4})", s)
    if m:
        return int(m.group(2)), int(m.group(1))
    m2 = re.search(r"(\d{4})[-/](\d{1,2})", s)
    if m2:
        return int(m2.group(1)), int(m2.group(2))
    return (0, 0)


def _normalize_quarter_str(raw_q: Any, updated_at: Any = "") -> str:
    """Normalize quarter label to 'Q1/2026' format (compatible with 'Quý 1/2026')."""
    s = str(raw_q or "").strip()
    m_q = re.match(r"^(?:Quý|Quy|Q)\s*([1-4])\s*/\s*(\d{4})$", s, re.IGNORECASE)
    if m_q:
        return f"Q{m_q.group(1)}/{m_q.group(2)}"
    m = re.search(r"(20\d{2})-(\d{2})", str(updated_at or ""))
    if m:
        yr = int(m.group(1))
        mo = int(m.group(2))
        q = (mo - 1) // 3 + 1
        return f"Q{q}/{yr}"
    now = datetime.now()
    return f"Q{(now.month - 1) // 3 + 1}/{now.year}"


def _retry_gspread(func, *args, **kwargs):
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
    doc = _retry_gspread(get_spreadsheet)
    try:
        ws = _retry_gspread(doc.worksheet, name)
    except gspread.exceptions.WorksheetNotFound:
        ws = _retry_gspread(doc.add_worksheet, title=name, rows=5000, cols=max(len(headers_tuple), 20))
        _retry_gspread(ws.append_row, list(headers_tuple))
    return ws


def get_ws(name: str, headers: List[str]):
    return _get_cached_ws(name, tuple(headers))


def _ensure_ws_capacity(ws, additional_rows: int):
    try:
        current_rows = ws.row_count
        if current_rows < additional_rows + 500:
            _retry_gspread(ws.add_rows, max(2000, additional_rows + 500))
    except Exception:
        pass


def _values_to_records(all_values: List[List[Any]], expected_headers: List[str]) -> List[Dict[str, Any]]:
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
    st.cache_data.clear()


@st.cache_resource(show_spinner=False)
def init_database():
    get_ws("eqa_batches", BATCHES_HEADERS)
    get_ws("eqa_results", RESULTS_HEADERS)
    get_ws("eqa_bias_summary", BIAS_SUMMARY_HEADERS)
    get_ws("tea_standards", TEA_HEADERS)
    get_ws("iqc_lots", IQC_LOTS_HEADERS)
    get_ws("iqc_cv_summary", CV_SUMMARY_HEADERS)
    get_ws("sigma_summary", SIGMA_SUMMARY_HEADERS)
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
        metadata.get("program_name", "Biochemistry"), metadata.get("program_code", "BC20C"), metadata.get("unit_code", ""),
        metadata.get("instrument_name", ""), metadata.get("sample_code", ""), metadata.get("provider_name", "VEQAS"),
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
# QUARTERLY BIAS SUMMARY STORAGE (eqa_bias_summary)
# ==============================================================================
def save_bias_summary_records(
    instrument_name: str,
    test_code: str,
    level_records: List[Dict[str, Any]],
    quarter_period: str = "Q1/2026",
):
    ws = get_ws("eqa_bias_summary", BIAS_SUMMARY_HEADERS)
    all_vals = _retry_gspread(ws.get_all_values)
    norm_code, _ = normalize_test_info(test_code, "")
    q_clean = _normalize_quarter_str(quarter_period)

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
            rec.get("level_name", "Level 1 (LOW)"),
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
    ws = get_ws("eqa_bias_summary", BIAS_SUMMARY_HEADERS)
    all_vals = _retry_gspread(ws.get_all_values)
    records = _values_to_records(all_vals, BIAS_SUMMARY_HEADERS)
    if not records:
        return pd.DataFrame()

    for r in records:
        norm_c, _ = normalize_test_info(r.get("test_code", ""), "")
        r["test_code"] = norm_c
        r["quarter_period"] = _normalize_quarter_str(r.get("formula_type", ""), r.get("updated_at", ""))
        lv_str = str(r.get("level_name", "")).strip()
        if lv_str.startswith("Mức "):
            r["level_name"] = lv_str.replace("Mức ", "Level ").replace("Chung", "General")

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
    ws = get_ws("eqa_bias_summary", BIAS_SUMMARY_HEADERS)
    all_vals = _retry_gspread(ws.get_all_values)
    norm_code, _ = normalize_test_info(test_code, "")
    target_q = _normalize_quarter_str(quarter_period) if quarter_period else None

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
            match_q = True if not target_q else r_q.lower() == target_q.lower()
            if match_test and match_inst and match_q:
                _retry_gspread(ws.delete_rows, i + 1)
    clear_db_cache()

# ==============================================================================
# TEA STANDARDS STORAGE (tea_standards)
# ==============================================================================
@st.cache_data(ttl=300, show_spinner=False)
def get_all_tea_standards() -> pd.DataFrame:
    ws = get_ws("tea_standards", TEA_HEADERS)
    all_vals = _retry_gspread(ws.get_all_values)
    records = _values_to_records(all_vals, TEA_HEADERS)
    if not records:
        return pd.DataFrame(columns=TEA_HEADERS)

    for r in records:
        r["instrument_name"] = str(r.get("instrument_name", "") or "").strip()
        norm_c, norm_n = normalize_test_info(r.get("test_code", ""), r.get("test_full_name", ""))
        r["test_code"] = norm_c
        r["test_full_name"] = norm_n or norm_c
        r["is_default"] = str(r.get("is_default", "")).strip().upper() in ("TRUE", "1", "YES")

    df = pd.DataFrame(records)
    for col in TEA_HEADERS:
        if col not in df.columns:
            df[col] = ""
    df["id"] = pd.to_numeric(df["id"], errors="coerce").fillna(0).astype(int)
    df["tea_pct"] = pd.to_numeric(df["tea_pct"], errors="coerce")
    return df[TEA_HEADERS].sort_values(
        by=["instrument_name", "test_code", "is_default", "tea_source"],
        ascending=[True, True, False, True],
    ).reset_index(drop=True)


def save_tea_standard(
    instrument_name: str,
    test_code: str,
    test_full_name: str,
    unit: str,
    tea_source: str,
    tea_pct: float,
    is_default: bool = True,
    notes: str = "",
):
    ws = get_ws("tea_standards", TEA_HEADERS)
    all_vals = _retry_gspread(ws.get_all_values)
    existing = _values_to_records(all_vals, TEA_HEADERS)

    clean_inst = str(instrument_name).strip()
    norm_code, norm_name = normalize_test_info(test_code, test_full_name)
    norm_name = norm_name or norm_code
    clean_source = str(tea_source).strip()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    same_inst_test_rows = [
        r for r in existing
        if str(r.get("instrument_name", "")).strip().lower() == clean_inst.lower()
        and normalize_test_info(r.get("test_code", ""), "")[0].upper() == norm_code.upper()
    ]
    if not same_inst_test_rows:
        is_default = True

    updated_existing = False
    max_id = max([int(r["id"]) for r in existing if str(r.get("id", "")).isdigit()], default=0)

    new_rows = [TEA_HEADERS]
    for r in existing:
        r_id = int(r["id"]) if str(r.get("id", "")).isdigit() else 0
        r_inst = str(r.get("instrument_name", "")).strip()
        r_code, r_name = normalize_test_info(r.get("test_code", ""), r.get("test_full_name", ""))
        r_source = str(r.get("tea_source", "")).strip()
        r_def = str(r.get("is_default", "")).strip().upper() in ("TRUE", "1", "YES")

        same_target = (
            r_inst.lower() == clean_inst.lower()
            and r_code.upper() == norm_code.upper()
        )

        if same_target and r_source.lower() == clean_source.lower():
            updated_existing = True
            new_rows.append([
                r_id,
                clean_inst,
                norm_code,
                norm_name or r_name,
                str(unit).strip() or r.get("unit", ""),
                clean_source,
                round(float(tea_pct), 3),
                "TRUE" if is_default else "FALSE",
                str(notes).strip(),
                now_str,
            ])
        else:
            if same_target and is_default:
                r_def = False
            new_rows.append([
                r_id,
                r_inst,
                r_code,
                r_name or r_code,
                r.get("unit", ""),
                r_source,
                round(float(r.get("tea_pct", 0.0) or 0.0), 3),
                "TRUE" if r_def else "FALSE",
                r.get("notes", ""),
                r.get("updated_at", now_str),
            ])

    if not updated_existing:
        max_id += 1
        new_rows.append([
            max_id,
            clean_inst,
            norm_code,
            norm_name,
            str(unit).strip(),
            clean_source,
            round(float(tea_pct), 3),
            "TRUE" if is_default else "FALSE",
            str(notes).strip(),
            now_str,
        ])

    _retry_gspread(ws.clear)
    _ensure_ws_capacity(ws, len(new_rows) + 10)
    _retry_gspread(ws.append_rows, new_rows)
    clear_db_cache()


def update_tea_standards_bulk(df_edited: pd.DataFrame):
    ws = get_ws("tea_standards", TEA_HEADERS)
    all_vals = _retry_gspread(ws.get_all_values)
    existing = _values_to_records(all_vals, TEA_HEADERS)
    if not existing or df_edited.empty:
        return

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    edit_map: Dict[int, Dict[str, Any]] = {}
    default_chosen_by_inst_test: Dict[Tuple[str, str], int] = {}

    for _, row in df_edited.iterrows():
        rid = int(row["id"])
        inst_key = str(row.get("instrument_name", "") or "").strip().lower()
        t_code = str(row["test_code"]).strip().upper()
        is_def = bool(row.get("is_default", False))
        edit_map[rid] = {
            "instrument_name": str(row.get("instrument_name", "") or "").strip(),
            "unit": str(row.get("unit", "") or "").strip(),
            "tea_source": str(row.get("tea_source", "") or "").strip(),
            "tea_pct": round(float(row.get("tea_pct", 0.0) or 0.0), 3),
            "is_default": is_def,
            "notes": str(row.get("notes", "") or "").strip(),
        }
        pair_key = (inst_key, t_code)
        if is_def and pair_key not in default_chosen_by_inst_test:
            default_chosen_by_inst_test[pair_key] = rid

    new_rows = [TEA_HEADERS]
    for r in existing:
        rid = int(r["id"]) if str(r.get("id", "")).isdigit() else 0
        r_inst = str(r.get("instrument_name", "") or "").strip()
        r_code, r_name = normalize_test_info(r.get("test_code", ""), r.get("test_full_name", ""))
        pair_key = (r_inst.lower(), r_code.upper())

        if rid in edit_map:
            ed = edit_map[rid]
            pair_key_ed = (ed["instrument_name"].lower(), r_code.upper())
            final_def = (
                (default_chosen_by_inst_test.get(pair_key_ed) == rid)
                if pair_key_ed in default_chosen_by_inst_test
                else ed["is_default"]
            )
            new_rows.append([
                rid,
                ed["instrument_name"],
                r_code,
                r_name or r_code,
                ed["unit"],
                ed["tea_source"],
                ed["tea_pct"],
                "TRUE" if final_def else "FALSE",
                ed["notes"],
                now_str,
            ])
        else:
            orig_def = str(r.get("is_default", "")).strip().upper() in ("TRUE", "1", "YES")
            if pair_key in default_chosen_by_inst_test:
                orig_def = False
            new_rows.append([
                rid,
                r_inst,
                r_code,
                r_name or r_code,
                r.get("unit", ""),
                r.get("tea_source", ""),
                round(float(r.get("tea_pct", 0.0) or 0.0), 3),
                "TRUE" if orig_def else "FALSE",
                r.get("notes", ""),
                r.get("updated_at", now_str),
            ])

    _retry_gspread(ws.clear)
    _ensure_ws_capacity(ws, len(new_rows) + 10)
    _retry_gspread(ws.append_rows, new_rows)
    clear_db_cache()

def delete_tea_standard(record_id: int):
    ws = get_ws("tea_standards", TEA_HEADERS)
    all_vals = _retry_gspread(ws.get_all_values)
    if len(all_vals) > 1:
        id_idx = all_vals[0].index("id") if "id" in all_vals[0] else 0
        for i in range(len(all_vals) - 1, 0, -1):
            if str(all_vals[i][id_idx]).strip() == str(record_id).strip():
                _retry_gspread(ws.delete_rows, i + 1)
                break
    clear_db_cache()

# ==============================================================================
# IQC LOTS & CUMULATIVE CV SUMMARY STORAGE (iqc_lots, iqc_cv_summary)
# ==============================================================================
def _ensure_ws_headers(ws, expected_headers: List[str]) -> List[List[Any]]:
    """Đảm bảo dòng 1 của Sheet luôn là expected_headers; tự động chèn lại nếu bị mất header."""
    all_vals = _retry_gspread(ws.get_all_values)
    if not all_vals:
        _retry_gspread(ws.append_row, list(expected_headers))
        return [list(expected_headers)]

    first_row = [str(c).strip() for c in all_vals[0]]
    if not any(first_row):
        _retry_gspread(ws.delete_rows, 1)
        return _ensure_ws_headers(ws, expected_headers)

    # Nếu dòng 1 là dữ liệu (cột đầu tiên không phải 'id') do mất dòng tiêu đề trước đó
    if first_row[0].lower() != "id":
        _retry_gspread(ws.insert_row, list(expected_headers), 1)
        all_vals.insert(0, list(expected_headers))
        return all_vals

    # Nếu dòng 1 là tiêu đề cũ nhưng khác số cột hiện tại
    if first_row != expected_headers:
        _retry_gspread(ws.insert_row, list(expected_headers), 1)
        _retry_gspread(ws.delete_rows, 2)
        all_vals[0] = list(expected_headers)

    return all_vals

@st.cache_data(ttl=300, show_spinner=False)
def get_all_iqc_lots() -> pd.DataFrame:
    ws = get_ws("iqc_lots", IQC_LOTS_HEADERS)
    all_vals = _ensure_ws_headers(ws, IQC_LOTS_HEADERS)
    records = _values_to_records(all_vals, IQC_LOTS_HEADERS)
    if not records:
        return pd.DataFrame(columns=IQC_LOTS_HEADERS)

    for r in records:
        norm_c, norm_n = normalize_test_info(r.get("test_code", ""), r.get("test_full_name", ""))
        r["test_code"] = norm_c
        r["test_full_name"] = norm_n or norm_c

    df = pd.DataFrame(records)
    for col in IQC_LOTS_HEADERS:
        if col not in df.columns:
            df[col] = ""

    num_cols = ["id", "level_no", "mean_val", "sd_val", "cv_pct", "n_points"]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["id"] = df["id"].fillna(0).astype(int)
    df["level_no"] = df["level_no"].fillna(1).astype(int)
    return df[IQC_LOTS_HEADERS].sort_values(
        by=["instrument_name", "test_code", "level_no", "id"],
        ascending=[True, True, True, False],
    ).reset_index(drop=True)

def save_iqc_lot(
    instrument_name: str,
    test_code: str,
    test_full_name: str,
    unit: str,
    level_no: int,
    level_name: str,
    lot_no: str,
    start_date: str,
    cutoff_date: str,
    lot_status: str,
    mean_val: Optional[float],
    sd_val: Optional[float],
    cv_pct: float,
    n_points: Optional[int],
    notes: str = "",
):
    ws = get_ws("iqc_lots", IQC_LOTS_HEADERS)
    all_vals = _ensure_ws_headers(ws, IQC_LOTS_HEADERS)
    norm_code, norm_name = normalize_test_info(test_code, test_full_name)
    norm_name = norm_name or norm_code
    clean_inst = str(instrument_name).strip()
    clean_lot = str(lot_no).strip()
    lv_int = int(level_no)

    if len(all_vals) > 1:
        headers = all_vals[0]
        inst_idx = headers.index("instrument_name") if "instrument_name" in headers else 1
        test_idx = headers.index("test_code") if "test_code" in headers else 2
        lv_idx = headers.index("level_no") if "level_no" in headers else 5
        lot_idx = headers.index("lot_no") if "lot_no" in headers else 7

        for i in range(len(all_vals) - 1, 0, -1):
            row_i = all_vals[i]
            r_inst = str(row_i[inst_idx]).strip().lower() if inst_idx < len(row_i) else ""
            r_test, _ = normalize_test_info(row_i[test_idx] if test_idx < len(row_i) else "", "")
            r_lv = int(float(row_i[lv_idx] or 1)) if lv_idx < len(row_i) and str(row_i[lv_idx]).strip() else 1
            r_lot = str(row_i[lot_idx]).strip().lower() if lot_idx < len(row_i) else ""

            if (
                r_inst == clean_inst.lower()
                and r_test.upper() == norm_code.upper()
                and r_lv == lv_int
                and r_lot == clean_lot.lower()
            ):
                _retry_gspread(ws.delete_rows, i + 1)

    after_vals = _ensure_ws_headers(ws, IQC_LOTS_HEADERS)
    existing = _values_to_records(after_vals, IQC_LOTS_HEADERS)
    next_id = max([int(r["id"]) for r in existing if str(r.get("id", "")).isdigit()], default=0) + 1
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    mean_cell = "" if mean_val is None else round(float(mean_val), 3)
    sd_cell = "" if sd_val is None else round(float(sd_val), 4)
    n_cell = "" if n_points is None else int(n_points)

    new_row = [
        next_id,
        clean_inst,
        norm_code,
        norm_name,
        str(unit).strip(),
        lv_int,
        level_name,
        clean_lot,
        str(start_date).strip(),
        str(cutoff_date).strip(),
        str(lot_status).strip(),
        mean_cell,
        sd_cell,
        round(float(cv_pct), 3),
        n_cell,
        str(notes).strip(),
        now_str,
    ]
    _ensure_ws_capacity(ws, len(existing) + 10)
    _retry_gspread(ws.append_row, new_row)
    clear_db_cache()

def delete_iqc_lot(record_id: int):
    ws = get_ws("iqc_lots", IQC_LOTS_HEADERS)
    all_vals = _retry_gspread(ws.get_all_values)
    if len(all_vals) > 1:
        id_idx = all_vals[0].index("id") if "id" in all_vals[0] else 0
        for i in range(len(all_vals) - 1, 0, -1):
            if str(all_vals[i][id_idx]).strip() == str(record_id).strip():
                _retry_gspread(ws.delete_rows, i + 1)
                break
    clear_db_cache()


def save_cv_summary_records(
    instrument_name: str,
    test_code: str,
    level_records: List[Dict[str, Any]],
    quarter_period: str = "Q1/2026",
):
    ws = get_ws("iqc_cv_summary", CV_SUMMARY_HEADERS)
    all_vals = _retry_gspread(ws.get_all_values)
    norm_code, _ = normalize_test_info(test_code, "")
    q_clean = _normalize_quarter_str(quarter_period)

    if len(all_vals) > 1:
        headers = all_vals[0]
        q_idx = headers.index("quarter_period") if "quarter_period" in headers else 1
        inst_idx = headers.index("instrument_name") if "instrument_name" in headers else 2
        test_idx = headers.index("test_code") if "test_code" in headers else 3
        upd_idx = headers.index("updated_at") if "updated_at" in headers else 12

        rows_to_del = []
        for i in range(len(all_vals) - 1, 0, -1):
            row_i = all_vals[i]
            r_inst = str(row_i[inst_idx]).strip().lower() if inst_idx < len(row_i) else ""
            r_test, _ = normalize_test_info(row_i[test_idx] if test_idx < len(row_i) else "", "")
            r_q = _normalize_quarter_str(
                row_i[q_idx] if q_idx < len(row_i) else "",
                row_i[upd_idx] if upd_idx < len(row_i) else "",
            )
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
    existing = _values_to_records(after_vals, CV_SUMMARY_HEADERS)
    next_id = max([int(r["id"]) for r in existing if str(r.get("id", "")).isdigit()], default=0)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    rows_to_add = []
    for rec in level_records:
        next_id += 1
        tot_pts = rec.get("total_points")
        p_mean = rec.get("pooled_mean")
        rows_to_add.append([
            next_id,
            q_clean,
            rec.get("instrument_name", instrument_name),
            norm_code,
            rec.get("unit", ""),
            int(rec.get("level_no", 1) or 1),
            rec.get("level_name", "Level 1 (LOW)"),
            int(rec.get("n_lots", 0) or 0),
            rec.get("selected_lots", ""),
            "" if tot_pts is None else int(tot_pts),
            "" if p_mean is None else round(float(p_mean), 3),
            round(float(rec.get("chosen_cv_pct", 0.0) or 0.0), 3),
            now_str,
        ])

    if rows_to_add:
        _ensure_ws_capacity(ws, len(existing) + len(rows_to_add) + 10)
        _retry_gspread(ws.append_rows, rows_to_add)
    clear_db_cache()


@st.cache_data(ttl=300, show_spinner=False)
def get_all_cv_summaries() -> pd.DataFrame:
    ws = get_ws("iqc_cv_summary", CV_SUMMARY_HEADERS)
    all_vals = _retry_gspread(ws.get_all_values)
    records = _values_to_records(all_vals, CV_SUMMARY_HEADERS)
    if not records:
        return pd.DataFrame(columns=CV_SUMMARY_HEADERS)

    for r in records:
        norm_c, _ = normalize_test_info(r.get("test_code", ""), "")
        r["test_code"] = norm_c
        r["quarter_period"] = _normalize_quarter_str(r.get("quarter_period", ""), r.get("updated_at", ""))

    df = pd.DataFrame(records)
    num_cols = ["level_no", "n_lots", "total_points", "pooled_mean", "chosen_cv_pct"]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values(
        by=["quarter_period", "instrument_name", "test_code", "level_no"],
        ascending=[True, True, True, True],
    ).reset_index(drop=True)


def delete_cv_summary_by_test(
    test_code: str,
    instrument_name: Optional[str] = None,
    quarter_period: Optional[str] = None,
):
    ws = get_ws("iqc_cv_summary", CV_SUMMARY_HEADERS)
    all_vals = _retry_gspread(ws.get_all_values)
    norm_code, _ = normalize_test_info(test_code, "")
    target_q = _normalize_quarter_str(quarter_period) if quarter_period else None

    if len(all_vals) > 1:
        headers = all_vals[0]
        q_idx = headers.index("quarter_period") if "quarter_period" in headers else 1
        inst_idx = headers.index("instrument_name") if "instrument_name" in headers else 2
        test_idx = headers.index("test_code") if "test_code" in headers else 3
        upd_idx = headers.index("updated_at") if "updated_at" in headers else 12

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
            match_q = True if not target_q else r_q.lower() == target_q.lower()
            if match_test and match_inst and match_q:
                _retry_gspread(ws.delete_rows, i + 1)
    clear_db_cache()

# ==============================================================================
# SIGMA & WESTGARD SUMMARY STORAGE (sigma_summary)
# ==============================================================================
def save_sigma_summary_records(
    instrument_name: str,
    test_code: str,
    level_records: List[Dict[str, Any]],
    quarter_period: str = "Q1/2026",
):
    ws = get_ws("sigma_summary", SIGMA_SUMMARY_HEADERS)
    all_vals = _retry_gspread(ws.get_all_values)
    norm_code, norm_name = normalize_test_info(test_code, "")
    q_clean = _normalize_quarter_str(quarter_period)

    if len(all_vals) > 1:
        headers = all_vals[0]
        q_idx = headers.index("quarter_period") if "quarter_period" in headers else 1
        inst_idx = headers.index("instrument_name") if "instrument_name" in headers else 2
        test_idx = headers.index("test_code") if "test_code" in headers else 3
        upd_idx = headers.index("updated_at") if "updated_at" in headers else 16

        rows_to_del = []
        for i in range(len(all_vals) - 1, 0, -1):
            row_i = all_vals[i]
            r_inst = str(row_i[inst_idx]).strip().lower() if inst_idx < len(row_i) else ""
            r_test, _ = normalize_test_info(row_i[test_idx] if test_idx < len(row_i) else "", "")
            r_q = _normalize_quarter_str(
                row_i[q_idx] if q_idx < len(row_i) else "",
                row_i[upd_idx] if upd_idx < len(row_i) else "",
            )
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
    existing = _values_to_records(after_vals, SIGMA_SUMMARY_HEADERS)
    next_id = max([int(r["id"]) for r in existing if str(r.get("id", "")).isdigit()], default=0)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    rows_to_add = []
    for rec in level_records:
        next_id += 1
        rows_to_add.append([
            next_id,
            q_clean,
            rec.get("instrument_name", instrument_name),
            norm_code,
            rec.get("test_full_name", norm_name or norm_code),
            rec.get("unit", ""),
            int(rec.get("level_no", 1) or 1),
            rec.get("level_name", "Level 1 (LOW)"),
            rec.get("tea_source", ""),
            round(float(rec.get("tea_pct", 0.0) or 0.0), 3),
            round(float(rec.get("bias_pct", 0.0) or 0.0), 3),
            round(float(rec.get("cv_pct", 0.0) or 0.0), 3),
            round(float(rec.get("sigma_val", 0.0) or 0.0), 2),
            rec.get("sigma_grade", ""),
            rec.get("westgard_rules", ""),
            rec.get("qc_freq_note", ""),
            now_str,
        ])

    if rows_to_add:
        _ensure_ws_capacity(ws, len(existing) + len(rows_to_add) + 10)
        _retry_gspread(ws.append_rows, rows_to_add)
    clear_db_cache()


@st.cache_data(ttl=300, show_spinner=False)
def get_all_sigma_summaries() -> pd.DataFrame:
    ws = get_ws("sigma_summary", SIGMA_SUMMARY_HEADERS)
    all_vals = _retry_gspread(ws.get_all_values)
    records = _values_to_records(all_vals, SIGMA_SUMMARY_HEADERS)
    if not records:
        return pd.DataFrame(columns=SIGMA_SUMMARY_HEADERS)

    for r in records:
        norm_c, norm_n = normalize_test_info(r.get("test_code", ""), r.get("test_full_name", ""))
        r["test_code"] = norm_c
        r["test_full_name"] = norm_n or norm_c
        r["quarter_period"] = _normalize_quarter_str(r.get("quarter_period", ""), r.get("updated_at", ""))

    df = pd.DataFrame(records)
    num_cols = ["level_no", "tea_pct", "bias_pct", "cv_pct", "sigma_val"]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values(
        by=["quarter_period", "instrument_name", "test_code", "level_no"],
        ascending=[True, True, True, True],
    ).reset_index(drop=True)


def delete_sigma_summary_by_test(
    test_code: str,
    instrument_name: Optional[str] = None,
    quarter_period: Optional[str] = None,
):
    ws = get_ws("sigma_summary", SIGMA_SUMMARY_HEADERS)
    all_vals = _retry_gspread(ws.get_all_values)
    norm_code, _ = normalize_test_info(test_code, "")
    target_q = _normalize_quarter_str(quarter_period) if quarter_period else None

    if len(all_vals) > 1:
        headers = all_vals[0]
        q_idx = headers.index("quarter_period") if "quarter_period" in headers else 1
        inst_idx = headers.index("instrument_name") if "instrument_name" in headers else 2
        test_idx = headers.index("test_code") if "test_code" in headers else 3
        upd_idx = headers.index("updated_at") if "updated_at" in headers else 16

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
            match_q = True if not target_q else r_q.lower() == target_q.lower()
            if match_test and match_inst and match_q:
                _retry_gspread(ws.delete_rows, i + 1)
    clear_db_cache()