# Sửa tiếp nhận ảnh và prompt — 2026-10-27

## Vấn đề và bằng chứng

Ảnh chụp người dùng cung cấp cho thấy khách đã gửi ảnh vườn nhưng bot yêu cầu
chụp ảnh và hứa liên hệ trước 15h30, đồng thời gọi cây là “a”.

Đã xác nhận trong code trước sửa:

- `compose_image_inquiry_response` truyền mốc liên hệ vào generator dù không
  có bằng chứng đặt lịch; fallback cũng chứa lời hẹn liên hệ.
- Payload không biểu diễn rõ đã nhận ảnh nhưng chưa phân tích pixel.
- Validator chưa có kiểm tra yêu cầu gửi lại ảnh và cam kết liên hệ cho nhánh ảnh.
- Bộ chuẩn hóa có thể nhận đại từ viết tắt/cụm chỉ vị trí ảnh làm tên cây.

Chưa đối chiếu được batch live của ảnh chụp: yêu cầu Docker bị hệ thống phê
duyệt công cụ từ chối do giới hạn sử dụng. Không khẳng định đã truy nguyên raw
model output hoặc attachment delivery của batch đó.

## Thay đổi

- `config/prompts/intent.md`: giữ schema hiện tại; làm rõ nhu cầu mua lẻ, đại lý,
  tư vấn chọn phân, chuyển chủ đề, số điện thoại và metadata ảnh; bỏ chỉ dẫn
  mâu thuẫn về AGRI_ADVICE. Không thêm intent ngoài enum.
- `config/prompts/response.md`: tách prompt diễn đạt ra file, dùng chung chính sách
  cho CFC/ZEO, giữ brand riêng. Phân biệt nhận ảnh với phân tích ảnh; không hẹn
  gọi hoặc xác nhận tác vụ khi không được backend cho phép.
- Image composer: payload có receipt/vision state, missing information và quyền
  cam kết liên hệ; không truyền deadline. Fallback hỏi tối đa hai thông tin thiếu,
  không hỏi lại cây/giai đoạn đã biết và không tự kê đơn.
- Validator: kiểm tra yêu cầu gửi/chụp lại ảnh và lời hứa liên hệ/giờ hẹn không
  được phép ở nhánh ảnh; fallback cũng phải qua cùng kiểm tra.
- Chuẩn hóa ngôn ngữ cấu hình: loại đại từ viết tắt và cụm chỉ vị trí trong ảnh
  khỏi crop. Không thêm câu người dùng vào bảng ánh xạ câu hỏi/câu trả lời.
- Khi thiếu file response prompt, generator trả None để dùng fallback thay vì
  làm hỏng lượt trả lời.

## Test đã chạy

```bash
.venv/bin/python -m pytest -q --tb=short tests/unit tests/integration/test_workflows.py tests/eval/test_qwen_understanding.py -k 'not test_workflow_product_cobanic_ambiguous_name_requests_disambiguation'
# 195 passed, 7 skipped, 1 deselected, 5 subtests passed

.venv/bin/python -m pytest tests/eval/test_regression_full.py -q --tb=short
# 12 passed (T01–T12)

.venv/bin/ruff check src/chatbot/modules/llm/ollama.py src/chatbot/modules/workflows/composer.py src/chatbot/modules/workflows/policy_validator.py tests/unit/test_image_response_contract.py tests/integration/test_workflows.py
# All checks passed!

git diff --check
# Exit 0
```

Ca deselected đã được thử ở lần đầu nhưng lỗi kết nối PostgreSQL; đó là test
catalog phụ thuộc DB/Redis thật, không được tính pass. Bảy ca live Ollama opt-in
chưa chạy. Test mới dùng model giả lập cố tình trả sai để chứng minh payload,
validator, fallback và pipeline xử lý an toàn; không chứng minh chất lượng model
thật của prompt mới. T01–T12 là regression tự động, không phải Meta live rehearsal.

## Áp dụng và kiểm tra thật còn lại

Chưa restart container, chưa reset hội thoại, chưa gửi tin Meta trong lượt này.
Prompt intent được load khi khởi tạo client, nên worker phải khởi động lại.

```bash
./build/manage.sh restart
./build/manage.sh logs worker
```

Gửi ảnh kèm nhu cầu tư vấn, ảnh không caption, rồi ảnh khi đã biết cây/giai đoạn.
Kiểm tra nhận ảnh, không xin ảnh lại, không tự hẹn giờ, không tạo tên cây từ đại từ.
Thử ảnh kèm hỏi giá/tên sản phẩm cụ thể để bảo đảm vẫn giữ workflow tương ứng.
Không cần reset nếu đang kiểm tra giữ ngữ cảnh; chỉ reset giữa các kịch bản độc lập.

Đây chưa phải vision: hệ thống mới biết có ảnh từ attachment metadata. Sửa prompt
không tự bổ sung khả năng đọc pixel/chẩn đoán bệnh. Bộ lọc ngôn ngữ vẫn cần live
eval cho các cách diễn đạt khác; không tuyên bố chặn được mọi câu sai.
