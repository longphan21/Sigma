# 🔬 Six Sigma & Westgard QC Management System

Ứng dụng web xây dựng bằng **Streamlit** hỗ trợ phòng xét nghiệm y khoa tự động hóa quy trình quản lý **Bias% (Ngoại kiểm — EQA)**, **TEa% (đa nguồn theo từng máy)**, **CV% cộng dồn (Nội kiểm — IQC theo LOT)**, tính toán chỉ số **Six Sigma ($\sigma$)**, lựa chọn **Quy tắc Westgard (Westgard Sigma Rules)** và xuất báo cáo **Excel (`.xlsx`)** phân màu trực quan phục vụ hồ sơ chất lượng theo **ISO 15189** và **Quyết định 2429/QĐ-BYT**.

---

## ✨ Tính năng chính

### 1. Tính toán Bias% từ Ngoại kiểm (EQA) — `bias_calculator.py`
* Hỗ trợ trích xuất dữ liệu trực tiếp từ báo cáo **PDF ngoại kiểm (EQA)** và cho phép nhập/hiệu chỉnh nhanh kết quả.
* Tự động tính toán sai số hệ thống ($\text{Bias}\%$) so với giá trị đích / trung bình nhóm đồng đẳng (Peer Group Mean) và lưu lịch sử theo từng đợt EQA.

### 2. Quản lý TEa% đa nguồn theo thiết bị — `tea_manager.py`
* Chuẩn hóa và lưu trữ danh mục **Sai số toàn bộ cho phép ($\text{TEa}\%$)** từ nhiều nguồn tham chiếu (CLIA, EFLM/Ricos, RiliBÄK, quy định nội bộ...).
* Cho phép cấu hình $\text{TEa}\%$ riêng biệt cho **từng xét nghiệm trên từng dòng máy phân tích**, đảm bảo đồng bộ khi đưa vào công thức tính Sigma.

### 3. Quản lý CV% cộng dồn theo LOT nội kiểm — `cv_manager.py`
* Theo dõi và tổng hợp **Hệ số biến thiên cộng dồn ($\text{CV}\%$)** theo từng mức nồng độ và từng **LOT mẫu nội kiểm (IQC)**.
* Tự động đồng bộ dữ liệu $\text{CV}\%$ mới nhất sang phân hệ tính toán Six Sigma.

### 4. Tính toán Six Sigma & Đề xuất Quy tắc Westgard — `sigma_calculator.py`
* Tự động ghép nối $\text{TEa}\%$, $\vert{}\text{Bias}\%\vert{}$ và $\text{CV}\%$ theo từng chỉ tiêu, máy phân tích và mức nồng độ để tính điểm Sigma:
  $$\sigma = \frac{\text{TEa}\% - \vert{}\text{Bias}\%\vert{}}{\text{CV}\%}$$
* Tự động phân loại chất lượng xét nghiệm và đề xuất **Quy tắc Westgard (Westgard Sigma Rules)** cùng tần suất chạy QC tương ứng.
* **Xuất báo cáo Excel (`.xlsx`) định dạng màu tự động**: Bảng tổng hợp được tô màu trực quan theo từng mức phân hạng Sigma, sẵn sàng in ấn và lưu hồ sơ đánh giá chất lượng định kỳ.

### 5. Giao diện & Trải nghiệm vận hành — `ui_theme.py`
* **Tông màu xanh lá nhạt tối giản**: Thiết kế sạch, dễ đọc số liệu khi làm việc liên tục tại phòng xét nghiệm.
* **State Persistence (`session_state` & `persistent_selectbox`)**: Giữ nguyên toàn bộ lựa chọn và số liệu đang thao tác sau khi lưu dữ liệu hoặc chuyển đổi giữa các tab.
* **Step-by-Step Locking**: Hỗ trợ khóa thông tin đầu vào theo từng bước để tránh chọn nhầm khi nhập liên tiếp nhiều chỉ tiêu.
* **Tối ưu đa thiết bị**: Tự động điều chỉnh bố cục cho cả **Máy tính (Desktop)** và **Điện thoại (Mobile)**.
* **Cơ sở dữ liệu Google Sheets (`connection.py`)**: Đồng bộ dữ liệu thời gian thực lên đám mây, dễ dàng tra cứu, sao lưu và chia sẻ giữa các nhân sự trong khoa.

---

## 📊 Bảng phân hạng Six Sigma & Quy tắc Westgard tham chiếu

| Mức Sigma ($\sigma$) | Phân loại chất lượng | Quy tắc Westgard đề xuất | Màu hiển thị Excel |
| :--- | :--- | :--- | :--- |
| **$\sigma \ge 6$** | World Class (Đẳng cấp thế giới) | $1_{3s}$ ($N=2, R=1$) | Xanh lá đậm |
| **$5 \le \sigma < 6$** | Excellent (Xuất sắc) | $1_{3s} / 2_{2s} / R_{4s}$ ($N=2, R=1$) | Xanh lá nhạt |
| **$4 \le \sigma < 5$** | Good (Tốt) | $1_{3s} / 2_{2s} / R_{4s} / 4_{1s}$ ($N=4, R=1$ hoặc $N=2, R=2$) | Vàng nhạt |
| **$3 \le \sigma < 4$** | Marginal (Cận biên) | $1_{3s} / 2_{2s} / R_{4s} / 4_{1s} / 8_x$ ($N=4, R=2$ hoặc $N=8, R=1$) | Cam |
| **$\sigma < 3$** | Unacceptable (Không đạt) | Cần rà soát lại phương pháp, hiệu chuẩn, bảo trì hoặc cải thiện độ chụm/độ đúng | Đỏ nhạt |

---

## 🗂️ Cấu trúc thư mục dự án

```text
.
├── app.py                 # Điểm khởi chạy chính, điều hướng phân hệ & trạng thái phiên làm việc
├── bias_calculator.py     # Xử lý dữ liệu EQA (bóc tách PDF / nhập liệu) và tính toán Bias%
├── tea_manager.py         # Quản lý danh mục TEa% đa nguồn theo từng máy phân tích
├── cv_manager.py          # Quản lý CV% cộng dồn theo từng LOT và mức nồng độ nội kiểm
├── sigma_calculator.py    # Tính toán Six Sigma, đề xuất Westgard Rules & xuất file Excel phân màu
├── connection.py          # Module kết nối Google Sheets API qua Service Account
├── ui_theme.py            # Cấu hình giao diện xanh lá nhạt, responsive CSS & persistent widgets
├── requirements.txt       # Danh sách thư viện Python phụ thuộc
└── README.md              # Tài liệu mô tả dự án
```

---

## ⚙️ Hướng dẫn cài đặt & chạy cục bộ

### 1. Yêu cầu môi trường
* Python **3.9** trở lên.
* Tài khoản Google Cloud đã bật **Google Sheets API** & **Google Drive API** kèm file khóa JSON của **Service Account** (đã chia sẻ quyền **Editor** vào file Google Sheets lưu dữ liệu).

### 2. Cài đặt thư viện
```bash
git clone <url-repository-cua-ban>
cd <thu-muc-du-an>
pip install -r requirements.txt
```

### 3. Cấu hình Secrets
Tạo file `.streamlit/secrets.toml` tại thư mục gốc dự án với cấu trúc tương ứng trong `connection.py`:

```toml
[gcp_service_account]
type = "service_account"
project_id = "your-project-id"
private_key_id = "your-private-key-id"
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "your-service-account@your-project.iam.gserviceaccount.com"
client_id = "your-client-id"
auth_uri = "[https://accounts.google.com/o/oauth2/auth](https://accounts.google.com/o/oauth2/auth)"
token_uri = "[https://oauth2.googleapis.com/token](https://oauth2.googleapis.com/token)"
auth_provider_x509_cert_url = "[https://www.googleapis.com/oauth2/v1/certs](https://www.googleapis.com/oauth2/v1/certs)"
client_x509_cert_url = "your-cert-url"

[connections.gsheets]
spreadsheet = "[https://docs.google.com/spreadsheets/d/](https://docs.google.com/spreadsheets/d/)<SPREADSHEET_ID>/edit"
```

### 4. Khởi chạy ứng dụng
```bash
streamlit run app.py
```

---

## ☁️ Triển khai trên Streamlit Community Cloud

1. Đẩy mã nguồn lên GitHub (lưu ý **không** commit thư mục `.streamlit/secrets.toml` — thêm vào `.gitignore`).
2. Truy cập [Streamlit Community Cloud](https://share.streamlit.io/) $\rightarrow$ chọn **New app** $\rightarrow$ chọn repository, nhánh `main` và file chạy `app.py`.
3. Vào **Advanced settings → Secrets**, dán nội dung cấu hình `secrets.toml` ở bước trên rồi bấm **Deploy**.

---

## 📚 Tài liệu tham chiếu

* **Westgard QC**: *Westgard Sigma Rules* — Lựa chọn quy tắc nội kiểm chất lượng dựa trên thang đo Six Sigma.
* **ISO 15189**: *Medical laboratories — Requirements for quality and competence*.
* **Quyết định 2429/QĐ-BYT**: *Tiêu chí đánh giá mức chất lượng phòng xét nghiệm y học* (Bộ Y tế Việt Nam).