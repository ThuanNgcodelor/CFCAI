# CFC–ZEO AI Platform — Implementation Roadmap & Phase Gatekeeper

> Tài liệu này dùng để theo dõi tiến độ chính xác của dự án và làm căn cứ nghiệm thu (Gatekeeper) trước khi chuyển phase.  
> **Nguyên tắc:** Một phase chỉ được tích `[x]` khi toàn bộ Tiêu chí hoàn thành (Definition of Done) và Automated Test tương ứng đã PASS.

---

## Tổng quan tiến độ

- [x] **Phase 0: Foundation, Architecture Contracts & Test Fixtures (COMPLETED)**
- [x] **Phase 1: Meta Webhook Ingestion & Durable Inbox (COMPLETED — staging/live tunnel verified)**
- [ ] **Phase 2: Message Aggregation & Handoff State Guard (IMPLEMENTED/STAGING PASS — còn live Meta takeover validation và Phase 4 slot analyzer)**
- [x] **Phase 3: Excel Catalog & FAQ Staging Pipeline (COMPLETED — versioned staging/publish/rollback gate pass)**
- [x] **Phase 4: Qwen 8B Understanding (Structured Intent & Entity Extraction) (COMPLETED — deterministic safety + Qwen structured JSON + live eval pass)**
- [x] **Phase 5: Business Workflows & Final Send Outbox Guard (COMPLETED — workflows, output policy validator & outbox guard pass)**
- [ ] **Phase 6: Approved Knowledge Retrieval & FAQ RAG (PARTIAL — approved Postgres/keyword retrieval có; semantic RAG/citation chưa có)**
- [ ] **Phase 7: Operations Console & Emergency Controls (Kill Switch) (PARTIAL — Redis shared pause/resume có; auth/RBAC/audit chưa có)**
- [ ] **Phase 8: Security Hardening, Regression Verification & Production Go-Live**
- [ ] **Integration: MISA AMIS CRM Python Warmer (PARTIAL — endpoint thật và Redis snapshot đã chạy; workflow chat/TTL/GPS còn thiếu)**

## Kế hoạch thực thi từ trạng thái hiện tại

> Thứ tự dưới đây là thứ tự triển khai bắt buộc. Không nhảy thẳng sang semantic RAG hoặc production khi conversation state và workflow giá chưa đạt gate.

### Mục tiêu sản phẩm sau cùng

Chatbot đạt yêu cầu khi không còn là bộ máy tìm FAQ theo từng tin nhắn rời rạc,
mà là một **conversation runtime có trạng thái**:

1. Nhớ các tin trước trong cùng cuộc hội thoại và hiểu câu follow-up ngắn.
2. Tách rõ `intent`, `workflow` và `slots`; Qwen chỉ hiểu ngôn ngữ, Python quyết định nghiệp vụ.
3. Tra đúng sản phẩm/đại lý/FAQ theo `page_id`, dữ liệu đã duyệt và mức tin cậy.
4. Không tự báo giá; tạo handoff ngay và giữ đủ ngữ cảnh cho nhân viên.
5. Không gửi AI sau khi nhân viên takeover; mọi lần gửi đều qua durable outbox và final guard.
6. Có regression từ hội thoại thật để mỗi lần sửa không làm bot “ngu lại”.

### Kiến trúc xử lý đích cho mỗi lượt chat

```text
Webhook → Durable Inbox → Debounce/Batch → Load Conversation State
        → Deterministic Safety Guards → Qwen Structured Understanding
        → Slot Merge + Intent Transition → Deterministic Workflow
        → Approved Retrieval/CRM Read Model → Response Composer
        → Output Policy Validation → Durable Outbox → Final Ownership Guard → Meta
```

Qwen không được gọi trực tiếp để “tự nghĩ rồi trả lời”. Model chỉ xuất JSON có
schema; workflow Python mới được quyền chọn nguồn dữ liệu, hỏi thêm, tạo handoff
hoặc chuẩn bị câu trả lời. Đây là khác biệt cốt lõi giữa chatbot mục tiêu và
pipeline keyword/FAQ hiện tại.

### Thứ tự phát hành bắt buộc

| Release | Phạm vi | Kết quả có thể kiểm chứng | Điều kiện chuyển tiếp |
|---|---|---|---|
| **R0 — Safety Hotfix** | Price guard, dealer ambiguity, transcript regression | Không tự trả giá; không chọn đại lý tùy tiện | Sprint 0 gate pass |
| **R1 — Stateful Core** | Conversation/message/slot DB, debounce, ownership | Hiểu “30 tấn”, “Rạch Giá Kiên Giang”, “rải mít” trong đúng ngữ cảnh | Phase 2 gate pass |
| **R2 — Understanding** | Rule ưu tiên + Qwen JSON + alias/entity normalization | Nhận đúng intent, product, quantity, crop, location kể cả viết tắt/sai nhẹ | Phase 4 eval pass |
| **R3 — Useful Workflows** | Product, dealer, price handoff, agriculture advice | Trả đúng nghiệp vụ, tự nhiên 1–3 câu, không raw CRM record | Phase 3 + 5 + 6 gate pass |
| **R4 — Operable Pilot** | Handoff queue, takeover, RBAC, audit, CRM freshness | Nhân viên nhận/chốt task và dừng bot an toàn | CRM + Phase 7 gate pass |
| **R5 — Production** | T01–T12, replay/shadow/canary, backup/security | Được phép bật auto-reply production có kiểm soát | Phase 8 gate pass |

### Backlog triển khai ngay — không làm song song sai thứ tự

#### PR-1 — Safety hotfix và test transcript

- Sửa precedence để `PRICE_INQUIRY` không thể bị FAQ/retrieval/Qwen ghi đè.
- Chặn câu “đại lý gần nhất” khi chưa có tỉnh/huyện chính xác hoặc dữ liệu không đủ.
- Thêm test tái hiện nguyên văn các đoạn chat người dùng đã cung cấp.
- Kết quả bắt buộc: không có con số giá, không trả sai tỉnh, không đổi intent vô lý.

#### PR-2 — Persistent conversation runtime

- Migration và repository cho `conversations`, `messages`, `conversation_slots`,
  `message_batches`, `handoff_tasks`, `handoff_events`.
- Mọi khóa/truy vấn đều có `page_id`; PostgreSQL là source of truth.
- Worker ghi message, debounce theo conversation, claim batch atomic và giữ
  `conversation_version`/`batch_version`.
- Kết quả bắt buộc: restart worker không mất ngữ cảnh hoặc tạo phản hồi trùng.

#### PR-3 — Intent/slot analyzer

- Chuẩn hóa đầu vào trước model: Unicode, viết tắt, đơn vị, tỉnh/huyện, SKU/công thức.
- Rule fail-closed cho giá, yêu cầu người thật và takeover chạy trước model.
- Qwen trả Pydantic JSON: intent transition, product mentions, quantity/unit,
  crop/stage/problem, province/district và evidence message IDs.
- Timeout/JSON lỗi phải dùng fallback an toàn; không retry vô hạn.

#### PR-4 — Workflow engine và response composer

- `PRICE_INQUIRY`: tạo task ngay, hỏi tối đa một slot còn thiếu, không báo giá.
- `PRODUCT_INQUIRY`: exact SKU/formula → alias → fuzzy có ngưỡng → hỏi lại nếu mơ hồ.
- `DEALER_LOOKUP`: giữ location qua nhiều lượt; exact administrative match trước,
  khoảng cách chỉ khi cả hai phía có tọa độ.
- `AGRI_ADVICE`: yêu cầu đủ crop/stage/problem và chỉ dùng nội dung đã duyệt.
- Composer biến domain result thành 1–3 câu tự nhiên; validator quét lại policy trước outbox.

#### PR-5 — Retrieval/data quality

- Hoàn thiện import batch, provenance, publish version và rollback.
- Tách index/ranking FAQ, product, dealer; luôn `APPROVED`, customer audience,
  đúng Page/brand và còn hiệu lực.
- Chỉ thêm embedding/pgvector sau khi exact + alias baseline được đo; vector search
  không được phép vượt qua price/page/approval guard.

#### PR-6 — Operations và go-live

- Handoff queue claim/resolve/SLA/notification; takeover/pause/resume per conversation.
- Auth/RBAC, append-only audit, metrics/alerts, dead-letter/reconciliation.
- Named Cloudflare Tunnel hoặc domain ổn định; backup/restore drill; rotate secret.
- Replay → shadow → canary một workflow/một Page → mở rộng có sign-off.

### Chỉ số nghiệm thu chatbot

| Chỉ số | Gate bắt buộc |
|---|---:|
| Bot tự nêu giá | **0** |
| Rò dữ liệu CFC ↔ ZEO | **0** |
| Bot gửi sau takeover | **0** |
| Duplicate logical reply trong replay | **0** |
| T01–T12 | **100% pass trước production** |
| Câu trả lời không có nguồn/độ tin cậy đủ | Clarify hoặc handoff, không đoán |

### Việc chưa nên làm lúc này

- Không fine-tune model trước khi có bộ eval và baseline structured extraction.
- Không đưa toàn bộ payload CRM, lịch sử dài hoặc bảng giá vào prompt.
- Không dùng vector RAG để che lỗi intent/state/workflow.
- Không bật auto-reply rộng chỉ vì unit test hoặc một vài tin Messenger đã chạy.
- Không coi Cloudflare Quick Tunnel là endpoint production ổn định.

### Sprint 0 — Safety Recovery (ưu tiên ngay)

- [x] Price guard chạy trước retrieval sinh câu trả lời và không thể bị workflow khác ghi đè.
- [x] Mọi `PRICE_INQUIRY` production tạo `handoff_task` theo page/batch; bot chỉ xác nhận khi task đã tồn tại.
- [x] Không trả dealer “gần nhất” nếu thiếu GPS; exact address chỉ được mô tả là phù hợp/trùng khu vực.
- [ ] Thêm regression cho chuỗi chat thực tế: sản phẩm → giá → số lượng → cây trồng → đại lý → địa điểm.
- [x] Chạy toàn bộ test cũ, không có regression (275 passed ngày 27/10/2026).
- **Gate:** zero price auto-answer, zero arbitrary dealer, zero intent override.

### Phase 2 — Conversation Runtime & Ownership

- [x] Tạo PostgreSQL `conversations`, `messages`, `conversation_slots` và repository page-scoped.
- [x] Worker gom tin bằng debounce cấu hình, max batch cấu hình trước khi phân loại; PostgreSQL là nguồn thật và Redis giữ lịch tăng tốc.
- [x] Repository lưu/merge `current_workflow`, `primary_intent` và slots dạng JSON không hardcode schema nghiệp vụ.
- [x] Follow-up ngắn như “Rạch Giá Kiên Giang”, “30 tấn”, “Rải mít” tiếp tục/chuyển workflow theo policy cấu hình.
- [x] Ops takeover chuyển ownership sang `HUMAN`, tăng version, hủy batch và suppress pending outbox trong cùng transaction.
- [ ] Xác minh live event phân biệt Business Suite human reply với bot echo trên cả CFC và ZEO.
- **Gate:** `tests/integration/test_aggregation_handoff.py` + test hội thoại nhiều lượt pass.

### Phase 3 — Data Publish Pipeline

- [x] Tách bảng chuẩn `faq_items`, `catalog_items`, `import_batches`; lưu source file/sheet/row/checksum.
- [x] Import idempotent vào `QUARANTINED`; approve/reject theo record hoặc batch.
- [x] Có publish version và rollback; `active=true` không tự thành `APPROVED`.
- [x] Loại `audience=agent` khỏi customer retrieval và giữ giá trong `internal_data`, ngoài read model/LLM context.
- **Gate:** bổ sung `tests/integration/test_excel_importer.py`, conflict/rollback/page isolation pass.

### Phase 4 — Intent & Slot Understanding

- [x] Rule deterministic xử lý price/human/takeover trước Ollama.
- [x] Qwen chỉ trích xuất structured intent/slots; không quyết định quyền gửi hay báo giá.
- [x] Chuẩn hóa aliases: Cobanic/HC/NPK/công thức/SKU/tỉnh-huyện/cây trồng/số lượng.
- [x] Đánh giá trên câu viết tắt, sai chính tả và chuỗi hội thoại thật.
- **Gate:** `tests/eval/test_qwen_understanding.py` (ĐÃ PASS 16/16 test, bao gồm live Qwen 2.5 7B).

### Phase 5 — Business Workflows

- [x] `PRICE_INQUIRY`: thu product + quantity + area, tạo handoff, không tự báo giá.
- [x] `PRODUCT_INQUIRY`: exact SKU/formula trước, alias sau, hỏi lại khi nhiều kết quả.
- [x] `DEALER_LOOKUP`: lấy province/district từ state, exact address match; distance chỉ dùng khi có GPS.
- [x] `AGRI_ADVICE`: yêu cầu crop/stage/problem; không dùng một FAQ dài cho mọi trường hợp.
- [x] Response composer biến record CRM thành câu trả lời tự nhiên 1–3 câu, không gửi raw record.
- **Gate:** `tests/integration/test_workflows.py`, `tests/unit/test_safe_pipeline.py`, `tests/unit/test_output_policy_validator.py` (ĐÃ PASS 45/45 test).


### Phase 6 — Retrieval Quality

- [x] Ranking tách riêng FAQ/product/agronomy/dealer; có minimum score và ambiguity guard.
- [x] Không match chỉ vì từ chung như “giá”, “sản phẩm”, “gần nhất”, “Giang”.
- [ ] Semantic/vector retrieval chỉ bổ sung sau exact/alias matching; luôn page-scoped và approved-only.
- [x] Có source/provenance nội bộ và clarification/fallback khi confidence thấp.
- **Gate:** retrieval precision/recall bộ câu thật đạt ngưỡng và T10/T11 pass.

### CRM Integration — Operational Workflows

- [x] Xác thực AMIS và warm snapshot thật vào Redis.
- [x] Snapshot hiện có: 422 locations, 942 products, 7.913 orders, 5.000 customer/loyalty records.
- [ ] Chốt field mapping vì nhiều `account_id`, `code`, `mobile`, `unit`, GPS đang null.
- [ ] TTL, refresh schedule, last-good snapshot và stale-data alert.
- [ ] Nối dealer/order/loyalty workflow vào conversation state; không để payload MISA lan vào prompt.
- **Gate:** contract test + cache failure fallback + CRM unavailable test pass.

### Phase 7 — Operations & Human Handoff

- [ ] Auth/RBAC cho admin endpoints; audit append-only.
- [ ] Handoff queue có claim/resolve/SLA/notification.
- [ ] Per-conversation pause/resume/takeover và outbox suppression kiểm chứng thật.
- [ ] Dashboard tối thiểu: inbox backlog, outbox failure, Ollama timeout, sync freshness.
- **Gate:** `tests/integration/test_ops_controls.py` mở rộng pass.

### Phase 8 — Go-Live

- [ ] Chuyển toàn bộ transcript thật thành T01–T12 automated regression.
- [ ] Replay/shadow/canary trước khi bật auto-reply rộng.
- [ ] Backup/restore PostgreSQL; Redis cache rebuild; Named Cloudflare Tunnel/domain cố định.
- [ ] Security review secrets/PII/webhook/admin endpoints.
- [ ] Business sign-off và rollback drill.
- **Gate:** `tests/eval/test_regression_full.py` pass 100%; thiếu một gate thì chưa production.

### Mốc hoàn thành thực dụng

| Mốc | Kết quả nhìn thấy được | Điều kiện |
|---|---|---|
| M1 — Safe Pilot | Bot không trả sai giá/đại lý; có handoff | Sprint 0 pass |
| M2 — Stateful Chat | Hiểu follow-up nhiều tin liên tiếp | Phase 2 pass |
| M3 — Useful Bot | Product/dealer/agri workflows trả lời đúng, tự nhiên | Phase 3–6 pass |
| M4 — Operable Pilot | Nhân viên takeover/handoff/audit được | CRM + Phase 7 pass |
| M5 — Production | Regression, security, backup, canary đạt | Phase 8 pass |

### Evidence audit — 25/10/2026 (updated)

Đây là trạng thái dựa trên artefact và lệnh kiểm tra thực tế trong workspace, không dựa trên giả định triển khai:

| Hạng mục | Bằng chứng hiện có | Kết luận |
|---|---|---|
| Phase 0 | `pytest tests/unit/test_contracts.py` — 5 passed | Đạt phần test gate hiện có |
| Phase 1 | Meta tunnel POST `/webhooks/meta` trả 200; `PostgresInboxStore`, lease worker, migration và page-specific HMAC/dedup có; Phase 1 integration gate pass | Đạt DoD staging; chưa phải production sign-off |
| Phase 2 | Durable conversation/message/batch/slot DB, Redis schedule, Ops takeover transaction và final outbox guard; integration gate 6/6 pass | Staging pass; chưa đóng gate vì chưa test live Business Suite echo/takeover và follow-up analyzer thuộc Phase 4 |
| Phase 3 | Mapping ngoài code, checksum/idempotent quarantine, record/batch review, atomic publish/rollback, customer-only read model; integration gate 5/5 pass | Đạt DoD kỹ thuật; batch dữ liệu thật vẫn chờ người duyệt |
| Phase 6 | Ranker riêng theo miền, exact/alias + score/margin, ambiguity fail-closed, page/status filter; F4 gate 132/132 pass; chưa có vector/RAG citation hiển thị | Partial |
| Phase 7 | `/admin/ops/status`, pause/resume; Redis state dùng chung API/worker; `tests/integration/test_ops_controls.py` pass; chưa có auth/RBAC/audit/task queue | Partial |
| Phase 8 | `tests/eval/test_regression_full.py` đã chạy T01–T12: 12/12 pass; full suite 275 pass; còn shadow/canary, security, backup/restore và production sign-off | Partial |
| MISA | Endpoint thật warm thành công và Redis snapshot có; dữ liệu GPS bằng 0, field mapping nhiều null, workflow chat chưa hoàn chỉnh | Partial, chưa production |

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
- [x] Worker durable inbox claim/lease chạy trong service `cfc_zeo_worker`.
- **Lệnh nghiệm thu:** `pytest tests/integration/test_webhook_inbox.py` (PASS) + Meta tunnel POST 200

---

### Phase 2: Message Aggregation & Handoff State Guard
- [x] Triển khai `aggregation_worker` dựa trên PostgreSQL durable work item + Redis schedule (thời gian lấy từ cấu hình).
- [x] Domain debounce giữ message, batch version và deadline; 4 tin nhắn gửi trong 6 giây được gom thành 1 batch trong test.
- [x] Domain state machine có `AI`, `HUMAN`, `PAUSED`, optimistic version và page-scope guard.
- [x] Ops Console takeover/resume chuyển ownership có version fence, ghi `handoff_events`, hủy batch và suppress outbox theo Page.
- [x] Final-send guard từ chối output cũ khi ownership/version thay đổi (Case T08 ở domain test).
- [x] Suppress/final-send guard đã nối vào PostgreSQL outbox claim transaction và pass integration race test.
- [ ] Còn phải kiểm chứng event human reply/echo và race với Meta API thật trên cả hai Page trước khi đóng Phase 2.
- **Lệnh nghiệm thu:** `pytest tests/integration/test_aggregation_handoff.py`

---

### Phase 3: Excel Catalog & FAQ Staging Pipeline
- [x] Viết FastExcelReader thuần Python đọc 2 file cấu hình tại `data/sources/cfc/catalog/CfcCoBayN8n.xlsx` và `data/sources/zeo/catalog/ZeoN8n.xlsx`.
- [x] Phân tích và map các sheets:
  - `CFC`: Sheet `FAQ`, `KnowledgeSnapshot`, `LearningQueue`.
  - `ZEO`: Sheet `FAQ`, `Shopee`, `Web`, `Lazada`.
- [x] Mọi bản ghi mới import mặc định trạng thái `QUARANTINED`, chỉ bản ghi được `APPROVED` mới chuyển vào Read Models cho Chatbot (INV-5).
- [x] Kiểm tra xung đột dữ liệu: Nếu trùng SKU hoặc mâu thuẫn thông số -> Gắn cờ cảnh báo, không để bot tự chọn (Case T11).
- [x] Lưu `import_batches`, provenance/checksum; import lặp không nhân đôi dữ liệu.
- [x] Review theo record/batch, atomic publish version và rollback version.
- [x] Read model chỉ nhận customer audience + approved/active; trường giá chỉ ở `internal_data` và không publish.
- **Lệnh nghiệm thu:** `pytest tests/integration/test_excel_importer.py` (ĐÃ PASS 5/5 TEST) + full suite 45 pass

---

### Phase 4: Qwen 8B Understanding (Intent & Entity Extraction)
- [x] Client kết nối Ollama (`src/chatbot/modules/llm/ollama.py`) với timeout và retry có kiểm soát.
- [x] Prompt trích xuất structured JSON cho Intent và Slot (`config/prompts/intent.md`).
- [x] Nhận diện chính xác ý định hỏi mua/giá (T01, T03), tìm đại lý (T04), tìm sản phẩm (T06).
- [x] Xử lý ngắt ngữ cảnh: Khách chuyển ý định ("Rải mít" sau câu hỏi giá -> giữ nguyên luồng giá hoặc tách bạch tư vấn) (Case T02).
- [x] Fallback an toàn khi Ollama timeout hoặc lỗi JSON: trả câu mẫu nhẹ nhàng hoặc chuyển nhân viên, không treo hệ thống (Case T12).
- **Lệnh nghiệm thu:** `RUN_LIVE_OLLAMA_EVAL=1 pytest tests/eval/test_qwen_understanding.py tests/integration/test_aggregation_handoff.py` (ĐÃ PASS 24/24 TEST ngày 27/10/2026)

---

### Phase 5: Business Workflows & Final Send Outbox Guard
- [x] Triển khai workflow `PRICE_INQUIRY`: **TUYỆT ĐỐI KHÔNG TỰ BÁO GIÁ**. Tạo handoff task cho nhân viên kinh doanh, bot chỉ lịch sự xác nhận và hỏi thêm số lượng/khu vực nếu cần (T01, T03, T05).
- [x] Triển khai workflow `DEALER_LOOKUP`: Hỏi khu vực để tra cứu đại lý chính thức (T04).
- [x] Triển khai workflow `PRODUCT_INQUIRY`: Cung cấp thông số kỹ thuật chuẩn từ catalog đã duyệt, không bịa đặt liều dùng.
- [x] Delivery Outbox Worker: Quét bảng `outbox_messages` bằng `FOR UPDATE SKIP LOCKED`.
- [x] **Final Send Guard:** Kiểm tra lại ownership và batch version trong cùng transaction trước khi gọi Meta Send API.
- **Lệnh nghiệm thu:** `pytest tests/integration/test_workflows.py tests/unit/test_safe_pipeline.py tests/unit/test_output_policy_validator.py` (ĐÃ PASS 51/51 TEST ngày 27/10/2026)

---

### Phase 6: Approved Knowledge Retrieval & FAQ RAG
- [x] Cơ chế tìm kiếm từ khóa trong phạm vi `page_id`, chỉ đọc `APPROVED`.
- [x] Cách ly tuyệt đối ở approved in-memory/Postgres store: CFC không nhận tài liệu ZEO (Case T10).
- [ ] Trả lời trực tiếp, ngắn gọn (1–3 câu), có nguồn kiểm chứng, không bịa thông tin kỹ thuật hoặc khuyến cáo sai rủi ro.
- **Lệnh nghiệm thu:** `pytest tests/integration/test_knowledge_retrieval.py`

---

### Phase 7: Operations Console & Emergency Controls
- [x] Cung cấp API quản trị khẩn cấp:
  - Pause / Resume auto-reply theo từng Page (`kill_switch_cfc`, `kill_switch_zeo`).
  - [ ] Takeover thủ công theo từng hội thoại.
  - [ ] Xem danh sách tác vụ Handoff đang chờ nhân viên xử lý.
- [ ] Hệ thống Audit Log: Ghi lại ai thay đổi trạng thái, ai duyệt dữ liệu, lịch sử chuyển quyền.
- **Lệnh nghiệm thu:** `pytest tests/integration/test_ops_controls.py`

---

### Phase 8: Security Hardening & Go-Live Verification
- [x] Chạy kiểm thử đầy đủ 12 ca hồi quy thực tế (T01 – T12) đạt 12/12 trong `tests/eval/test_regression_full.py` ngày 27/10/2026.
- [ ] Kiểm tra bảo mật: Mask thông tin cá nhân (PII) trong log, bảo vệ secret keys.
- [ ] Chạy Replay test trên dữ liệu cũ và Shadow mode trước khi bật gửi tin thật.
- [ ] Docker Compose, PostgreSQL backup/restore, Ollama health/model readiness và Meta webhook production test đạt.
- [ ] Nghiệm thu toàn bộ Go-live gate và ký duyệt bàn giao; chưa được bật auto-reply trước bước này.
- **Lệnh nghiệm thu:** `pytest tests/eval/test_regression_full.py`
