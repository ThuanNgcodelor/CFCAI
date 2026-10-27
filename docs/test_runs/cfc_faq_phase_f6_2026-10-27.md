# Báo cáo nghiệm thu Phase F6 — CFC FAQ

Ngày chạy: 27/10/2026  
Phạm vi: full FAQ regression, held-out retrieval, bốn transcript Messenger,
restart worker simulation, T01–T12, output policy và production read model local.

## Kết luận

**Phase F6: PASS cho toàn bộ nguồn đang được phép active.**

Kết quả này không tự động duyệt nội dung nghiệp vụ. Trong 119 biến thể có đáp
án, 26 biến thể thuộc 8 dòng `SAFE_WORKFLOW` được gate runtime; 93 biến thể còn
lại vẫn chạy để audit nhưng mang verdict `NOT_GATED` vì đang chờ business,
catalog hoặc chuyên gia nông học duyệt.

## Kết quả đo được

| Gate | Kết quả |
|---|---:|
| Câu mẫu nguồn retrieval Top-1 | 119/119 |
| Câu mẫu nguồn retrieval Top-3 | 119/119 |
| Cách ly ZEO | 119/119 |
| Held-out paraphrase Top-1 | 28/28 |
| Held-out paraphrase Top-3 | 28/28 |
| Runtime active expected outcome | 26/26 |
| Output policy violation trên active | 0 |
| Bốn transcript Messenger | 4/4 |
| T01–T12 | 12/12 |
| Full suite với FAQ eval bật | 278 pass, 4 skip |
| FAQ Markdown active trong PostgreSQL | 8 |

Bốn test bị skip là integration phụ thuộc điều kiện ngoài bộ gate hiện tại;
không có test fail. Pytest còn một cảnh báo deprecation từ `fastapi.testclient`,
không ảnh hưởng kết quả nghiệp vụ.

## Những lỗi F6 đã phát hiện và sửa

1. Evaluator cũ chỉ chạy câu đầu của 47 dòng, so độ giống văn bản và vẫn exit 0
   khi có FAIL. Evaluator mới chạy đủ 119 biến thể, có baseline và exit khác 0
   khi metric giảm.
2. `Rạch Giá` trong dealer context có thể bị hiểu nhầm là hỏi giá. Quy tắc mới
   phân biệt marker giá ngắn với ngữ cảnh thương mại và giữ dealer workflow.
3. Yêu cầu làm đại lý từng rơi vào dealer lookup. Nhóm
   `sales_lead_markers` cấu hình được chuyển đúng sang `SALES_LEAD`.
4. Câu chọn/pha/trộn phân từng rơi vào product lookup. Nhóm
   `agri_question_markers` chuyển sang luồng nông học fail-closed.
5. `SALES_LEAD` trước đây không có composer riêng. Workflow mới chỉ xác nhận
   chuyển nhân viên khi đủ khu vực + số điện thoại và durable handoff task đã
   được tạo.
6. Bốn transcript cũ bắt đầu bằng state riêng; hai transcript tái tạo pipeline
   giữa các lượt để chứng minh state vẫn còn sau worker restart.

Các marker là taxonomy ngôn ngữ trong cấu hình, không chứa câu trả lời kinh
doanh, tên đại lý hoặc tên sản phẩm hardcode.

## Dữ liệu production local

- Batch Markdown:
  `d58062756b21c8da2ec8c4c19492df2636b6d526cbefc3416aed16c1058e4741`.
- Publication CFC version: `2`.
- 44 dòng có đáp án đã qua bước approve staging.
- Read model chỉ bật 8 dòng có `source_active=true`; 36 dòng pending vẫn không
  được retrieval production phục vụ khách.
- Snapshot Excel CFC cũ chứa 47 FAQ và 0 product record; publication Markdown
  thay snapshot FAQ cũ, không làm mất catalog sản phẩm CFC trong batch này.

## Lệnh nghiệm thu

```bash
python scripts/build_cfc_faq_test_cases.py --check
RUN_CFC_FAQ_EVAL=1 pytest -q
python scripts/evaluate_cfc_faq.py --live --check-production --check
```

Artefact chi tiết:

- `reports/cfc_faq_evaluation.json`
- `reports/cfc_faq_evaluation.md`
- `tests/fixtures/cfc_conversation_replays.json`
- `tests/fixtures/cfc_faq_f6_baseline.json`

## Việc chưa thuộc F6

- 36 dòng pending cần đúng người duyệt trước khi đổi `source_active=true`.
- Ba dòng FAQ thiếu đáp án vẫn bị disable.
- Shadow/canary, thời gian quan sát và business sign-off là Phase F7; F6 PASS
  không tự cho phép bật rộng auto-reply production.
