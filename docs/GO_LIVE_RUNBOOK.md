# Runbook shadow, canary, rollback và phục hồi

Tài liệu này là quy trình vận hành; không lệnh nào ở đây tự bật trả lời thật.
Chỉ operator được ủy quyền, sau business sign-off, mới được thay đổi biến môi
trường delivery hoặc gọi `/admin` với `X-Admin-Token`.

## 1. Preflight

1. Chạy full regression và F6 evaluation, rồi lưu report cùng ngày phát hành.
2. Tạo backup và kiểm tra file tồn tại:

   ```bash
   bash scripts/backup_postgres.sh
   ```

3. Kiểm tra cấu hình và health, không gửi Messenger:

   ```bash
   python scripts/verify_go_live.py
   ```

4. Đảm bảo `ADMIN_API_TOKEN` là secret mới, không phải giá trị trong
   `.env.example`; `/admin` phải trả `403` khi thiếu/sai `X-Admin-Token`.
5. Xác minh FAQ version active và version rollback bằng `data-loader status`.

## 2. Shadow (bắt buộc trước canary)

Đặt `DELIVERY_MODE=shadow`. `META_SEND_ENABLED` có thể để `false`: pipeline vẫn
tạo outbox, dispatcher sẽ chuyển ứng viên sang `SUPPRESSED` và ghi evidence vào
`delivery_shadow_reviews`; không có gọi Meta Send API.

Sau khoảng quan sát đã thống nhất, operator xem metadata:

```bash
curl -sS -H "X-Admin-Token: <secret>" \
  "http://localhost:8000/admin/shadow-reviews?page_id=CFC"
```

Chỉ dùng `include_text=true` trong phiên review đã được cấp quyền. Đối chiếu
output với case FAQ/nhân viên, đồng thời xem `/admin/ops/summary` cho outbox,
handoff và count shadow. Nếu có lỗi safety, giữ `disabled`, sửa và replay lại.

## 3. Canary

Canary phải được khai báo bằng cấu hình, không sửa Python:

```dotenv
META_SEND_ENABLED=true
DELIVERY_MODE=canary
CANARY_PAGE_IDS=CFC
CANARY_WORKFLOWS=FAQ_ANSWER
CANARY_PERCENT=<small approved percent>
CANARY_SEND_APPROVED=true
# Set immediately before rollout; older PENDING outbox rows remain unsendable.
DELIVERY_NOT_BEFORE=<ISO-8601 timestamp with UTC offset>
```

`CANARY_RECIPIENT_IDS` là allow-list tùy chọn cho pilot kín. Bất kỳ message nào
ngoài page/workflow/phần trăm đã cấu hình đều bị suppress, không được gửi muộn
khi thay mode. Product/dealer chỉ được thêm vào `CANARY_WORKFLOWS` sau khi có
evidence; nông học cần chuyên gia duyệt riêng.

## 4. Emergency stop và takeover

```bash
# Pause chỉ page CFC, có audit; worker dừng tạo auto-reply mới.
curl -X POST -H "X-Admin-Token: <secret>" -H "X-Operator-Id: <operator>" \
  http://localhost:8000/admin/ops/CFC/pause

# Takeover một cuộc hội thoại: hủy batch/open outbox AI trong cùng transaction.
curl -X POST -H "X-Admin-Token: <secret>" \
  -H 'Content-Type: application/json' \
  -d '{"actor":"<operator>","reason":"human support"}' \
  http://localhost:8000/admin/conversations/CFC/<conversation_id>/takeover
```

Sau incident, xem `/admin/ops/audit` và chỉ resume khi người phụ trách xác nhận.

## 5. FAQ rollback và database restore

FAQ rollback không đòi restore database:

```bash
curl -X POST -H "X-Admin-Token: <secret>" \
  http://localhost:8000/admin/catalog/publications/CFC/<known_version>/rollback
```

Restore database chỉ dùng khi hỏng dữ liệu nghiêm trọng, sau khi dừng `api` và
`worker`, có backup mới và một người thứ hai xác nhận file đích:

```bash
docker compose --profile app stop api worker
bash scripts/restore_postgres.sh --confirm-restore backups/<known_file>.dump
docker compose --profile app up -d api worker
```

Sau restore phải chạy lại health, migration idempotent, F6 gate tối thiểu và
kiểm tra `ops/status` trước khi đổi bất kỳ delivery mode nào.

## 6. Điều kiện mở rộng / dừng phát hành

Không mở rộng khi còn price leak, page leak, duplicate, send sau takeover,
output guard rejection bất thường, outbox `FAILED`, CRM stale hoặc shadow review
chưa được chấp nhận. Production final gate vẫn cần Meta webhook thật, backup
restore drill có log và business sign-off; các điều kiện ngoài hệ thống này
không thể được unit test thay thế.
