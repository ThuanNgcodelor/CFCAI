# Kiểm chứng bộ lệnh build — 2026-10-27

## Test tự động

```bash
./build/manage.sh test
# 17 tests OK — Docker giả lập, không chạm dữ liệu thật

.venv/bin/python -m pytest -q tests/unit/test_build_commands.py tests/unit/test_reset_conversations.py
# 19 passed, 5 subtests passed

.venv/bin/ruff check tests/unit/test_build_commands.py
# All checks passed!

bash -n build/manage.sh
git diff --check
# Exit 0
```

Kiểm tra: chạy từ thư mục khác/đường dẫn có khoảng trắng; không thực thi `.env`
như shell; giữ volume khi stop; recreate khi restart; bắt buộc xác nhận reset;
thiếu recipient hoặc worker thì từ chối; reset mặc định giới hạn sender test;
chỉ `--all --yes` mới xóa tất cả; dừng API/worker trước reset và phục hồi đúng
service cũ kể cả khi reset/stop lỗi; trả lỗi nếu phục hồi service thất bại.
Hai test reset hiện có kiểm tra thứ tự xóa handoff trước conversation và phạm vi sender.

## Kiểm tra môi trường thật, chỉ đọc

- `./build/manage.sh status`: API, PostgreSQL, Redis healthy; worker đang chạy.
- `./build/manage.sh check`: API health và Ollama `/api/tags` đều HTTP 200;
  delivery mode canary, canary scope và release fence PASS.
- Preflight **exit 2**: `admin_auth: BLOCKED` vì worker chưa có `ADMIN_API_TOKEN`.
  Đây là thiếu cấu hình staging/production, không phải bằng chứng Meta không gửi.

Không chạy start/stop/restart/reset thật trong lượt này; không xóa chat, không
gửi tin Meta, không đổi `.env`, không warm CRM. Các đường thao tác thay đổi trạng
thái mới được kiểm tra qua Docker giả lập, chưa phải rehearsal với Docker thật.
Báo cáo không thay thế test nội dung chatbot, test Messenger hay sign-off F1–F8.
