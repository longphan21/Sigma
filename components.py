from typing import List, Dict, Any
from ui_theme import render_html, format_status_badge_html


def fmt_num(val, decimals: int = 3) -> str:
    """Định dạng số thập phân sử dụng dấu chấm (.) chuẩn hệ thống phòng xét nghiệm."""
    if val is None or val == "":
        return "-"
    try:
        f = float(val)
        if decimals == 0:
            return f"{int(round(f))}"
        return f"{f:.{decimals}f}"
    except (ValueError, TypeError):
        return str(val)


def map_eval_badge(status_code: str, z_score: float = None) -> str:
    """Chuyển trạng thái đánh giá EQA (PASS / WARN / FAIL) sang badge HTML của ui_theme."""
    s = str(status_code or "").upper()
    if s == "PASS":
        return format_status_badge_html("ĐẠT")
    if s == "FAIL":
        return format_status_badge_html("KHÔNG ĐẠT")
    return format_status_badge_html(f"CẢNH BÁO (|z|={fmt_num(abs(z_score), 2)})" if z_score is not None else "CẢNH BÁO")


def render_batch_meta_bar(batch: Dict[str, Any]):
    """Hiển thị thanh thông tin tóm tắt của 1 đợt Ngoại kiểm (.history-meta-bar)."""
    render_html(f"""
    <div class="history-meta-bar">
        <span><span class="date-pill">{batch.get('month_year', '-')}</span></span>
        <span><b>Đợt:</b> <span class="lot-pill">Đợt {batch.get('batch_no', '01')}</span></span>
        <span><b>Chương trình:</b> {batch.get('program_name', '-')} (<b>{batch.get('program_code', '-')}</b>)</span>
        <span><b>Thiết bị:</b> {batch.get('instrument_name', '-')}</span>
        <span><b>Mã đơn vị:</b> <code>{batch.get('unit_code', '-')}</code></span>
        <span><b>Mã mẫu:</b> <span class="lot-pill">{batch.get('sample_code', '-')}</span></span>
    </div>
    """)


def render_eqa_results_table(results: List[Dict[str, Any]], max_height: int = 340):
    """
    Hiển thị bảng kết quả ngoại kiểm chuẩn y khoa (.lab-table-wrapper & .lab-table)
    với công thức cố định BIAS % = (|KQ đơn vị - GT ấn định| * 100) / GT ấn định.
    """
    if not results:
        render_html('<div class="search-result-pill">Không có dữ liệu xét nghiệm phù hợp.</div>')
        return

    rows_html = []
    for idx, r in enumerate(results, start=1):
        badge_html = map_eval_badge(r.get("eval_status"), r.get("z_score"))
        lab_v = r.get("lab_result")
        asg_v = r.get("assigned_value")
        bias_pct_val = r.get("bias_pct")

        if lab_v is not None and asg_v not in (None, 0):
            try:
                exact_b = abs(float(lab_v) - float(asg_v)) * 100.0 / abs(float(asg_v))
                bias_pct_str = f"{exact_b:.2f}%"
            except Exception:
                bias_pct_str = f"{abs(float(bias_pct_val)):.2f}%" if bias_pct_val is not None else "-"
        else:
            bias_pct_str = f"{abs(float(bias_pct_val)):.2f}%" if bias_pct_val is not None else "-"

        z_val = r.get("z_score")
        z_str = f"{float(z_val):+.2f}" if z_val is not None else "-"

        rows_html.append(f"""
        <tr>
            <td class="text-center">{idx}</td>
            <td class="text-left"><b>{r.get('test_code', '')}</b></td>
            <td class="text-left">{r.get('test_full_name', '')}</td>
            <td class="text-center">{r.get('unit', '')}</td>
            <td class="text-right"><b>{fmt_num(lab_v, 3)}</b></td>
            <td class="text-right">{fmt_num(asg_v, 3)}</td>
            <td class="text-right">{fmt_num(r.get('bias_abs'), 3)}</td>
            <td class="text-right"><b>{bias_pct_str}</b></td>
            <td class="text-right">{fmt_num(r.get('sigma_p'), 3)}</td>
            <td class="text-right"><b>{z_str}</b></td>
            <td class="text-right">{fmt_num(r.get('peer_sd'), 4)}</td>
            <td class="text-right">{fmt_num(r.get('peer_cv'), 2)}%</td>
            <td class="text-center">{badge_html}</td>
        </tr>
        """)

    table_html = f"""
    <div class="lab-table-wrapper" style="max-height: {max_height}px;">
        <table class="lab-table">
            <thead>
                <tr>
                    <th class="text-center">#</th>
                    <th class="text-left">Mã XN</th>
                    <th class="text-left">Tên thông số xét nghiệm</th>
                    <th class="text-center">Đơn vị</th>
                    <th class="text-right">KQ Đơn vị (D)</th>
                    <th class="text-right">GT Ấn định (E)</th>
                    <th class="text-right">|D - E|</th>
                    <th class="text-right">BIAS %</th>
                    <th class="text-right">σp</th>
                    <th class="text-right">z-score</th>
                    <th class="text-right">SD Nhóm máy</th>
                    <th class="text-right">%CV Nhóm máy</th>
                    <th class="text-center">Đánh giá</th>
                </tr>
            </thead>
            <tbody>
                {"".join(rows_html)}
            </tbody>
        </table>
    </div>
    """
    render_html(table_html)


def render_overview_compact_card(batch: Dict[str, Any], results: List[Dict[str, Any]]):
    """
    Hiển thị danh sách xét nghiệm trong 1 đợt theo dạng Compact List (.overview-list-card)
    đúng cấu trúc CSS của ui_theme.py, bấm vào từng xét nghiệm sẽ xổ ra 3 nhóm so sánh (All / Method / Instrument).
    """
    if not results:
        return

    items_html = []
    for r in results:
        code = r.get("test_code", "XN")
        avatar_txt = code[:2].upper()
        badge_html = map_eval_badge(r.get("eval_status"), r.get("z_score"))
        lab_v = r.get("lab_result")
        asg_v = r.get("assigned_value")
        bias_pct = r.get("bias_pct")

        if lab_v is not None and asg_v not in (None, 0):
            try:
                exact_b = abs(float(lab_v) - float(asg_v)) * 100.0 / abs(float(asg_v))
                bias_str = f"{exact_b:.2f}%"
            except Exception:
                bias_str = f"{abs(float(bias_pct)):.2f}%" if bias_pct is not None else "-"
        else:
            bias_str = f"{abs(float(bias_pct)):.2f}%" if bias_pct is not None else "-"

        z_val = r.get("z_score")
        z_str = f"z = {float(z_val):+.2f}" if z_val is not None else "-"

        items_html.append(f"""
        <details class="overview-item">
            <summary class="overview-row">
                <div class="item-name-cell">
                    <span class="item-avatar">{avatar_txt}</span>
                    <span>{code} — {r.get('test_full_name', '')} <small style="color:#64748B;">({r.get('unit', '')})</small></span>
                </div>
                <div class="item-lot-cell">KQ: {fmt_num(lab_v, 3)} / {fmt_num(asg_v, 3)}</div>
                <div class="item-date-cell">BIAS%: <b>{bias_str}</b> | {z_str}</div>
                <div>{badge_html}</div>
                <div class="item-action-cell">Chi tiết ▾</div>
            </summary>
            <div class="overview-subbox">
                <div class="history-meta-bar" style="margin-bottom:6px;">
                    <span><b>Kết quả đơn vị (D):</b> <code>{fmt_num(lab_v, 3)} {r.get('unit', '')}</code></span>
                    <span><b>Giá trị ấn định (E):</b> <code>{fmt_num(asg_v, 3)} {r.get('unit', '')}</code></span>
                    <span><b>|D - E|:</b> <code>{fmt_num(r.get('bias_abs'), 4)}</code></span>
                    <span><b>BIAS % = |D-E|*100/E:</b> <code>{bias_str}</code></span>
                    <span><b>σp:</b> <code>{fmt_num(r.get('sigma_p'), 3)}</code></span>
                    <span><b>z-score:</b> <code>{z_str}</code></span>
                </div>
                <div class="lab-table-wrapper" style="max-height:160px;">
                    <table class="lab-table">
                        <thead>
                            <tr>
                                <th class="text-left">Nhóm phân tích thống kê (VEQAS)</th>
                                <th class="text-left">Tên nhóm / Phương pháp / Máy</th>
                                <th class="text-right">N</th>
                                <th class="text-right">Giá trị ấn định</th>
                                <th class="text-right">SD</th>
                                <th class="text-right">%CV</th>
                                <th class="text-right">Số KQ loại</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr>
                                <td class="text-left"><b>1. Tất cả phương pháp</b></td>
                                <td class="text-left">Tất cả phương pháp</td>
                                <td class="text-right">{fmt_num(r.get('all_n'), 0)}</td>
                                <td class="text-right">{fmt_num(r.get('all_mean'), 3)}</td>
                                <td class="text-right">{fmt_num(r.get('all_sd'), 4)}</td>
                                <td class="text-right">{fmt_num(r.get('all_cv'), 2)}%</td>
                                <td class="text-right">{fmt_num(r.get('all_excluded'), 0)}</td>
                            </tr>
                            <tr>
                                <td class="text-left"><b>2. Nhóm phương pháp</b></td>
                                <td class="text-left">{r.get('method_name') or '-'}</td>
                                <td class="text-right">{fmt_num(r.get('method_n'), 0)}</td>
                                <td class="text-right">{fmt_num(r.get('method_mean'), 3)}</td>
                                <td class="text-right">{fmt_num(r.get('method_sd'), 4)}</td>
                                <td class="text-right">{fmt_num(r.get('method_cv'), 2)}%</td>
                                <td class="text-right">{fmt_num(r.get('method_excluded'), 0)}</td>
                            </tr>
                            <tr>
                                <td class="text-left"><b>3. Nhóm thiết bị (Peer)</b></td>
                                <td class="text-left"><b>{r.get('peer_name') or batch.get('instrument_name', '-')}</b></td>
                                <td class="text-right">{fmt_num(r.get('peer_n'), 0)}</td>
                                <td class="text-right"><b>{fmt_num(r.get('peer_mean'), 3)}</b></td>
                                <td class="text-right">{fmt_num(r.get('peer_sd'), 4)}</td>
                                <td class="text-right"><b>{fmt_num(r.get('peer_cv'), 2)}%</b></td>
                                <td class="text-right">{fmt_num(r.get('peer_excluded'), 0)}</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </details>
        """)

    card_html = f"""
    <div class="overview-list-card">
        <div class="overview-group-header">
            <div class="overview-mach-title">🔬 {batch.get('instrument_name', 'Thiết bị')} — {batch.get('batch_label', '')} ({len(results)} XN)</div>
            <div>KQ Đơn vị / Ấn định</div>
            <div>BIAS % & z-score</div>
            <div>Trạng thái</div>
            <div style="text-align:right;">Thao tác</div>
        </div>
        {"".join(items_html)}
    </div>
    """
    render_html(card_html)
