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


def get_ws(name: str, headers: List[str]):
    """Lấy Worksheet, nếu chưa có thì tự động tạo và thêm dòng Header."""
    doc = get_spreadsheet()
    try:
        return doc.worksheet(name)
    except:
        ws = doc.add_worksheet(title=name, rows=100, cols=len(headers))
        ws.append_row(headers)
        return ws


def init_database():
    """Khởi tạo các trang tính nếu chưa tồn tại."""
    get_ws("eqa_batches", BATCHES_HEADERS)
    get_ws("eqa_results", RESULTS_HEADERS)


def check_batch_exists(program_code: str, batch_no: str, month_year: str, instrument_name: str,
                       sample_code: str = "") -> Optional[int]:
    ws = get_ws("eqa_batches", BATCHES_HEADERS)
    records = ws.get_all_records()
    for r in records:
        if (str(r.get("program_code", "")).strip() == program_code.strip() and
                str(r.get("batch_no", "")).strip() == batch_no.strip() and
                str(r.get("month_year", "")).strip() == month_year.strip() and
                str(r.get("instrument_name", "")).strip() == instrument_name.strip()):
            if not sample_code or str(r.get("sample_code", "")).strip() == sample_code.strip():
                return int(r["id"]) if r.get("id") else None
    return None


def save_eqa_batch(metadata: Dict[str, Any], results: List[Dict[str, Any]],
                   overwrite_batch_id: Optional[int] = None) -> int:
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
        metadata.get("instrument_name", ""), metadata.get("sample_code", ""),
        metadata.get("provider_name", "VEQAS - TT Kiểm chuẩn XN TP.HCM"),
        metadata.get("source_filename", ""), total_tests, pass_count, warn_count, fail_count, now_str,
        metadata.get("notes", "")
    ]
    ws_batches.append_row(batch_row)

    results_records = ws_results.get_all_records()
    res_id = max([int(r["id"]) for r in results_records if str(r.get("id")).isdigit()], default=0)

    rows_to_append = []
    for item in results:
        res_id += 1
        row = [
            res_id, batch_id, item.get("test_code", ""), item.get("test_full_name", ""), item.get("unit", ""),
            item.get("lab_result", ""), item.get("assigned_value", ""), item.get("sigma_p", ""),
            item.get("z_score", ""),
            item.get("bias_abs", ""), item.get("bias_pct", ""), item.get("eval_status", "PASS"),
            item.get("all_n", ""), item.get("all_mean", ""), item.get("all_sd", ""), item.get("all_cv", ""),
            item.get("all_excluded", ""),
            item.get("method_name", ""), item.get("method_n", ""), item.get("method_mean", ""),
            item.get("method_sd", ""), item.get("method_cv", ""), item.get("method_excluded", ""),
            item.get("peer_name", ""), item.get("peer_n", ""), item.get("peer_mean", ""), item.get("peer_sd", ""),
            item.get("peer_cv", ""), item.get("peer_excluded", ""),
            item.get("page_no", "")
        ]
        row = ["" if x is None else x for x in row]
        rows_to_append.append(row)

    if rows_to_append:
        ws_results.append_rows(rows_to_append)

    return batch_id


def get_all_batches() -> List[Dict[str, Any]]:
    ws = get_ws("eqa_batches", BATCHES_HEADERS)
    records = ws.get_all_records()
    records.sort(key=lambda x: (str(x.get("month_year", "")), str(x.get("batch_no", "")), int(x.get("id", 0))),
                 reverse=True)
    return records


def get_batch_by_id(batch_id: int) -> Optional[Dict[str, Any]]:
    for r in get_all_batches():
        if str(r.get("id")) == str(batch_id):
            return r
    return None


def get_results_by_batch(batch_id: int) -> List[Dict[str, Any]]:
    ws = get_ws("eqa_results", RESULTS_HEADERS)
    records = ws.get_all_records()
    filtered = [r for r in records if str(r.get("batch_id", "")) == str(batch_id)]

    for r in filtered:
        for k, v in list(r.items()):
            if v == "":
                r[k] = None
            elif k in ["lab_result", "assigned_value", "bias_abs", "bias_pct", "sigma_p", "z_score", "peer_sd",
                       "peer_cv"]:
                try:
                    r[k] = float(v)
                except:
                    pass
    filtered.sort(key=lambda x: (x.get("page_no", 999), x.get("id", 0)))
    return filtered


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

    return b_deleted