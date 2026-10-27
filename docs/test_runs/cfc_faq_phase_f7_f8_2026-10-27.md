# F7/F8 — Operations, security và release controls

Ngày: 27/10/2026  
Trạng thái: **AUTOMATED PASS / PRODUCTION BLOCKED**

## Phạm vi đã triển khai

| Hạng mục | Bằng chứng code/test |
|---|---|
| Admin auth/RBAC | `ADMIN_API_TOKEN` break-glass và `ADMIN_ROLE_TOKENS_JSON` theo role; test operator không truy cập catalog |
| Kill switch/takeover | pause/resume page-scoped, takeover/resume conversation, audit và outbox/batch suppression |
| Handoff operations | list/claim/resolve page-scoped, idempotent state validation và `ops_audit_log` |
| Shadow/canary | mode disabled mặc định; shadow record/suppress; canary giới hạn page/workflow/recipient/rate bằng config và `DELIVERY_NOT_BEFORE` chặn outbox cũ |
| PII/secret | logging redactor, API CRM không trả exception thô, test phone/token masking |
| Recovery | migration `009`, backup script, restore cần `--confirm-restore`, preflight read-only, runbook |

## Lệnh và kết quả

```text
INBOX_BACKEND=memory .venv/bin/pytest -q tests/integration/test_ops_controls.py
6 passed, 1 warning

RUN_CFC_FAQ_EVAL=1 .venv/bin/pytest -q
292 passed, 4 skipped, 1 warning
```

Warning còn lại là `StarletteDeprecationWarning` từ FastAPI TestClient/httpx,
không phải assertion failure hay security bypass.

## Điều kiện chưa được phép đánh dấu PASS production

1. Shadow traffic thật cần chạy theo khoảng quan sát do chủ hệ thống chấp thuận,
   sau đó review evidence trong `delivery_shadow_reviews`.
2. Canary/Meta Send API chỉ cấu hình sau business sign-off; code không tự chuyển
   từ `disabled` sang mode khác.
3. Cần backup/restore drill thực tế có hai người xác nhận; restore chưa chạy vì
   là thao tác phá hủy dữ liệu.
4. Cần Meta webhook production và Ollama model readiness test tại môi trường phát
   hành, cùng SLA notification channel/assignment policy của đội vận hành.

Vì bốn điều kiện này là phụ thuộc môi trường/quyền kinh doanh, không được thay
bằng unit test hoặc ghi là đã hoàn tất.
