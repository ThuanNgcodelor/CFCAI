# CFC live regression record — 2026-10-26

Nguồn kiểm chứng: PostgreSQL `inbox_events`, `conversation_messages`,
`conversation_slots`, `outbox_messages`; Redis CRM; hội thoại Messenger của tài
khoản test `CFC:29357217407195130`.

## Test 1 — Cobanic và hội thoại tư vấn nối tiếp

- Kết quả: **FAIL**.
- Câu hỏi Cobanic tạo đúng một outbox và không còn placeholder
  `{so_dien_thoai_khach}`.
- Ba phản hồi tư vấn gần giống nhau thuộc ba batch khác nhau, cho thấy workflow
  tư vấn không hoàn tất/kế thừa ngữ cảnh hợp lý.
- Outbox liên quan: `95`–`98`.

## Test 2 — Tìm đại lý theo địa bàn

- Kết quả: **FAIL**.
- `Rạch giá kiên giang có ko` bị ép sai sang `PRICE_HANDOFF` vì marker `giá`
  khớp chuỗi con trong địa danh `Rạch Giá`.
- Gazetteer chưa có Rạch Giá và ánh xạ tên cũ Kiên Giang sang địa giới An Giang
  hiện hành.
- CRM có record tại phường Vĩnh Thông, tỉnh An Giang, thuộc khu vực Rạch Giá cũ.
- Fallback làm lộ thuật ngữ nội bộ `snapshot CRM`.
- Lượt hỏi Cần Thơ trả về ba record có địa chỉ CRM và đạt yêu cầu.
- Outbox liên quan: `100`–`103`.

## Test 3 — Giá, đại lý, Cobanic và thu thập số điện thoại

- Kết quả: **MOSTLY PASS / CÓ LỖI**.
- Đạt: chuẩn hóa câu giá viết dính, không bịa giá số, nhận Cobanic 21/30 và số
  điện thoại `0388509046`.
- Sai xưng hô: `Chào em`, `Anh sẽ báo giá cho em`, `Chào chị/chú`.
- Sai cam kết: tự nói `em sẽ gửi hàng tận nơi` khi chưa có căn cứ giao nhận.
- Tìm điểm bán chỉ phân giải tới cấp tỉnh Vĩnh Long thay vì khu vực gần chợ mà
  khách nêu; một địa chỉ CRM nguồn bị lỗi định dạng.
- Outbox liên quan: `104`–`110`.

## Test 4 — Cobanic 30, một tấn và follow-up kỹ thuật

- Kết quả: **PASS WITH ISSUES**.
- Đạt: không bịa giá, nhận đúng Cobanic 30, số lượng `1 tấn`, số điện thoại và
  gắn liên hệ kinh doanh/hotline từ cấu hình.
- Sai xưng hô/persona: `Chào em`, `chị sẽ liên hệ`, `Anh/chị ơi`,
  `Chào chị/em`, `của chị`, `Chúng tôi`.
- `tôi muốn rải mít` vẫn bị giữ trong `PRICE_HANDOFF` thay vì chuyển sang tư vấn
  nông nghiệp.
- Outbox liên quan: `111`–`114`.

## Quy chuẩn rút ra

- Bot chỉ tự xưng `em` hoặc `bên em`; luôn gọi khách là `anh/chị`.
- Không suy đoán tuổi/giới tính; không dùng `chị/chú`, `chị/em`, `chào em`,
  `cô/bác`, `anh/chị ơi` hoặc đảo vai người nói.
- Không tự hứa giao hàng/gọi lại; phải nêu đúng chủ thể `nhân viên phụ trách`.
- Không đưa thuật ngữ kỹ thuật như `snapshot CRM`, tên slot hay placeholder ra
  câu trả lời khách.
- Intent địa danh phải được phân giải trước các marker trùng chuỗi như chữ
  `giá` trong `Rạch Giá`.
