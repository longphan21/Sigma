import io
import streamlit as st
import pandas as pd

from ui_theme import (
    init_theme,
    render_sidebar_menu,
    render_page_banner,
    queue_popup,
    format_status_badge_html,
    render_html,
)
from database import (
    init_database,
    check_batch_exists,
    save_eqa_batch,
    get_all_batches,
    get_results_by_batch,
    get_all_results_joined,
    delete_batch,
)
from pdf_parser import parse_veqas_pdf
from components import (
    render_batch_meta_bar,
    render_eqa_results_table,
    render_overview_compact_card,
)
from bias_calculator import render_bias_calculator_page

# 1. Khởi tạo giao diện chuẩn ui_theme.py & Database Google Sheets
init_theme(page_title="EQA Database - Six Sigma Module")
init_database()

# 2. Thanh Menu dọc bên trái
MENU_ITEMS = [
    ("1. Overview", ":material/dashboard:"),
    ("2. Import EQA PDF", ":material/upload_file:"),
    ("3. Tính %Bias (EQA)", ":material/calculate:"),
    ("4. Quản lý Đợt EQA", ":material/folder_open:"),
]

page = render_sidebar_menu(
    brand_title="🔬 LAB SYSTEM",
    brand_subtitle="EQA & Six Sigma Module",
    menu_items=MENU_ITEMS,
)


# ==============================================================================
# TRANG 1: OVERVIEW - TỔNG QUAN CÁC ĐỢT NGOẠI KIỂM ĐÃ LƯU
# ==============================================================================
if page == "1. Overview":
    render_page_banner(
        "Tổng quan Cơ sở dữ liệu Ngoại kiểm (EQA)",
        "Quản lý kết quả ngoại kiểm theo từng đợt (Tháng/Năm) và tính BIAS % = (|KQ đơn vị - GT ấn định| * 100) / GT ấn định.",
    )

    batches = get_all_batches()
    df_all = get_all_results_joined()

    if not batches:
        with st.container(border=True):
            st.markdown("#### :material/info: Chưa có dữ liệu ngoại kiểm trong Database")
            st.write(
                "Hãy chuyển sang mục **2. Import EQA PDF** ở thanh menu bên trái để tải lên file PDF kết quả ngoại kiểm (VEQAS) đầu tiên."
            )
    else:
        total_batches = len(batches)
        total_records = len(df_all)
        pass_total = int((df_all["eval_status"] == "PASS").sum()) if not df_all.empty else 0
        pass_rate = (pass_total / total_records * 100.0) if total_records > 0 else 0.0
        mean_abs_bias = df_all["bias_pct"].abs().mean() if not df_all.empty else 0.0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Tổng số đợt EQA", f"{total_batches} đợt")
        c2.metric("Tổng số kết quả XN", f"{total_records} XN")
        c3.metric("Tỷ lệ Đạt (|z| ≤ 2.0)", f"{pass_rate:.1f}%")
        c4.metric("BIAS % trung bình", f"{mean_abs_bias:.2f}%")

        with st.container(border=True):
            st.markdown("#### :material/filter_alt: Bộ lọc tra cứu nhanh theo Đợt & Xét nghiệm")
            f1, f2, f3, f4 = st.columns([1.3, 1.3, 1.4, 1.0])

            month_options = ["Tất cả"] + sorted(list({b["month_year"] for b in batches}), reverse=True)
            inst_options = ["Tất cả"] + sorted(list({b["instrument_name"] for b in batches if b.get("instrument_name")}))

            sel_month = f1.selectbox("Kỳ Tháng/Năm", month_options, key="ov_month")
            sel_inst = f2.selectbox("Thiết bị phân tích", inst_options, key="ov_inst")
            search_kw = f3.text_input("Tìm nhanh Xét nghiệm (VD: ALT, GLU, CREA...)", key="ov_kw").strip().lower()
            view_mode = f4.selectbox("Chế độ hiển thị", ["Compact List", "Bảng chuẩn Y khoa"], key="ov_view_mode")

        shown_batches = 0
        for b in batches:
            if sel_month != "Tất cả" and b["month_year"] != sel_month:
                continue
            if sel_inst != "Tất cả" and b["instrument_name"] != sel_inst:
                continue

            b_results = get_results_by_batch(b["id"])
            if search_kw:
                b_results = [
                    r for r in b_results
                    if search_kw in str(r.get("test_code", "")).lower()
                    or search_kw in str(r.get("test_full_name", "")).lower()
                ]
            if not b_results:
                continue

            shown_batches += 1
            expander_title = (
                f"📅 {b['batch_label']} — Chương trình: {b['program_name']} ({b['program_code']}) "
                f"| Máy: {b['instrument_name']} | Mã ĐV: {b['unit_code']}"
            )
            with st.expander(expander_title, expanded=False):
                if view_mode == "Compact List":
                    render_overview_compact_card(b, b_results)
                else:
                    render_batch_meta_bar(b)
                    render_eqa_results_table(b_results, max_height=360)

        if shown_batches == 0:
            render_html('<div class="search-result-pill">Không tìm thấy đợt ngoại kiểm nào khớp với điều kiện lọc.</div>')


# ==============================================================================
# TRANG 2: IMPORT EQA PDF - BÓC TÁCH VÀ LƯU FILE PDF NGOẠI KIỂM VÀO DATABASE
# ==============================================================================
elif page == "2. Import EQA PDF":
    render_page_banner(
        "Import & Bóc tách File PDF Kết quả Ngoại kiểm",
        "Tự động đọc file PDF báo cáo ngoại kiểm VEQAS, trích xuất kết quả từng xét nghiệm và lưu thành mục riêng theo từng đợt.",
    )

    with st.container(border=True):
        st.markdown("#### :material/upload_file: Bước 1: Chọn file PDF kết quả ngoại kiểm (VEQAS)")
        uploaded_pdf = st.file_uploader(
            "Tải lên file PDF báo cáo phân tích kết quả ngoại kiểm (VD: VEQAS_BC20C_01_...pdf)",
            type=["pdf"],
            key="eqa_pdf_uploader",
        )

    if uploaded_pdf is not None:
        file_bytes = uploaded_pdf.getvalue()
        file_sig = f"{uploaded_pdf.name}_{len(file_bytes)}"

        if st.session_state.get("last_parsed_sig") != file_sig:
            with st.spinner("Đang bóc tách dữ liệu từ file PDF..."):
                parsed_data = parse_veqas_pdf(file_bytes, filename=uploaded_pdf.name)
                st.session_state["last_parsed_sig"] = file_sig
                st.session_state["parsed_eqa_data"] = parsed_data

        parsed_data = st.session_state.get("parsed_eqa_data")
        if parsed_data:
            meta = parsed_data["metadata"]
            results = parsed_data["results"]

            with st.container(border=True):
                st.markdown("#### :material/tune: Bước 2: Kiểm tra & Hiệu chỉnh thông tin Đợt Ngoại kiểm")
                col1, col2, col3, col4 = st.columns(4)
                batch_no_in = col1.text_input("Số Đợt (VD: 01)", value=meta.get("batch_no", "01"))
                month_year_in = col2.text_input("Kỳ Tháng/Năm (MM/YYYY)", value=meta.get("month_year", "01/2026"))
                prog_code_in = col3.text_input("Mã chương trình", value=meta.get("program_code", "BC20C"))
                prog_name_in = col4.text_input("Tên chương trình", value=meta.get("program_name", "Sinh hóa"))

                col5, col6, col7, col8 = st.columns(4)
                inst_in = col5.text_input("Thiết bị / Máy xét nghiệm", value=meta.get("instrument_name", ""))
                unit_code_in = col6.text_input("Mã đơn vị", value=meta.get("unit_code", ""))
                sample_code_in = col7.text_input("Mã mẫu ngoại kiểm", value=meta.get("sample_code", ""))
                default_label = f"Đợt {batch_no_in.strip()} - Tháng {month_year_in.strip()}"
                batch_label_in = col8.text_input("Tên mục lưu trong Database", value=default_label)

                notes_in = st.text_input(
                    "Ghi chú đợt ngoại kiểm (tùy chọn)",
                    placeholder="VD: Ngoại kiểm Sinh hóa đợt 1 tháng 01/2026 - Máy Abbott Alinity c...",
                )

                existing_id = check_batch_exists(
                    program_code=prog_code_in,
                    batch_no=batch_no_in,
                    month_year=month_year_in,
                    instrument_name=inst_in,
                    sample_code=sample_code_in,
                )
                overwrite_flag = False
                if existing_id is not None:
                    render_html(f"""
                    <div class="eval-result-box eval-result-fail" style="margin-bottom:8px;">
                        <span>⚠️ <b>Đợt {batch_no_in} - Tháng {month_year_in} ({prog_code_in} - {inst_in})</b> đã tồn tại trong Database (ID #{existing_id}).</span>
                        {format_status_badge_html('CẢNH BÁO TRÙNG')}
                    </div>
                    """)
                    overwrite_flag = st.checkbox(
                        "Cho phép ghi đè (cập nhật lại) dữ liệu của đợt này trong Database",
                        value=True,
                        key="chk_overwrite_batch",
                    )

            with st.container(border=True):
                st.markdown(f"#### :material/assignment: Bước 3: Xem trước {len(results)} xét nghiệm được bóc tách từ PDF")
                render_html(f"""
                <div class="search-result-pill">
                    Đã trích xuất thành công <b>{len(results)} thông số xét nghiệm</b> từ file <code>{uploaded_pdf.name}</code>
                </div>
                """)
                render_eqa_results_table(results, max_height=380)

                btn_col1, _ = st.columns([1.2, 3.8])
                with btn_col1:
                    if st.button(":material/save: Lưu vào Database", type="primary", use_container_width=True):
                        if not results:
                            queue_popup("Không có dữ liệu!", "Không tìm thấy thông số xét nghiệm nào trong file PDF.", "error")
                            st.rerun()
                        elif existing_id is not None and not overwrite_flag:
                            queue_popup(
                                "Đợt EQA đã tồn tại!",
                                "Vui lòng tích chọn 'Cho phép ghi đè' hoặc đổi tên Đợt / Tháng-Năm trước khi lưu.",
                                "warning",
                            )
                            st.rerun()
                        else:
                            final_meta = {
                                "batch_label": batch_label_in.strip(),
                                "batch_no": batch_no_in.strip(),
                                "month_year": month_year_in.strip(),
                                "program_name": prog_name_in.strip(),
                                "program_code": prog_code_in.strip(),
                                "unit_code": unit_code_in.strip(),
                                "instrument_name": inst_in.strip(),
                                "sample_code": sample_code_in.strip(),
                                "source_filename": uploaded_pdf.name,
                                "notes": notes_in.strip(),
                            }
                            saved_id = save_eqa_batch(
                                metadata=final_meta,
                                results=results,
                                overwrite_batch_id=existing_id if overwrite_flag else None,
                            )
                            queue_popup(
                                "Lưu Database thành công!",
                                f"Đã lưu mục '{batch_label_in}' ({len(results)} xét nghiệm - Máy {inst_in}) vào Database (ID #{saved_id}).",
                                "success",
                            )
                            st.rerun()


# ==============================================================================
# TRANG 3: TÍNH %BIAS THEO MỨC NỒNG ĐỘ (TỰ CHỌN THÁNG)
# ==============================================================================
elif page == "3. Tính %Bias (EQA)":
    render_bias_calculator_page()


# ==============================================================================
# TRANG 4: QUẢN LÝ & XUẤT DỮ LIỆU TỪNG ĐỢT EQA
# ==============================================================================
elif page == "4. Quản lý Đợt EQA":
    render_page_banner(
        "Quản lý Mục Ngoại kiểm & Xuất File",
        "Xem chi tiết từng mục ngoại kiểm đã lưu, xuất file CSV/Excel hoặc xóa đợt nhập nhầm.",
    )

    batches = get_all_batches()
    if not batches:
        with st.container(border=True):
            st.markdown("#### :material/storage: Database hiện đang trống")
            st.write("Vui lòng import file PDF ngoại kiểm tại mục **2. Import EQA PDF** trước.")
    else:
        with st.container(border=True):
            st.markdown("#### :material/folder_open: Chọn Mục Ngoại kiểm (Đợt / Tháng-Năm)")
            batch_map = {
                f"[#{b['id']}] {b['batch_label']} | {b['program_code']} - {b['instrument_name']} ({b['total_tests']} XN)": b
                for b in batches
            }
            sel_label = st.selectbox("Danh sách các mục EQA trong Database", list(batch_map.keys()), key="hist_sel_batch")
            sel_batch = batch_map[sel_label]
            sel_results = get_results_by_batch(sel_batch["id"])

            render_batch_meta_bar(sel_batch)
            render_eqa_results_table(sel_results, max_height=400)

            df_export = pd.DataFrame(sel_results)
            act1, act2, act3 = st.columns([1.2, 1.2, 2.6])

            csv_bytes = df_export.to_csv(index=False).encode("utf-8-sig")
            act1.download_button(
                ":material/download: Xuất CSV đợt này",
                data=csv_bytes,
                file_name=f"EQA_{sel_batch['program_code']}_Dot_{sel_batch['batch_no']}_{sel_batch['month_year'].replace('/', '-')}.csv",
                mime="text/csv",
                use_container_width=True,
            )

            excel_buf = io.BytesIO()
            with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
                df_export.to_excel(writer, index=False, sheet_name="EQA_Results")
            act2.download_button(
                ":material/table_view: Xuất Excel (.xlsx)",
                data=excel_buf.getvalue(),
                file_name=f"EQA_{sel_batch['program_code']}_Dot_{sel_batch['batch_no']}_{sel_batch['month_year'].replace('/', '-')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

            with act3:
                if st.button(":material/delete: Xóa đợt ngoại kiểm này", type="secondary"):
                    delete_batch(sel_batch["id"])
                    queue_popup(
                        "Đã xóa mục ngoại kiểm!",
                        f"Mục '{sel_batch['batch_label']}' đã được xóa khỏi Database.",
                        "error",
                    )
                    st.rerun()
