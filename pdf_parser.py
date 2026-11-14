import io
import os
import re
from datetime import datetime
from typing import Dict, Any, List, Tuple, Union
import pypdf


def _to_float(val_str: str) -> float:
    """Chuyển chuỗi số (hỗ trợ cả dấu chấm hoặc phẩy) sang float chuẩn dấu chấm."""
    if val_str is None:
        return None
    cleaned = str(val_str).strip().replace(",", ".")
    cleaned = re.sub(r"[^0-9.\-+]", "", cleaned)
    if not cleaned or cleaned in (".", "-", "+"):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _to_int(val_str: str) -> int:
    """Chuyển chuỗi số nguyên sang int."""
    f = _to_float(val_str)
    return int(round(f)) if f is not None else None


def _is_numeric_token(token: str) -> bool:
    """Kiểm tra token có phải là một con số thuần túy hay không."""
    t = token.strip().replace(",", ".")
    return bool(re.fullmatch(r"[-+]?\d+(?:\.\d+)?", t))


def _extract_nums_from_line(tokens: List[str], after_colon: bool = True) -> List[float]:
    """
    Trích xuất chuẩn xác các con số trên 1 dòng văn bản PDF,
    kể cả khi con số bị dính liền với dấu hai chấm hoặc đơn vị đo.
    """
    direct_nums = [_to_float(t) for t in tokens if _is_numeric_token(t)]
    direct_nums = [x for x in direct_nums if x is not None]
    if direct_nums:
        return direct_nums

    joined = " ".join(tokens)
    target_str = joined.split(":", 1)[1] if (after_colon and ":" in joined) else joined
    matches = re.findall(r"[-+]?\d+(?:[.,]\d+)?", target_str)
    res = [_to_float(m) for m in matches]
    return [x for x in res if x is not None]


def _evaluate_zscore(z_val: float) -> str:
    """Phân loại kết quả ngoại kiểm theo chuẩn |z-score|."""
    if z_val is None:
        return "WARN"
    az = abs(z_val)
    if az <= 2.0:
        return "PASS"
    elif az < 3.0:
        return "WARN"
    return "FAIL"


def _extract_page_items(page: pypdf.PageObject) -> List[Tuple[float, str]]:
    """
    Trích xuất danh sách các đoạn text kèm tọa độ dọc y (từ trên xuống dưới)
    theo đúng thứ tự xuất hiện trong luồng PDF của báo cáo VEQAS.
    """
    items: List[Tuple[float, str]] = []

    def _visitor(text, cm, tm, font_dict, font_size):
        txt = text.strip()
        if txt:
            y = round(float(tm[5]), 2)
            items.append((y, txt))

    page.extract_text(visitor_text=_visitor)
    return items


def _group_by_y(items: List[Tuple[float, str]], tolerance: float = 2.2) -> List[Tuple[float, List[str]]]:
    """Gom các phần tử có cùng tọa độ y (trong ngưỡng tolerance) thành từng dòng ngang."""
    sorted_items = sorted(items, key=lambda x: -x[0])
    grouped: List[Tuple[float, List[str]]] = []
    for y, txt in sorted_items:
        if not grouped or abs(grouped[-1][0] - y) > tolerance:
            grouped.append((y, [txt]))
        else:
            grouped[-1][1].append(txt)
    return grouped


def _parse_test_header(raw_header: str) -> Tuple[str, str, str]:
    """
    Tách tên đầy đủ, mã viết tắt và đơn vị đo từ chuỗi tiêu đề thông số VEQAS.
    Có xử lý lỗi dấu ngoặc lồng nhau (VD: ALT (GPT)).
    """
    s = raw_header.strip()

    parens = list(re.finditer(r"\(([^()]+)\)", s))
    if not parens:
        parts = s.rsplit(" ", 1)
        if len(parts) == 2:
            return parts[0].strip(), parts[0].strip(), parts[1].strip()
        return s, s, ""

    last_paren = parens[-1]
    test_code = last_paren.group(1).strip()
    unit = s[last_paren.end():].strip()

    if unit.startswith(")"):
        unit = unit[1:].strip()

    full_name = s if not unit else s[:-len(unit)].strip()
    return test_code, full_name, unit


def _parse_peer_row(tokens: List[str]) -> Dict[str, Any]:
    """
    Phân tích 1 dòng trong bảng thống kê 3 nhóm (Tất cả phương pháp / Phương pháp / Thiết bị).
    """
    name_parts = [t for t in tokens if not _is_numeric_token(t)]
    num_parts = [t for t in tokens if _is_numeric_token(t)]

    group_name = " ".join(name_parts).strip()
    if len(num_parts) < 5:
        return {
            "name": group_name,
            "n": _to_int(num_parts[0]) if len(num_parts) > 0 else None,
            "mean": _to_float(num_parts[1]) if len(num_parts) > 1 else None,
            "sd": _to_float(num_parts[2]) if len(num_parts) > 2 else None,
            "cv": _to_float(num_parts[3]) if len(num_parts) > 3 else None,
            "excluded": _to_int(num_parts[4]) if len(num_parts) > 4 else None,
        }

    first_is_int = "." not in num_parts[0]
    second_is_int = "." not in num_parts[1]
    last_is_int = "." not in num_parts[4]

    if first_is_int and second_is_int and not last_is_int:
        excluded = _to_int(num_parts[0])
        n_val = _to_int(num_parts[1])
        mean_val = _to_float(num_parts[2])
        sd_val = _to_float(num_parts[3])
        cv_val = _to_float(num_parts[4])
    else:
        n_val = _to_int(num_parts[0])
        mean_val = _to_float(num_parts[1])
        sd_val = _to_float(num_parts[2])
        cv_val = _to_float(num_parts[3])
        excluded = _to_int(num_parts[4])

    return {
        "name": group_name,
        "n": n_val,
        "mean": mean_val,
        "sd": sd_val,
        "cv": cv_val,
        "excluded": excluded,
    }


def _infer_month_year(batch_no: str, filename: str, full_text: str) -> str:
    """Tự động suy luận kỳ Tháng/Năm (MM/YYYY) từ nội dung PDF hoặc tên file."""
    m = re.search(r"\b(0?[1-9]|1[0-2])[-/](20\d{2})\b", full_text)
    if m:
        return f"{int(m.group(1)):02d}/{m.group(2)}"

    y_match = re.search(r"(20\d{2})", filename)
    year_str = y_match.group(1) if y_match else str(datetime.now().year)
    try:
        b_int = int(batch_no)
        month_int = b_int if 1 <= b_int <= 12 else datetime.now().month
    except ValueError:
        month_int = datetime.now().month
    return f"{month_int:02d}/{year_str}"


def _compute_bias_fields(item: Dict[str, Any]):
    """
    Tính và cập nhật bias_abs, bias_pct = (|D - E| * 100) / E, z_score và eval_status cho 1 xét nghiệm.
    """
    lab_result = item.get("lab_result")
    assigned_value = item.get("assigned_value")
    sigma_p = item.get("sigma_p")
    z_score = item.get("z_score")

    bias_abs = None
    bias_pct = None
    if lab_result is not None and assigned_value not in (None, 0):
        bias_abs = round(abs(float(lab_result) - float(assigned_value)), 4)
        bias_pct = round((abs(float(lab_result) - float(assigned_value)) * 100.0) / abs(float(assigned_value)), 4)

    if z_score is None and lab_result is not None and assigned_value is not None and sigma_p not in (None, 0):
        z_score = round((float(lab_result) - float(assigned_value)) / float(sigma_p), 2)

    item["bias_abs"] = bias_abs
    item["bias_pct"] = bias_pct
    item["z_score"] = z_score
    item["eval_status"] = _evaluate_zscore(z_score)


def parse_veqas_pdf(file_source: Union[str, bytes, io.BytesIO], filename: str = "") -> Dict[str, Any]:
    """
    Hàm chính bóc tách file PDF Kết quả Ngoại kiểm (VEQAS).
    Trả về dict gồm:
      - 'metadata': Thông tin chung của đợt ngoại kiểm (Đợt, Tháng/Năm, Mã chương trình, Máy, Mã đơn vị...)
      - 'results': Danh sách kết quả chi tiết của từng xét nghiệm (kèm Bias tuyệt đối, BIAS % = |D-E|*100/E, σp, z-score, 3 nhóm peer)
    """
    if isinstance(file_source, bytes):
        pdf_stream = io.BytesIO(file_source)
    else:
        pdf_stream = file_source

    reader = pypdf.PdfReader(pdf_stream)
    if not filename and isinstance(file_source, str):
        filename = os.path.basename(file_source)

    metadata = {
        "program_name": "Sinh hóa",
        "program_code": "BC20C",
        "batch_no": "01",
        "unit_code": "",
        "instrument_name": "",
        "sample_code": "",
        "provider_name": "VEQAS - TT Kiểm chuẩn XN TP.HCM",
        "source_filename": filename,
    }

    # --- BƯỚC 1: ĐỌC TRANG BÌA (TRANG 1) ---
    if len(reader.pages) > 0:
        p1_items = _extract_page_items(reader.pages[0])
        p1_lines = _group_by_y(p1_items, tolerance=2.5)
        for idx, (y, tokens) in enumerate(p1_lines):
            line_str = " ".join(tokens)
            if "Mã đơn vị" in line_str:
                nums = [t for t in tokens if _is_numeric_token(t)]
                if nums:
                    metadata["unit_code"] = nums[0]
                else:
                    m_u = re.search(r"Mã đơn vị:\s*(\S+)", line_str)
                    if m_u:
                        metadata["unit_code"] = m_u.group(1)
                if idx + 1 < len(p1_lines):
                    next_line = " ".join(p1_lines[idx + 1][1]).strip()
                    if next_line and "Chương trình" not in next_line and "ISO" not in next_line:
                        metadata["instrument_name"] = next_line

            if "Chương trình ngoại kiểm tra" in line_str and idx + 1 < len(p1_lines):
                metadata["program_name"] = " ".join(p1_lines[idx + 1][1]).strip()

            if "Mã chương trình" in line_str:
                for t in tokens:
                    if "Mã chương trình" not in t and t.strip(":"):
                        metadata["program_code"] = t.strip()
                        break

            if "Đợt" in line_str:
                for t in tokens:
                    if _is_numeric_token(t):
                        metadata["batch_no"] = f"{int(float(t)):02d}"
                        break

            if y < 40 and len(tokens) == 1 and re.fullmatch(r"\d{8,16}", tokens[0]):
                metadata["sample_code"] = tokens[0]

    detail_results: List[Dict[str, Any]] = []
    summary_lookup: Dict[str, Dict[str, Any]] = {}
    all_text_concat = []

    # --- BƯỚC 2: DUYỆT CÁC TRANG CHI TIẾT (TRANG 2 -> N) & TRANG TỔNG HỢP ---
    for page_idx, page in enumerate(reader.pages):
        page_no = page_idx + 1
        items = _extract_page_items(page)
        lines = _group_by_y(items, tolerance=2.2)
        raw_page_text = "\n".join(" ".join(t for _, t in items) for _ in [0])
        all_text_concat.append(raw_page_text)

        for y, tokens in lines:
            joined = " ".join(tokens)
            m_hdr = re.search(r"MÃ CHƯƠNG TRÌNH\s*:\s*([A-Z0-9]+)\s*-\s*ĐỢT\s*(\d+)", joined, re.IGNORECASE)
            if m_hdr:
                metadata["program_code"] = m_hdr.group(1).strip()
                metadata["batch_no"] = f"{int(m_hdr.group(2)):02d}"
            if not metadata["unit_code"] and "Mã đơn vị:" in joined:
                m_u = re.search(r"Mã đơn vị:\s*(\d+)", joined)
                if m_u:
                    metadata["unit_code"] = m_u.group(1)

        has_thong_so = any("THÔNG SỐ:" in " ".join(tk) for _, tk in lines)
        has_kq_don_vi = any("Kết quả đơn vị:" in " ".join(tk) for _, tk in lines)

        if has_thong_so and has_kq_don_vi:
            test_code, test_full_name, unit = "", "", ""
            peer_rows = []
            lab_result = None
            assigned_value = None
            sigma_p = None
            z_score = None

            for y, tokens in lines:
                joined = " ".join(tokens)

                if "THÔNG SỐ:" in joined:
                    clean_tokens = [
                        t for t in tokens
                        if "THÔNG SỐ" not in t and "Mã đơn vị" not in t and t != metadata["unit_code"]
                    ]
                    if clean_tokens:
                        test_code, test_full_name, unit = _parse_test_header(" ".join(clean_tokens))

                elif 670.0 <= y <= 722.0:
                    num_cnt = sum(1 for t in tokens if _is_numeric_token(t))
                    if num_cnt >= 4:
                        peer_rows.append(_parse_peer_row(tokens))

                elif "Kết quả đơn vị" in joined:
                    nums = _extract_nums_from_line(tokens)
                    if nums:
                        lab_result = nums[-1]
                elif "Giá trị ấn định so sánh" in joined:
                    nums = _extract_nums_from_line(tokens)
                    if nums:
                        assigned_value = nums[-1]
                elif "σp" in joined or "op" in joined.lower():
                    nums = _extract_nums_from_line(tokens)
                    if nums:
                        sigma_p = nums[-1]
                elif "z-score" in joined.lower():
                    nums = _extract_nums_from_line(tokens)
                    if nums:
                        z_score = nums[0]

            all_grp = peer_rows[0] if len(peer_rows) >= 1 else {}
            method_grp = peer_rows[1] if len(peer_rows) >= 2 else {}
            peer_grp = peer_rows[2] if len(peer_rows) >= 3 else (peer_rows[-1] if len(peer_rows) > 1 else {})

            if not metadata["instrument_name"] and peer_grp.get("name"):
                metadata["instrument_name"] = peer_grp["name"]

            item_dict = {
                "test_code": test_code,
                "test_full_name": test_full_name,
                "unit": unit,
                "lab_result": lab_result,
                "assigned_value": assigned_value,
                "sigma_p": sigma_p,
                "z_score": z_score,
                "all_n": all_grp.get("n"),
                "all_mean": all_grp.get("mean"),
                "all_sd": all_grp.get("sd"),
                "all_cv": all_grp.get("cv"),
                "all_excluded": all_grp.get("excluded"),
                "method_name": method_grp.get("name", ""),
                "method_n": method_grp.get("n"),
                "method_mean": method_grp.get("mean"),
                "method_sd": method_grp.get("sd"),
                "method_cv": method_grp.get("cv"),
                "method_excluded": method_grp.get("excluded"),
                "peer_name": peer_grp.get("name", ""),
                "peer_n": peer_grp.get("n"),
                "peer_mean": peer_grp.get("mean"),
                "peer_sd": peer_grp.get("sd"),
                "peer_cv": peer_grp.get("cv"),
                "peer_excluded": peer_grp.get("excluded"),
                "page_no": page_no,
            }
            _compute_bias_fields(item_dict)
            detail_results.append(item_dict)

        elif any("Đơn vị đo" in " ".join(tk) and "Thông số" in " ".join(tk) for _, tk in lines):
            for y, tokens in lines:
                if 100.0 <= y <= 700.0 and len(tokens) >= 6:
                    nums = [t for t in tokens if _is_numeric_token(t)]
                    non_nums = [t for t in tokens if not _is_numeric_token(t)]
                    if len(nums) == 4 and len(non_nums) >= 2:
                        raw_t_name = non_nums[-1].strip()
                        parsed_code, _, _ = _parse_test_header(raw_t_name)
                        t_code = parsed_code or raw_t_name
                        t_unit = non_nums[0].strip()
                        z_val = _to_float(nums[0])
                        sp_val = _to_float(nums[1])
                        asg_val = _to_float(nums[2])
                        res_val = _to_float(nums[3])
                        summary_lookup[t_code.upper()] = {
                            "test_code": t_code,
                            "test_full_name": raw_t_name,
                            "unit": t_unit,
                            "lab_result": res_val,
                            "assigned_value": asg_val,
                            "sigma_p": sp_val,
                            "z_score": z_val,
                        }

    # --- BƯỚC 3: ĐỐI CHIẾU CHÉO VỚI BẢNG TỔNG HỢP (TRANG CUỐI) ---
    if detail_results and summary_lookup:
        for item in detail_results:
            code_key = item["test_code"].upper()
            if code_key in summary_lookup:
                s_row = summary_lookup[code_key]
                updated = False
                for field in ("lab_result", "assigned_value", "sigma_p", "z_score", "unit"):
                    if item.get(field) is None and s_row.get(field) is not None:
                        item[field] = s_row[field]
                        updated = True
                if updated:
                    _compute_bias_fields(item)
    elif not detail_results and summary_lookup:
        for idx, (_, s_row) in enumerate(reversed(list(summary_lookup.items())), start=1):
            item_dict = {
                "test_code": s_row["test_code"],
                "test_full_name": s_row.get("test_full_name", s_row["test_code"]),
                "unit": s_row["unit"],
                "lab_result": s_row["lab_result"],
                "assigned_value": s_row["assigned_value"],
                "sigma_p": s_row["sigma_p"],
                "z_score": s_row["z_score"],
                "page_no": idx,
            }
            _compute_bias_fields(item_dict)
            detail_results.append(item_dict)

    month_year = _infer_month_year(metadata["batch_no"], filename, "\n".join(all_text_concat))
    metadata["month_year"] = month_year
    metadata["batch_label"] = f"Đợt {metadata['batch_no']} - Tháng {month_year}"

    return {
        "metadata": metadata,
        "results": detail_results,
    }
