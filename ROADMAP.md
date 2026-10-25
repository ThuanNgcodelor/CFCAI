# CFC–ZEO AI Platform — Implementation Roadmap & Phase Gatekeeper

> Tài liệu này dùng để theo dõi tiến độ chính xác của dự án và làm căn cứ nghiệm thu (Gatekeeper) trước khi chuyển phase.  
> **Nguyên tắc:** Một phase chỉ được tích `[x]` khi toàn bộ Tiêu chí hoàn thành (Definition of Done) và Automated Test tương ứng đã PASS.

---

## Tổng quan tiến độ

- [x] **Phase 0: Foundation, Architecture Contracts & Test Fixtures (COMPLETED)**
- [ ] **Phase 1: Meta Webhook Ingestion & Durable Inbox (PARTIAL — unit-only; Postgres inbox chưa triển khai)**
- [ ] **Phase 2: Message Aggregation (Debounce) & Handoff State Guard**
- [ ] **Phase 3: Excel Catalog & FAQ Staging Pipeline (PARTIAL — unit-only; chưa có integration gate/publish DB)**
- [ ] **Phase 4: Qwen 8B Understanding (Structured Intent & Entity Extraction)**
- [ ] **Phase 5: Business Workflows & Final Send Outbox Guard**
- [ ] **Phase 6: Approved Knowledge Retrieval & FAQ RAG**
- [ ] **Phase 7: Operations Console & Emergency Controls (Kill Switch)**
- [ ] **Phase 8: Security Hardening, Regression Verification & Production Go-Live**
- [ ] **Integration: MISA AMIS CRM Python Warmer (PARTIAL — code/unit test có, chưa kiểm chứng endpoint thật)**

### Evidence audit — 25/10/2026

Đây là trạng thái dựa trên artefact và lệnh kiểm tra thực tế trong workspace, không dựa trên giả định triển khai:

| Hạng mục | Bằng chứng hiện có | Kết luận |
|---|---|---|
| Phase 0 | `pytest tests/unit/test_contracts.py` — 5 passed | Đạt phần test gate hiện có |
| Phase 1 | Unit test Meta pass; `durable_inbox` hiện là `set`/`dict` trong process, chưa phải Postgres; integration test được khai báo nhưng chưa tồn tại | Chưa đạt DoD |
| Phase 2 | Domain debounce/state/final-send guard đã có test integration cơ bản; chưa có worker/Redis/Postgres adapter | Đang triển khai |
| Phase 3 | Excel reader/importer unit test có; chưa có integration test theo gate và chưa có publish/rollback read model | Chưa đạt DoD đầy đủ |
| Phase 8 | `tests/eval/test_regression_full.py` chưa tồn tại; Docker daemon chưa sẵn sàng; Ollama model chưa có | Chưa được xác minh |
| MISA | Client/warmer và unit test có; chưa có contract test/endpoint thật/secret runtime | Chưa được xác minh production |

Không được đổi `[ ]` thành `[x]` chỉ vì code hoặc fixture tồn tại. Mỗi phase cần lệnh gate, regression của phase trước và bằng chứng môi trường tương ứng.

---

## Chi tiết từng Phase & Tiêu chí nghiệm thu (Definition of Done)

### Phase 0: Foundation, Architecture Contracts & Test Fixtures
- [x] Dựng toàn bộ khung xương Modular Monolith theo Mục 4 tài liệu kiến trúc.
- [x] Khởi tạo `docker-compose.yml` gồm PostgreSQL 16 (`pgvector`) và Redis 7.
- [x] Khởi tạo file cấu hình trang `config/pages/cfc.yaml` và `config/pages/zeo.yaml`.
- [x] Viết toàn bộ Pydantic schemas và contracts cho:
  - Events: `InboxEvent`, `OutboxMessageSchema`, `NormalizedMessage`.
  - Conversation: `Ownership` (`AI`, `HUMAN`), `SenderRole`, `MessageDirection`.
  - Intents: `IntentType` (`PRICE_INQUIRY`, `DEALER_LOOKUP`, `PRODUCT_INQUIRY`, v.v.).
- [x] Tạo file fixtures 12 ca kiểm thử hồi quy `tests/fixtures/regression_cases.json` (T01 - T12).
- **Lệnh nghiệm thu:** `pytest tests/unit/test_contracts.py` (ĐÃ PASS 5/5 TEST)

---

### Phase 1: Meta Webhook Ingestion & Durable Inbox
- [x] Webhook endpoint `POST /webhook` tiếp nhận sự kiện từ Meta Messenger.
- [x] Endpoint `GET /webhook` xác thực challenge token theo chuẩn Meta.
- [x] Xác minh chữ ký `X-Hub-Signature-256` bằng HMAC-SHA256 (fail-closed nếu sai chữ ký).
- [x] Chống trùng lặp (Deduplication) dựa trên `event_id` / `mid` (Case T09).
- [x] Lưu bền vững vào bảng `inbox_events` (Durable Inbox) trước khi trả về `200 OK` cho Meta (< 500ms).
- [x] Phân tách dữ liệu tuyệt đối theo `page_id` (`CFC` hoặc `ZEO`).
- **Lệnh nghiệm thu:** `pytest tests/unit/test_meta_webhook.py` (ĐÃ PASS 3/3 TEST)

---

### Phase 2: Message Aggregation & Handoff State Guard
- [ ] Triển khai `aggregation_worker` dựa trên PostgreSQL durable work item + Redis schedule (Debounce 5s, max batch 20s).
- [x] Domain debounce giữ message, batch version và deadline; 4 tin nhắn gửi trong 6 giây được gom thành 1 batch trong test.
- [x] Domain state machine có `AI`, `HUMAN`, `PAUSED`, optimistic version và page-scope guard.
- [ ] Chế độ takeover: Khi nhân viên nhắn tin trên Meta Business Suite hoặc thao tác Ops Console, hệ thống chuyển `ownership = HUMAN` và ghi audit event.
- [x] Final-send guard từ chối output cũ khi ownership/version thay đổi (Case T08 ở domain test).
- [ ] Suppress guard được nối vào PostgreSQL outbox worker và kiểm chứng với Meta API thật.
- **Lệnh nghiệm thu:** `pytest tests/integration/test_aggregation_handoff.py`

---

### Phase 3: Excel Catalog & FAQ Staging Pipeline
- [x] Viết FastExcelReader thuần Python đọc 2 file: `docs/CfcCoBayN8n.xlsx` và `docs/ZeoN8n.xlsx`.
- [x] Phân tích và map các sheets:
  - `CFC`: Sheet `FAQ`, `KnowledgeSnapshot`, `LearningQueue`.
  - `ZEO`: Sheet `FAQ`, `Shopee`, `Web`, `Lazada`.
- [x] Mọi bản ghi mới import mặc định trạng thái `QUARANTINED`, chỉ bản ghi được `APPROVED` mới chuyển vào Read Models cho Chatbot (INV-5).
- [x] Kiểm tra xung đột dữ liệu: Nếu trùng SKU hoặc mâu thuẫn thông số -> Gắn cờ cảnh báo, không để bot tự chọn (Case T11).
- **Lệnh nghiệm thu:** `pytest tests/unit/test_excel_importer.py` (ĐÃ PASS 4/4 TEST)

---

### Phase 4: Qwen 8B Understanding (Intent & Entity Extraction)
- [ ] Client kết nối Ollama (`src/chatbot/modules/llm/ollama.py`) với timeout và retry có kiểm soát.
- [ ] Prompt trích xuất structured JSON cho Intent và Slot (`config/prompts/intent.md`).
- [ ] Nhận diện chính xác ý định hỏi mua/giá (T01, T03), tìm đại lý (T04), tìm sản phẩm (T06).
- [ ] Xử lý ngắt ngữ cảnh: Khách chuyển ý định ("Rải mít" sau câu hỏi giá -> giữ nguyên luồng giá hoặc tách bạch tư vấn) (Case T02).
- [ ] Fallback an toàn khi Ollama timeout hoặc lỗi JSON: trả câu mẫu nhẹ nhàng hoặc chuyển nhân viên, không treo hệ thống (Case T12).
- **Lệnh nghiệm thu:** `pytest tests/eval/test_qwen_understanding.py`

---

### Phase 5: Business Workflows & Final Send Outbox Guard
- [ ] Triển khai workflow `PRICE_INQUIRY`: **TUYỆT ĐỐI KHÔNG TỰ BÁO GIÁ**. Tạo handoff task cho nhân viên kinh doanh, bot chỉ lịch sự xác nhận và hỏi thêm số lượng/khu vực nếu cần (T01, T03, T05).
- [ ] Triển khai workflow `DEALER_LOOKUP`: Hỏi khu vực để tra cứu đại lý chính thức (T04).
- [ ] Triển khai workflow `PRODUCT_INQUIRY`: Cung cấp thông số kỹ thuật chuẩn từ catalog đã duyệt, không bịa đặt liều dùng.
- [ ] Delivery Outbox Worker: Quét bảng `outbox_messages` bằng `FOR UPDATE SKIP LOCKED`.
- [ ] **Final Send Guard:** Kiểm tra lại ownership và batch version trong cùng transaction trước khi gọi Meta Send API.
- **Lệnh nghiệm thu:** `pytest tests/integration/test_workflows.py`

---

### Phase 6: Approved Knowledge Retrieval & FAQ RAG
- [ ] Cơ chế tìm kiếm FAQ theo ngữ nghĩa hoặc từ khóa trong phạm vi `page_id`.
- [ ] Cách ly tuyệt đối: Khách hỏi Page CFC không bao giờ nhận được tài liệu riêng của Page ZEO (Case T10).
- [ ] Trả lời trực tiếp, ngắn gọn (1–3 câu), có nguồn kiểm chứng, không bịa thông tin kỹ thuật hoặc khuyến cáo sai rủi ro.
- **Lệnh nghiệm thu:** `pytest tests/integration/test_knowledge_retrieval.py`

---

### Phase 7: Operations Console & Emergency Controls
- [ ] Cung cấp API / CLI quản trị khẩn cấp:
  - Pause / Resume auto-reply theo từng Page (`kill_switch_cfc`, `kill_switch_zeo`).
  - Takeover thủ công theo từng hội thoại.
  - Xem danh sách tác vụ Handoff đang chờ nhân viên xử lý.
- [ ] Hệ thống Audit Log: Ghi lại ai thay đổi trạng thái, ai duyệt dữ liệu, lịch sử chuyển quyền.
- **Lệnh nghiệm thu:** `pytest tests/integration/test_ops_controls.py`

---

### Phase 8: Security Hardening & Go-Live Verification
- [ ] Chạy kiểm thử đầy đủ 12 ca hồi quy thực tế (T01 – T12) đạt tỉ lệ pass 100% trong `tests/eval/test_regression_full.py`.
- [ ] Kiểm tra bảo mật: Mask thông tin cá nhân (PII) trong log, bảo vệ secret keys.
- [ ] Chạy Replay test trên dữ liệu cũ và Shadow mode trước khi bật gửi tin thật.
- [ ] Docker Compose, PostgreSQL backup/restore, Ollama health/model readiness và Meta webhook production test đạt.
- [ ] Nghiệm thu toàn bộ Go-live gate và ký duyệt bàn giao; chưa được bật auto-reply trước bước này.
- **Lệnh nghiệm thu:** `pytest tests/eval/test_regression_full.py`
