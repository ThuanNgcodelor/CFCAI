# Báo cáo nghiệm thu Phase F3–F5 — 27/10/2026

## Kết luận

Ba gate F3, F4 và F5 đều **PASS** ở phạm vi kỹ thuật đã định nghĩa trong
`docs/CFC_FAQ_IMPLEMENTATION_PLAN.md`. Không có case fail còn lại trong các gate
này. Trạng thái này không đồng nghĩa toàn hệ thống đã production-ready; shadow,
canary, security, backup/restore và business sign-off vẫn thuộc F7/Phase 8.

## Thay đổi chính

- F3: follow-up được quyết định theo workflow đang mở; `Rải mít` trong luồng giá
  giữ `PRICE_INQUIRY_DETAIL`, còn câu hỏi rõ `rải ... thế nào` chuyển sang tư vấn.
  Slot sản phẩm được chuyển từ product sang price bằng cấu hình transition.
- F4: PostgreSQL, in-memory và CRM Redis dùng cùng contract confidence. Exact
  alias/SKU được ưu tiên; kết quả Top-1/Top-2 sát nhau trả `AMBIGUOUS` và yêu cầu
  khách làm rõ, không lấy record đầu tiên.
- F5: thêm `handoff_tasks` bền vững, idempotent, page/batch fenced. Bot chỉ nói đã
  tạo/chuyển yêu cầu khi task đã commit. Output validator kiểm tra cả fallback,
  chặn persona `bạn`, phone lạ, giá, placeholder, nội bộ, nearest không GPS,
  công thức và named entity không có grounding.
- Thêm bộ executable regression `tests/eval/test_regression_full.py` cho T01–T12.

## Kết quả gate

| Gate | Lệnh | Kết quả |
|---|---|---:|
| F3 | `RUN_LIVE_OLLAMA_EVAL=1 pytest -q tests/eval/test_qwen_understanding.py tests/integration/test_aggregation_handoff.py` | 24 passed |
| F4 | `RUN_CFC_FAQ_EVAL=1 pytest -q tests/eval/test_cfc_faq_cases.py tests/integration/test_knowledge_retrieval.py` | 132 passed |
| F5 | `pytest -q tests/integration/test_workflows.py tests/unit/test_safe_pipeline.py tests/unit/test_output_policy_validator.py` | 51 passed |
| T01–T12 | `pytest -q tests/eval/test_regression_full.py` | 12 passed |
| Full suite | `RUN_CFC_FAQ_EVAL=1 RUN_LIVE_OLLAMA_EVAL=1 pytest -q` | 275 passed, 1 dependency deprecation warning |
| Lint | `ruff check src tests` | All checks passed |

## Dữ liệu cần nghiệp vụ duyệt

- Ba FAQ đang `MISSING_ANSWER` (số 4, 17, 19) vẫn không được publish làm câu trả lời.
- Nội dung nông học và liều lượng phải được chuyên gia ký duyệt trước khi mở rộng
  auto-reply thật.
- CRM có nhiều biến thể Cobanic 21; câu thiếu mã/quy cách được hỏi lại là hành vi
  có chủ đích, không phải lỗi retrieval.
