# Báo cáo triển khai và tự test CFC FAQ — Phase F1/F2

Ngày chạy: 26/10/2026  
Phạm vi: source governance, data source bootstrap, import lifecycle và CRM warmer.

## Kết luận

| Phase | Kết quả | Ghi chú |
|---|---|---|
| F1 — Làm sạch và quản trị FAQ | **PASS — safe scope** | Dữ liệu chưa được nghiệp vụ/chuyên gia duyệt vẫn inactive |
| F2 — Import/publish/rollback và CRM warm | **PASS — technical gate** | FAQ đã stage, chưa approve/publish |

Không có nội dung FAQ Markdown mới nào tự động đi vào câu trả lời production.

## F1 — Kết quả dữ liệu

- 47/47 dòng có governance metadata ngoài code.
- 44 dòng có đáp án và được stage hợp lệ.
- 3 dòng thiếu đáp án (`004`, `017`, `019`) được giữ inactive và không import.
- 44/44 đáp án có sẵn không còn gọi khách là `bạn`, không còn `admin` hoặc
  `chúng tôi` trong persona customer-facing.
- 8 workflow record ít rủi ro được đánh dấu `source_active=true`.
- Các thông tin công ty/sản phẩm/chính sách chưa xác nhận và toàn bộ claim nông
  học cần chuyên môn vẫn `source_active=false`.
- Fixture được sinh lại từ nguồn, schema version 2; mỗi case thể hiện intent,
  category, response mode, required slots, review status và active status.

## F2 — Kết quả dữ liệu file

Nguồn đã chuyển sang:

```text
data/sources/manifest.yaml
data/sources/cfc/faq/CFC_Co_Bay_FAQ.md
data/sources/cfc/catalog/CfcCoBayN8n.xlsx
data/sources/zeo/catalog/ZeoN8n.xlsx
```

Data loader validation:

| Source | Page | Records | Conflicts |
|---|---:|---:|---:|
| `cfc-faq` | CFC | 44 | 0 |
| `cfc-excel` | CFC | 47 | 0 |
| `zeo-excel` | ZEO | 154 | 0 |

Batch FAQ thật đã tạo:

- Batch ID: `d58062756b21c8da2ec8c4c19492df2636b6d526cbefc3416aed16c1058e4741`
- Trạng thái: `QUARANTINED`
- Actor audit: `codex-phase-f2`
- Chạy stage lần hai: `UNCHANGED`; không tạo batch/record trùng.
- Không approve và không publish.
- Publication CFC/ZEO đang hoạt động trước đó được giữ nguyên.

## F2 — Kết quả CRM warmer

Một lượt warm thật đã hoàn tất qua CLI riêng:

- Dealers/locations: 422.
- Dealers có GPS: 0.
- Products: 942.
- Eligible orders: 7.913.
- Customers/loyalty: 5.000.
- Current snapshot: `4424fc33e4dfc395-c6369d99cae1b103`.
- Status đọc lại từ process mới: `stale=false`.
- Distributed lock được giải phóng sau sync.

Do CRM hiện có 0 tọa độ GPS, dealer workflow chỉ được dùng exact address/địa
giới đủ căn cứ; không được gọi một record bất kỳ là “gần nhất”.

## Automated test evidence

### Targeted F1/F2

- Unit/source/data/CRM: **15 passed**.
- PostgreSQL integration loader/import/publish/rollback: **7 passed**.
- Unit + default FAQ eval gate: **48 passed, 119 skipped**. Phần 119 retrieval
  full gate thuộc F4 nên mặc định chưa bật ở F1/F2.
- Ruff trên toàn bộ file thay đổi: **PASS**.
- Docker Compose config validation: **PASS**.

### Zero-regression

```text
103 passed, 123 skipped, 1 warning
```

Warning còn lại là cảnh báo deprecation giữa FastAPI TestClient/httpx, không làm
test fail và không liên quan data lifecycle.

Hai integration fixture dùng event ID theo PID trước đây đã được đổi sang UUID,
để chạy lặp trên PostgreSQL bền vững không tạo false failure.

## Lệnh vận hành sau bàn giao

```bash
# Validate, không ghi DB
docker compose --profile data run --rm data-loader validate --all

# Stage duy nhất các file thay đổi
docker compose --profile data run --rm data-loader stage --changed --actor <ten-admin>

# Xem batch
docker compose --profile data run --rm data-loader status --page CFC

# CRM warm thủ công / đọc trạng thái
docker compose --profile data run --rm crm-warmer sync
docker compose --profile data run --rm crm-warmer status

# Chạy scheduler CRM định kỳ
docker compose --profile scheduler up -d crm-scheduler
```

Approve/publish FAQ phải chờ xem record diff và ký duyệt nghiệp vụ; restart
container hoặc chạy stage không thể tự publish.

## Việc chờ ký duyệt trước khi publish FAQ

1. Bổ sung đáp án dòng 4, 17 và 19.
2. Xác nhận giờ làm việc, địa chỉ, giới thiệu công ty và chính sách giao nhận.
3. Đối chiếu các tuyên bố sản phẩm với catalog chính thức.
4. Chuyên gia nông học duyệt các hướng dẫn, liều lượng, tỷ lệ và khẳng định mạnh.

Các mục này không làm gate kỹ thuật F1/F2 fail vì chúng đang bị fail-closed;
chúng chỉ chặn việc publish các record tương ứng.
