# Cây thư mục và cách hệ thống CFC–ZEO hoạt động

Cập nhật: 27/10/2026. Tài liệu này mô tả mã nguồn đang chạy, nguồn dữ liệu,
artefact cục bộ và ranh giới giữa các thành phần. Nó không thay thế
`Agent.md`, `ROADMAP.md` hoặc kế hoạch FAQ.

## 1. Cây thư mục cần quan tâm

```text
CFCAI/
├── apps/                         Điểm khởi chạy process
│   ├── api/main.py               FastAPI: webhook Meta và API quản trị
│   ├── worker/main.py            Worker inbox -> pipeline -> outbox
│   └── tools/                    CLI vận hành dữ liệu, CRM và reset test state
├── config/                       Chính sách/cấu hình, không chứa mã trả lời riêng từng câu
│   ├── business/                 Danh bạ hotline, kinh doanh, khuyến nông
│   ├── data_sources/             Mapping import và governance từng nguồn
│   ├── normalization/            Alias intent, địa danh hành chính
│   ├── pages/                    Cấu hình tách Page CFC/ZEO
│   ├── policies/                 Handoff và output policy
│   ├── prompts/                  Prompt hiểu intent có cấu trúc
│   └── retrieval/                Ngưỡng/rule xếp hạng retrieval
├── data/sources/                 Nguồn nghiệp vụ do quản trị cập nhật
│   ├── manifest.yaml             Danh sách nguồn và chính sách stage/publish
│   ├── cfc/faq/                  FAQ Markdown chuẩn duy nhất của CFC
│   ├── cfc/catalog/              Excel danh mục CFC
│   └── zeo/catalog/              Excel danh mục ZEO
├── migrations/                   Schema PostgreSQL 001..008, chạy theo thứ tự
├── src/chatbot/                  Mã nghiệp vụ chính
│   ├── core/                     Settings và đọc biến môi trường
│   ├── infrastructure/           Database, durable inbox/outbox, worker
│   ├── modules/
│   │   ├── aggregation/          Gom burst tin nhắn theo debounce
│   │   ├── channels/meta/        Xác thực, chuẩn hóa và gửi Messenger
│   │   ├── conversations/        State, slot, ownership và handoff task
│   │   ├── delivery/             Gửi outbox với final ownership guard
│   │   ├── integrations/         Import Markdown/Excel và warm CRM AMIS
│   │   ├── knowledge/            Retrieval APPROVED, dealer resolver
│   │   ├── llm/                  Client Ollama/Qwen; không sở hữu business truth
│   │   ├── ops/                  Kill switch/pause/resume
│   │   ├── orchestration/        Phân intent, chuyển state và pipeline tổng
│   │   └── workflows/            Composer, contact, SLA, output validator
│   └── shared/                   Enum, event schema, địa danh dùng chung
├── tests/                        Unit, integration, eval và fixture bất biến
├── scripts/                      Sinh fixture, đánh giá F6 và tiện ích local
├── reports/                      Bằng chứng eval đã sinh; không phải dữ liệu production
├── docs/                         Kiến trúc, nguồn dữ liệu, kế hoạch, test run
├── docker-compose.yml            API/worker/Postgres/Redis/data jobs
├── Dockerfile                    Image Python dùng chung
├── pyproject.toml                Metadata dự án và dependency phát triển
├── requirements.txt              Dependency cài trong image hiện tại
├── Agent.md                      Năm bất biến kiến trúc
├── NGUYEN_TAC_TRUNG_THUC.md      Quy tắc trung thực dữ liệu
└── ROADMAP.md                    Phase và Definition of Done cấp hệ thống
```

Các file `__init__.py` dù trống vẫn xác định package Python, không phải file rác.
`pyproject.toml` và `requirements.txt` hiện cùng cần thiết: file đầu phục vụ công
cụ/phát triển, file sau đang được Dockerfile sử dụng.

## 2. Luồng một tin nhắn hiện tại

```text
Meta webhook
  -> xác thực chữ ký + xác định page_id
  -> PostgreSQL inbox (deduplicate, ACK nhanh)
  -> worker claim event
  -> aggregator gom các tin đến gần nhau
  -> đọc conversation context/slot/ownership
  -> deterministic safety + Qwen intent JSON
  -> workflow theo intent
  -> dữ liệu APPROVED/CRM resolver nếu workflow cần
  -> composer
  -> output policy: giá, placeholder, persona, grounding, jargon
  -> PostgreSQL outbox
  -> final ownership + batch/version guard
  -> Meta Send API
```

Qwen chỉ hỗ trợ hiểu ngôn ngữ và diễn đạt. Giá, sản phẩm, đại lý, số điện thoại
và hướng dẫn nông học phải đến từ nguồn đã duyệt hoặc cấu hình cho phép. Một tin
đã vào inbox không đồng nghĩa chắc chắn được gửi: takeover, pause, batch cũ hoặc
conversation version cũ sẽ chặn ở final send guard.

## 3. Luồng dữ liệu

```text
Markdown/Excel -> manifest -> validate -> QUARANTINED -> approve -> publish
                                                       -> knowledge read model

MISA AMIS -> crm-warmer -> snapshot tạm -> validate -> atomic current pointer
                                                   -> dealer/product/order lookup
```

- Nguồn file chuẩn nằm duy nhất trong `data/sources/`; không đọc file trong
  `docs/` để trả lời khách.
- Import không tự publish. Runtime chỉ đọc record `APPROVED`, active và đúng
  `page_id`.
- CFC và ZEO bị tách ở mọi truy vấn. Dữ liệu một Page không được làm fallback
  cho Page còn lại.
- CRM warm là job riêng; snapshot lỗi không được ghi đè last-known-good.
- `tests/fixtures/` và `reports/` chỉ phục vụ kiểm thử, không phải knowledge base.

## 4. File sinh tự động và chính sách dọn dẹp

| Đường dẫn | Xử lý | Lý do |
|---|---|---|
| `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/` | Xóa an toàn | Công cụ tự sinh lại |
| `**/__pycache__/` | Xóa an toàn | Python tự sinh lại |
| `cloudflared-tunnel.*.log` | Không commit | Log phiên chạy local |
| `.venv/` | Giữ local, không commit | Môi trường hiện dùng để chạy test; có thể tái tạo |
| `.codegraph/` | Giữ local | Chỉ mục hỗ trợ phân tích code; không phải runtime dependency |
| `.env` | Giữ local, không commit | Chứa secret/cấu hình thật |
| `reports/` | Giữ có chọn lọc | Bằng chứng baseline/gate F6; không phải cache |
| Docker volumes | Giữ | Chứa PostgreSQL/Redis local; xóa sẽ mất state test/data |

Chạy dọn cache an toàn bằng:

```bash
bash scripts/cleanup_local_artifacts.sh
```

Script cố ý không đụng `.venv`, `.env`, `.codegraph`, `reports/`, dữ liệu nguồn
hoặc Docker volumes.

## 5. Những thứ đã loại bỏ trong đợt rà soát này

- `cloudflared-tunnel.err.log` và `cloudflared-tunnel.out.log`: log local bị
  commit nhầm; đã thêm ignore.
- `scripts/reset_conversations.py`: bản sao cũ dùng module settings không còn
  tồn tại. Bản hợp lệ là `apps/tools/reset_conversations.py`.
- `docs/CfcCoBayN8n_FAQ_editable.md`: bản xuất cũ 360 dòng, persona không an
  toàn và không thuộc manifest. Nguồn chuẩn là
  `data/sources/cfc/faq/CFC_Co_Bay_FAQ.md`; lịch sử cũ vẫn phục hồi được từ Git.

## 6. Lệnh vận hành chính

```bash
# Chạy hạ tầng và ứng dụng
docker compose --profile app up -d --build

# Kiểm tra/stage/publish nguồn file
docker compose --profile data run --rm data-loader validate --all
docker compose --profile data run --rm data-loader stage --changed
docker compose --profile data run --rm data-loader status --page CFC

# Warm CRM riêng
docker compose --profile data run --rm crm-warmer sync
docker compose --profile data run --rm crm-warmer status

# Reset state hội thoại khi test thủ công (tác vụ phá hủy state test)
python apps/tools/reset_conversations.py --sender-id <PSID>

# Gate F6
python scripts/build_cfc_faq_test_cases.py --check
python scripts/evaluate_cfc_faq.py --live --check-production --check
pytest tests/eval/test_regression_full.py tests/eval/test_cfc_conversation_replays.py
pytest
```

Không chạy `reset_conversations.py --all`, xóa Docker volume hoặc publish batch
trên môi trường thật nếu chưa xác định chính xác phạm vi và có bản sao lưu.
