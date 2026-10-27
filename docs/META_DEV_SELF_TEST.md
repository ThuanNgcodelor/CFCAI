# Meta Development self-test — CFC

Tài liệu này dành cho tài khoản Meta Developer/tester. Đây không phải runbook
production và không được dùng để mở gửi cho khách thật.

## Phạm vi test hiện tại

| Kiểm soát | Giá trị test |
| --- | --- |
| Page gửi | `CFC` |
| Delivery | `canary`, 100% |
| Workflow | Toàn bộ `WorkflowType` của CFC |
| Người nhận | Chỉ `META_TEST_RECIPIENT_ID` trong `.env` |
| Production live | `LIVE_SEND_APPROVED=false` |

Ba hàng cuối không phải là trở ngại cho tài khoản test đã cấu hình. Không xóa
allow-list người nhận, page isolation, zero-price policy hoặc ownership guard:
đó là các bất biến cần được chính lượt test F1–F8 kiểm chứng.

Mỗi tin có debounce tối đa khoảng 5 giây. Chỉ kiểm tra các tin gửi **sau** khi
service đã được rebuild; hàng outbox cũ có trạng thái `SUPPRESSED` không được
phát lại vì có thể sai ngữ cảnh.

Test route operations dùng control store in-memory; test suite không được phép
pause Redis control của CFC thật.

## Bắt đầu một lượt test sạch

```bash
docker compose --profile app up -d --build --force-recreate api worker
docker compose exec -T worker python apps/tools/reset_conversations.py --sender-id <CFC_TEST_PSID>
docker compose ps
docker compose logs -f api worker
```

Lấy `<CFC_TEST_PSID>` từ `META_TEST_RECIPIENT_ID` trong `.env`. Lệnh reset chỉ
xóa history/slot/batch/outbox/handoff của PSID đó; không xóa CRM snapshot,
catalog, FAQ hoặc audit log.

Sau mỗi tin, kiểm tra trạng thái delivery mà không in nội dung khách hàng:

```bash
docker compose exec -T postgres sh -c \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -P pager=off -c
  "SELECT created_at, page_id, payload->>''workflow'' AS workflow, status, sent_at,
  COALESCE(failure_code, ''-'') AS failure_code
  FROM outbox_messages ORDER BY created_at DESC LIMIT 10;"'
```

`SENT` nghĩa là Meta Send API đã trả `message_id`. `FAILED` cần xem log worker.
`SUPPRESSED` với một tin mới nghĩa là phải kiểm tra ownership, pause/kill switch
hoặc cấu hình canary; không gửi lại row cũ.

## Ma trận tự test F1–F8

| Mục | Thao tác qua Meta Dev | Kết quả phải thấy |
| --- | --- | --- |
| F1 — Webhook/inbox | Gửi `Xin chào`. | API nhận webhook; bot chào lại bằng `anh/chị`, outbox `SENT`, không tạo handoff. |
| F2 — Context/batch | Trong dưới 5 giây gửi: `Tôi cần giá Cobanic 21`, `1 tấn`, `Cần Thơ`. | Một phản hồi logic, giữ được product/quantity/location; không có giá tự bịa. |
| F3 — Catalog | Gửi tên/SKU CFC có trong danh mục, rồi gửi một tên không có. | Item xác nhận phải thuộc CFC và approved; tên không rõ phải hỏi lại, không đoán. |
| F4 — Intent/slots | Gửi `HC vs 25kg 30% nhiều tấn`, `xin giá`, và câu nông học viết tắt/sai chính tả. | Giá đi vào handoff; model giữ intent/slot có căn cứ và fallback ngắn khi không chắc. |
| F5 — Workflows | Lần lượt test tìm sản phẩm, `Tôi muốn tìm đại lý gần nhất`, cung cấp tỉnh/huyện, `Hướng dẫn bón cho mít`, rồi gửi 1–2 ảnh vườn kèm caption xin tư vấn. | Product/dealer/nông học đi đúng luồng; ảnh được ghi nhận dù có caption và không rơi vào catalog no-match; dealer không tự gọi một điểm chưa xác nhận là gần nhất. |
| F6 — Retrieval | Hỏi một FAQ có trong nguồn, một câu paraphrase, và câu ngoài dữ liệu. | Chỉ dùng knowledge approved, đúng page; câu ngoài dữ liệu phải clarify/handoff, không bịa. |
| F7 — Operations | Trong Meta Business Suite takeover cuộc hội thoại rồi nhắn tiếp; dùng admin token để pause/resume CFC nếu có. | Sau takeover/pause bot không gửi; resume mới cho auto-reply lại. |
| F8 — Regression/safety | Gửi câu hỏi giá rõ ràng, gửi trùng một tin, và test CFC không lấy SKU ZEO. | Không có giá, không duplicate logical reply, không rò dữ liệu chéo Page. |

Để test ZEO qua Meta, phải dùng PSID test riêng của ZEO (PSID là page-scoped)
và cấu hình Page/recipient riêng; không tái sử dụng giả định PSID CFC.

## Evidence tự động đã chạy trên image mới — 2026-10-27

```text
Intent/workflow + T01–T12 regression: 74 passed
Default full suite: 190 passed, 137 opt-in skipped
Full FAQ-enabled suite (RUN_CFC_FAQ_EVAL=1): 309 passed, 18 skipped
Live Ollama/Qwen intent gate (RUN_LIVE_OLLAMA_EVAL=1): 20 passed
```

`pytest -q` mặc định có các skip có chủ đích cho FAQ variants và live-Qwen; các
gate đầy đủ đã được chạy riêng và pass như evidence nêu trên.

## Giới hạn trung thực

Lượt Meta Dev này là pilot CFC, không là production sign-off. Theo `ROADMAP.md`,
vẫn còn bằng chứng vận hành cần hoàn thiện: live Business Suite takeover trên cả
CFC/ZEO, SLA notification/rehearsal, shadow/restore drill và business sign-off.
Ảnh được ghi nhận là attachment; bot không được khẳng định đã chẩn đoán pixel
của ảnh nếu chưa có pipeline vision được triển khai.
