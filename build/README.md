# Bật/tắt dự án và tự test Meta Dev

Thư mục này chứa công cụ vận hành, không phải dữ liệu build sinh tự động.
Chạy các lệnh dưới đây từ thư mục gốc `CFCAI`. Script cũng chạy được từ nơi khác
nếu gọi bằng đường dẫn tuyệt đối. Cần Bash, Docker Compose v2, Docker daemon đang
chạy và tài khoản có quyền Docker. Không ghi mật khẩu máy hoặc token vào script.

## Các lệnh dùng hằng ngày

```bash
./build/manage.sh start         # Build và bật API, worker, PostgreSQL, Redis
./build/manage.sh status        # Xem cả container đang chạy và đã dừng
./build/manage.sh check         # Kiểm tra API, Ollama, cấu hình; không bật quyền gửi
./build/manage.sh logs          # Theo dõi API + worker; Ctrl+C chỉ thoát xem log
./build/manage.sh logs worker   # Chỉ xem worker
./build/manage.sh stop          # Tắt các service Compose, KHÔNG xóa volume
./build/manage.sh restart       # Build/recreate API + worker để nhận code/.env mới
```

`start`/`restart` dùng cấu hình gửi đang có trong `.env`, **không tự mở gửi** và
không reset hội thoại. Khi được bật, worker có thể xử lý tin đang chờ theo các
guard hiện hành. `restart` giữ PostgreSQL/Redis; muốn tắt/bật toàn bộ thì dùng
`stop` rồi `start`. Scheduler CRM tùy chọn không tự bật lại bởi `start`:

```bash
docker compose --profile scheduler up -d --build crm-scheduler
```

Ollama và tunnel webhook bên ngoài Compose không được khởi động/tắt bởi script.
Meta Dev vẫn cần webhook HTTPS đang truy cập được, Page đã đăng ký webhook và
tài khoản test hợp lệ. `check` thành công không chứng minh đã gửi được Messenger
hay model đã được tải: nó kiểm tra API health, endpoint Ollama `/api/tags` và một
số cấu hình preflight. Xem log và phản hồi thực tế để nghiệm thu.

`check` dùng preflight staging/production nên có thể trả mã lỗi 2 với
`admin_auth: BLOCKED` khi thiếu `ADMIN_API_TOKEN`, dù API/Ollama vẫn chạy.
Đây là cảnh báo bảo vệ API quản trị, không phải script vừa chặn Messenger.
Đọc từng mục kết quả; không công khai API quản trị khi chưa có xác thực.

## Xóa ngữ cảnh để bắt đầu cuộc hội thoại mới

Không gửi tin trong lúc reset. Mặc định dùng `META_TEST_RECIPIENT_ID` trong `.env`,
không cần chép PSID vào terminal. Thiếu ID thì lệnh từ chối, **không tự chuyển sang
xóa toàn bộ**. API/worker phải được start trước; script tạm dừng các service này
để tránh xử lý đồng thời, sau đó khởi động lại đúng những service vốn đang chạy.
Webhook có thể tạm lỗi và Meta có thể gửi lại sự kiện trong khoảng dừng.

```bash
./build/manage.sh reset-chat --yes
```

Xóa inbox/outbox, lịch sử, slots, batches và handoff tasks/events của sender test
qua công cụ reset hiện có, theo thứ tự khóa ngoại. Giữ CRM snapshot, catalog,
FAQ đã duyệt và audit vận hành. Reset không đổi pause/kill switch cấp Page,
allowlist hay quyền gửi. Redis không bị flush; lịch debounce cũ không phải nguồn
lịch sử hội thoại (PostgreSQL mới là nguồn thật).

Chỉ khi chủ động muốn xóa **mọi hội thoại trên cả CFC và ZEO**:

```bash
./build/manage.sh reset-chat --all --yes
```

Không có undo trong script; cần bản backup trước đó nếu muốn khôi phục dữ liệu
đã xóa (xem [runbook](../docs/GO_LIVE_RUNBOOK.md)). Đây là xóa trí nhớ phía bot,
**không xóa bong bóng chat trên Messenger/Facebook**. Nếu cần, xóa cuộc chat trong
giao diện Messenger riêng. PSID là page-scoped; ID test CFC không dùng thay ID ZEO.

## Một lượt tự test mới

```bash
./build/manage.sh start
./build/manage.sh check
./build/manage.sh reset-chat --yes
./build/manage.sh logs
```

Gửi tin mới từ tài khoản Meta Dev đúng `META_TEST_RECIPIENT_ID`. Cấu hình canary
phải cho phép đúng Page, recipient và workflow; không xóa guard quyền gửi hoặc
ownership để làm test pass. Đợi hết debounce và thời gian model xử lý trước khi
gửi lại. Reset giữa các nhóm độc lập, nhưng **không reset giữa các lượt** của cùng
kịch bản kiểm tra trí nhớ.

| Nhóm | Tin nhắn / thao tác | Kết quả cần kiểm tra |
| --- | --- | --- |
| Chào | `Xin chào` | Chào bằng anh/chị; không tự tạo yêu cầu nhân viên. |
| Đại lý | `Tôi muốn tìm đại lý gần nhất` → gửi địa chỉ → phản hồi lại kết quả | Hỏi địa chỉ khi chưa có; không lấy địa chỉ từ đợt trước. Chỉ nêu 2–3 điểm nếu có đủ record phù hợp, không bịa cho đủ số. Không gọi gần nhất nếu thiếu căn cứ GPS. |
| Sản phẩm | `Tôi muốn tìm mua Hữu cơ Cobanic 21` | Đúng sản phẩm có nguồn; nếu mơ hồ thì hỏi lại, không xổ danh sách không liên quan. |
| Giá / liên hệ | `Xin giá` → cung cấp nhu cầu và số điện thoại test | Không tự báo giá, không placeholder, không xác nhận có số khi khách chưa cung cấp; handoff phải tồn tại mới xác nhận đã tạo. |
| Ngữ cảnh | `Tư vấn cách dùng` → `bón cho mít` → `giai đoạn nuôi trái` | Giữ cây/giai đoạn; không hỏi lại cây đã biết, không tự đổi sang khuyến cáo khác. |
| Ảnh | Gửi ảnh vườn kèm `vườn anh nè nên mua phân bón gì` | Nhận biết có attachment, hỏi thông tin còn thiếu; không tự nhận đã chẩn đoán ảnh hoặc tìm mã sản phẩm không có căn cứ. |
| Không có dữ liệu | Hỏi một sản phẩm / địa chỉ ngoài nguồn | Nói chưa xác nhận, không bịa tên, giá, thời hạn gọi hoặc lộ `snapshot CRM`. |

Nếu không thấy trả lời: xem `status`, `check`, log API có nhận webhook không,
log worker có xử lý không; kiểm tra pause/ownership, canary và trạng thái outbox.
`SENT` là Meta Send API đã trả message ID; `SUPPRESSED` là bị guard chặn,
`FAILED` là gửi lỗi. Không replay các row cũ để thử lại. Không công khai log có
số điện thoại/token. Ghi thời điểm, nhóm test, câu trả lời thực tế và lỗi vào
`docs/test_runs/`. Xem [ma trận Meta Dev](../docs/META_DEV_SELF_TEST.md) để test thêm.

## Kiểm tra bộ lệnh (không gửi tin, không xóa dữ liệu thật)

```bash
./build/manage.sh test
```

Chỉ cần Python 3. Test dùng Docker giả lập để kiểm tra tham số, xác nhận reset,
từ chối thiếu recipient, giữ volumes và phục hồi service khi lỗi. Đây **không phải**
test chất lượng chatbot hay nghiệm thu F1–F8; vẫn phải test Meta theo bảng trên.

## Cập nhật dữ liệu độc lập với restart

Nguồn file ở `data/sources/`, khai báo trong `data/sources/manifest.yaml`.
FAQ CFC: `data/sources/cfc/faq/CFC_Co_Bay_FAQ.md`. Restart không tự duyệt nội dung.

```bash
docker compose --profile data run --rm --build data-loader validate --all
docker compose --profile data run --rm --build data-loader stage --changed --actor manual-test
docker compose --profile data run --rm --build crm-warmer sync
```

Hai lệnh đầu validate/stage file; stage vẫn `QUARANTINED`, cần review/approve/publish.
Lệnh cuối gọi CRM thật để warm snapshot Redis, cần credential hợp lệ; không tự
chạy khi start/reset. Xem [quy trình dữ liệu](../docs/knowledge_sources.md).
Không dùng `docker compose down -v`, `FLUSHALL` hoặc xóa volume để bắt đầu test mới.
