# CFC FAQ evaluation

Generated: `2026-10-26T08:17:58.551028+00:00`

## Summary

- Source rows: **47**
- Answerable rows: **44**
- Missing-answer rows: **3**
- Answerable question variants: **119**
- Retrieval top-1: **109/119**
- Retrieval top-3: **118/119**
- ZEO isolation: **119/119**
- Runtime status: **COMPLETED**
- Runtime PASS/PARTIAL/FAIL/NO_REFERENCE: **{'FAIL': 44, 'NO_REFERENCE': 3}**
- Published FAQ records in current runtime: **0**

Exact source matching only proves consistency with the Markdown file; it does not
scientifically approve agronomy claims. Rows carrying strong claims remain review items.

## Source review

- Rows conflicting with the required salutation/persona policy: **36**
- Rows containing strong percentage/agronomy claims: **18**
- Missing answers: CFC-FAQ-004, CFC-FAQ-017, CFC-FAQ-019

## Runtime representative cases

| Case | Topic | Intent | Result | Exact | Recall | Violations |
|---|---|---|---:|---:|---:|---|
| CFC-FAQ-001 | Giờ mở cửa | UNKNOWN | FAIL | yes | 1.00 | customer_called_ban |
| CFC-FAQ-002 | Danh mục phân bón | PRODUCT_INQUIRY | FAIL | no | 0.35 | — |
| CFC-FAQ-003 | Giao hàng / nhận hàng | ORDER_TRACKING | FAIL | no | 0.15 | — |
| CFC-FAQ-004 | Mua hàng / link sản phẩm | DEALER_LOOKUP | NO_REFERENCE | no | — | — |
| CFC-FAQ-005 | Nhập hàng / làm đại lý | DEALER_LOOKUP | FAIL | no | 0.48 | — |
| CFC-FAQ-006 | Cần hỗ trợ / gặp admin | HUMAN_REQUEST | FAIL | no | 0.25 | — |
| CFC-FAQ-007 | Địa chỉ công ty | DEALER_LOOKUP | FAIL | no | 0.29 | internal_term |
| CFC-FAQ-008 | Giới thiệu công ty | HUMAN_REQUEST | FAIL | no | 0.00 | — |
| CFC-FAQ-009 | Phân NPK | PRODUCT_INQUIRY | FAIL | no | 0.26 | — |
| CFC-FAQ-010 | Phân hữu cơ | PRODUCT_INQUIRY | FAIL | no | 0.35 | — |
| CFC-FAQ-011 | Giá phân bón | PRICE_INQUIRY | FAIL | no | 0.32 | — |
| CFC-FAQ-012 | Tìm đại lý / nhà phân phối gần nhất | DEALER_LOOKUP | FAIL | no | 0.28 | internal_term |
| CFC-FAQ-013 | Đặt mua phân bón | PRODUCT_INQUIRY | FAIL | no | 0.37 | — |
| CFC-FAQ-014 | Giao phân về tỉnh / khu vực | PRICE_INQUIRY_DETAIL | FAIL | no | 0.19 | — |
| CFC-FAQ-015 | Liều lượng / cách dùng / phối trộn | PRICE_INQUIRY | FAIL | no | 0.21 | — |
| CFC-FAQ-016 | Tư vấn phân theo cây trồng | AGRI_ADVICE | FAIL | no | 0.32 | — |
| CFC-FAQ-017 | Sản phẩm ngoài phân bón (nước giặt, nước rửa… | PRODUCT_INQUIRY | NO_REFERENCE | no | — | — |
| CFC-FAQ-018 | Hỏi lại yêu cầu đã gửi | CONTACT_REQUEST | FAIL | no | 0.05 | — |
| CFC-FAQ-019 | Website Cò Bay | UNKNOWN | NO_REFERENCE | no | — | customer_called_ban |
| CFC-FAQ-020 | Sầu riêng nhú đọt + trái non | PRICE_INQUIRY | FAIL | no | 0.12 | — |
| CFC-FAQ-021 | Chống rụng hoa, dai cuống | PRODUCT_INQUIRY | FAIL | no | 0.13 | — |
| CFC-FAQ-022 | Giai đoạn xả nhụy, hãm đọt | AGRI_ADVICE | FAIL | no | 0.11 | — |
| CFC-FAQ-023 | Nuôi trái non, chống méo trái | PRODUCT_INQUIRY | FAIL | no | 0.15 | — |
| CFC-FAQ-024 | Vàng lá, rễ đen, thối rễ | AGRI_ADVICE | FAIL | no | 0.06 | — |
| CFC-FAQ-025 | Kali nuôi trái trước thu hoạch | PRODUCT_INQUIRY | FAIL | no | 0.10 | — |
| CFC-FAQ-026 | Chống sượng cơm, cháy múi, tích nước | AGRI_ADVICE | FAIL | no | 0.07 | — |
| CFC-FAQ-027 | Phục hồi cây sau thu hoạch | PRODUCT_INQUIRY | FAIL | no | 0.09 | — |
| CFC-FAQ-028 | Làm bông, tạo mầm hoa | PRODUCT_INQUIRY | FAIL | no | 0.09 | — |
| CFC-FAQ-029 | Kali trắng và Kali đỏ | PRODUCT_INQUIRY | FAIL | no | 0.16 | — |
| CFC-FAQ-030 | Giá DAP, Urê và xu hướng giá | PRICE_INQUIRY | FAIL | no | 0.24 | — |
| CFC-FAQ-031 | So sánh với phân nhập khẩu | PRICE_INQUIRY | FAIL | no | 0.06 | — |
| CFC-FAQ-032 | Định mức hữu cơ tiết kiệm chi phí | PRICE_INQUIRY | FAIL | no | 0.14 | — |
| CFC-FAQ-033 | Công nợ, ghi sổ cuối vụ | PRICE_INQUIRY | FAIL | no | 0.17 | — |
| CFC-FAQ-034 | NPK Tháp Cao (phức hợp) khác phân trộn | PRODUCT_INQUIRY | FAIL | no | 0.12 | — |
| CFC-FAQ-035 | Cách thử phân bón thật giả | AGRI_ADVICE | FAIL | no | 0.08 | — |
| CFC-FAQ-036 | Phân bị ẩm, vón cục; bảo quản | PRODUCT_INQUIRY | FAIL | no | 0.03 | — |
| CFC-FAQ-037 | Đất phèn mặn | PRODUCT_INQUIRY | FAIL | no | 0.13 | — |
| CFC-FAQ-038 | Bón phân mùa mưa dầm | AGRI_ADVICE | FAIL | no | 0.07 | — |
| CFC-FAQ-039 | Cải tạo đất chai cứng, bạc màu | AGRI_ADVICE | FAIL | no | 0.07 | — |
| CFC-FAQ-040 | Thiếu vi lượng TE, vàng lá gân xanh | AGRI_ADVICE | FAIL | no | 0.11 | — |
| CFC-FAQ-041 | Pha phân bón lá với thuốc BVTV | PRODUCT_INQUIRY | FAIL | no | 0.09 | — |
| CFC-FAQ-042 | Trộn NPK với phân hữu cơ | PRODUCT_INQUIRY | FAIL | no | 0.06 | — |
| CFC-FAQ-043 | Phân tưới nhỏ giọt (Fertigation) | PRODUCT_INQUIRY | FAIL | no | 0.25 | — |
| CFC-FAQ-044 | Hữu cơ trước, hóa học sau | PRICE_INQUIRY | FAIL | no | 0.04 | — |
| CFC-FAQ-045 | Dấu hiệu vi sinh hoạt động trong đất | AGRI_ADVICE | FAIL | no | 0.04 | — |
| CFC-FAQ-046 | Phân chuồng tươi có cần ủ hoai không | PRODUCT_INQUIRY | FAIL | no | 0.08 | — |
| CFC-FAQ-047 | Vi sinh và thuốc trị nấm hóa học | PRICE_INQUIRY | FAIL | no | 0.03 | — |

## Runtime failures and partial matches

### CFC-FAQ-001 — Giờ mở cửa

- Question: `Shop mở cửa lúc mấy giờ?`
- Intent: `UNKNOWN`
- Expected: Dạ shop Cò Bay mở cửa từ 8:00 đến 21:00 mỗi ngày nha bạn.
- Actual: Dạ shop Cò Bay mở cửa từ 8:00 đến 21:00 mỗi ngày nha bạn.
- Violations: customer_called_ban

### CFC-FAQ-002 — Danh mục phân bón

- Question: `Có những loại phân bón nào?`
- Intent: `PRODUCT_INQUIRY`
- Expected: Dạ chào bạn, Cò Bay hiện có các dòng phân bón như NPK, Hữu cơ,... Bạn đang cần tư vấn cho loại cây trồng nào để bên mình hỗ trợ phù hợp hơn ạ?
- Actual: Dạ hiện tại Cò Bay chưa tìm thấy mã sản phẩm phù hợp trong danh mục. Anh/chị cho bên mình xin thêm tên cụ thể hoặc nhu cầu sử dụng để bên mình hỗ trợ chi tiết nhé!
- Violations: none

### CFC-FAQ-003 — Giao hàng / nhận hàng

- Question: `Có giao hàng không?`
- Intent: `ORDER_TRACKING`
- Expected: Dạ có, chúng tôi hiện tại giao hàng thông qua 02 hình thức chính là nhận trực tiếp tại Công ty hoặc nhận tại nhà phân phối gần bạn nhất nhé ạ.
- Actual: Dạ để em kiểm tra hành trình và tình trạng đơn hàng cho mình, anh/chị cho em xin Số điện thoại đặt hàng hoặc Mã đơn hàng nhé ạ 🌾
- Violations: none

### CFC-FAQ-005 — Nhập hàng / làm đại lý

- Question: `Muốn nhập hàng Muốn làm đại lý Muốn phân phối sản phẩm Muốn kinh doanh phân bón Làm nhà phân phối được không?`
- Intent: `DEALER_LOOKUP`
- Expected: Bạn vui lòng để lại số điện thoại và khu vực muốn kinh doanh, admin sẽ gửi đến nhà phân phối hoặc nhân viên khu vực liên hệ bạn sớm nhất ạ.
- Actual: Để em kiểm tra điểm bán gần nhất, anh/chị cho em xin tỉnh/huyện mình đang ở ạ? Sau khi có khu vực, mình có thể để lại số điện thoại nếu cần nhân viên hỗ trợ liên hệ.
- Violations: none

### CFC-FAQ-006 — Cần hỗ trợ / gặp admin

- Question: `Cần hỗ trợ Hỗ trợ giúp mình Muốn gặp admin Cần tư vấn thêm Có người hỗ trợ không?`
- Intent: `HUMAN_REQUEST`
- Expected: Dạ bạn cần admin hỗ trợ gì về sản phẩm hay dịch vụ ạ?
- Actual: Dạ em đã chuyển tin nhắn của anh/chị đến nhân viên phụ trách fanpage rồi ạ. Bạn sẽ vào hỗ trợ mình ngay nhé! Cảm ơn anh/chị đã kiên nhẫn ạ 😊
- Violations: none

### CFC-FAQ-007 — Địa chỉ công ty

- Question: `Địa chỉ ở đâu?`
- Intent: `DEALER_LOOKUP`
- Expected: Dạ, địa chỉ Công ty ở: Trục chính KCN Trà Nóc 1, phường Thới An Đông, thành phố Cần Thơ ạ.
- Actual: Dạ Mình đã kiểm tra khu vực địa chỉ ở đâu?, nhưng snapshot CRM hiện chưa có điểm bán được xác nhận tại đây nên em không muốn chỉ nhầm địa chỉ. Anh/chị có thể cho em thêm xã/ấp cụ thể hoặc nhắn “gặp nhân viên” nếu cần kiểm tra thủ công ạ.
- Violations: internal_term

### CFC-FAQ-008 — Giới thiệu công ty

- Question: `Giới thiệu về công ty bạn đi Công ty bạn là công ty gì?`
- Intent: `HUMAN_REQUEST`
- Expected: Dạ, Cò Bay là thương hiệu phân bón thuộc Công ty Cổ phần Phân bón và Hóa chất Cần Thơ (thành lập năm 1977, hơn 45 năm kinh nghiệm), hiện cung cấp các dòng phân bón như NPK và phân Hữu cơ. Địa chỉ Công ty ở: Trục chính KCN Trà Nóc 1, phường Thới An Đông, thành phố Cần Thơ ạ.
- Actual: Dạ em đã chuyển tin nhắn của anh/chị đến nhân viên phụ trách fanpage rồi ạ. Bạn sẽ vào hỗ trợ mình ngay nhé! Cảm ơn anh/chị đã kiên nhẫn ạ 😊
- Violations: none

### CFC-FAQ-009 — Phân NPK

- Question: `Cò Bay có NPK không?`
- Intent: `PRODUCT_INQUIRY`
- Expected: Dạ Cò Bay hiện có dòng phân bón NPK chất lượng cao nha bạn. Bạn đang cần tư vấn cho cây trồng nào và khu vực nào để kỹ sư Cò Bay hỗ trợ phù hợp hơn ạ?
- Actual: Dạ hiện tại Cò Bay chưa tìm thấy mã sản phẩm phù hợp trong danh mục. Anh/chị cho bên mình xin thêm tên cụ thể hoặc nhu cầu sử dụng để bên mình hỗ trợ chi tiết nhé!
- Violations: none

### CFC-FAQ-010 — Phân hữu cơ

- Question: `Cò Bay có phân hữu cơ không?`
- Intent: `PRODUCT_INQUIRY`
- Expected: Dạ Cò Bay hiện có dòng phân bón Hữu cơ nha bạn. Bạn cho mình biết loại cây trồng và khu vực để bên mình tư vấn cách chọn sản phẩm phù hợp hơn ạ.
- Actual: Dạ hiện tại Cò Bay chưa tìm thấy mã sản phẩm phù hợp trong danh mục. Anh/chị cho bên mình xin thêm tên cụ thể hoặc nhu cầu sử dụng để bên mình hỗ trợ chi tiết nhé!
- Violations: none

### CFC-FAQ-011 — Giá phân bón

- Question: `Giá phân bón Cò Bay bao nhiêu?`
- Intent: `PRICE_INQUIRY`
- Expected: Dạ bảng giá phân bón Cò Bay phụ thuộc vào từng dòng sản phẩm, quy cách đóng bao và khu vực phân phối. Bạn gửi giúp mình số điện thoại, khu vực và loại cây trồng cần bón, kỹ sư hoặc nhân viên Cò Bay sẽ kiểm tra và liên hệ báo giá chính xác nhất nha.
- Actual: Dạ giá 1 bao phân tùy khu vực và số lượng nên bên em không báo số cụ thể trên chat ạ; bạn kinh doanh sẽ báo giá chính xác. Anh/chị có thể để lại số điện thoại để được liên hệ nha 🌾 ☎️ Trưởng phòng Kinh doanh Lê Trọng Nhơn: 0981 205 448 ☎️ Hotline công ty: 1900 5307
- Violations: none

### CFC-FAQ-012 — Tìm đại lý / nhà phân phối gần nhất

- Question: `Ở khu vực tôi có đại lý Cò Bay không?`
- Intent: `DEALER_LOOKUP`
- Expected: Dạ bạn gửi giúp mình số điện thoại và khu vực/tỉnh thành cụ thể. Admin sẽ chuyển thông tin để nhà phân phối hoặc nhân viên phụ trách khu vực liên hệ hướng dẫn điểm mua gần bạn nhất ạ.
- Actual: Dạ Mình đã kiểm tra khu vực khu vực tôi, nhưng snapshot CRM hiện chưa có điểm bán được xác nhận tại đây nên em không muốn chỉ nhầm địa chỉ. Anh/chị có thể cho em thêm xã/ấp cụ thể hoặc nhắn “gặp nhân viên” nếu cần kiểm tra thủ công ạ.
- Violations: internal_term

### CFC-FAQ-013 — Đặt mua phân bón

- Question: `Tôi muốn đặt phân Cò Bay Cho mình mua phân bón Cò Bay Mình muốn đặt NPK Đặt phân hữu cơ như thế nào?`
- Intent: `PRODUCT_INQUIRY`
- Expected: Dạ Cò Bay đã ghi nhận nhu cầu mua phân bón của bạn. Bạn gửi thêm số điện thoại, khu vực và loại cây trồng cần bón để bên mình kiểm tra đúng sản phẩm và hỗ trợ đặt hàng nha.
- Actual: Dạ hiện tại Cò Bay chưa tìm thấy mã sản phẩm phù hợp trong danh mục. Anh/chị cho bên mình xin thêm tên cụ thể hoặc nhu cầu sử dụng để bên mình hỗ trợ chi tiết nhé!
- Violations: none

### CFC-FAQ-014 — Giao phân về tỉnh / khu vực

- Question: `Ship phân bón về tỉnh được không?`
- Intent: `PRICE_INQUIRY_DETAIL`
- Expected: Dạ hiện bên mình hỗ trợ giao nhận thông qua 2 hình thức: nhận trực tiếp tại Công ty hoặc nhận tại nhà phân phối gần bạn nhất. Bạn gửi khu vực/tỉnh thành để bên mình kiểm tra hình thức nhận hàng phù hợp nha.
- Actual: Dạ giá 1 bao phân tùy khu vực và số lượng nên bên em không báo số cụ thể trên chat ạ; bạn kinh doanh sẽ báo giá chính xác. Anh/chị có thể để lại số điện thoại để được liên hệ nha 🌾 ☎️ Trưởng phòng Kinh doanh Lê Trọng Nhơn: 0981 205 448 ☎️ Hotline công ty: 1900 5307
- Violations: none

### CFC-FAQ-015 — Liều lượng / cách dùng / phối trộn

- Question: `Bón bao nhiêu kg cho 1 công lúa?`
- Intent: `PRICE_INQUIRY`
- Expected: Dạ phần liều lượng, cách bón hoặc phối trộn cần kỹ sư nông nghiệp kiểm tra theo cây trồng, giai đoạn và khu vực canh tác. Bạn gửi giúp mình loại cây trồng, diện tích/khu vực và số điện thoại để kỹ sư Cò Bay tư vấn an toàn, đúng nhu cầu ạ.
- Actual: Dạ giá 1 bao phân tùy khu vực và số lượng nên bên em không báo số cụ thể trên chat ạ; bạn kinh doanh sẽ báo giá chính xác. Anh/chị có thể để lại số điện thoại để được liên hệ nha 🌾 ☎️ Trưởng phòng Kinh doanh Lê Trọng Nhơn: 0981 205 448 ☎️ Hotline công ty: 1900 5307
- Violations: none

### CFC-FAQ-016 — Tư vấn phân theo cây trồng

- Question: `Tư vấn phân bón cho cây trồng giúp mình Cây lúa nên dùng phân nào?`
- Intent: `AGRI_ADVICE`
- Expected: Dạ mình sẵn sàng hỗ trợ ạ. Bạn cho biết loại cây trồng, giai đoạn cây hiện tại và khu vực/tỉnh thành để kỹ sư Cò Bay tư vấn dòng phân bón phù hợp hơn nha.
- Actual: Dạ Cò Bay cần thêm loại cây, giai đoạn cây để tra đúng hướng dẫn đã được duyệt và tư vấn sát vườn mình ạ. ☎️ Khuyến nông Lê Thanh Đạm: 0353 857 516 ☎️ Hotline công ty: 1900 5307
- Violations: none

### CFC-FAQ-018 — Hỏi lại yêu cầu đã gửi

- Question: `Đã gửi thông tin rồi có ai liên hệ chưa?`
- Intent: `CONTACT_REQUEST`
- Expected: Dạ mình đã ghi nhận tin nhắn của bạn. Nếu bạn đã gửi số điện thoại và khu vực, admin đang chuyển thông tin để kỹ sư hoặc nhân viên Cò Bay liên hệ lại sớm nhất ạ.
- Actual: Dạ, để hỗ trợ khách hàng, anh/chị có thể liên hệ trực tiếp: ☎️ Trưởng phòng Kinh doanh Lê Trọng Nhơn: 0981 205 448 ☎️ Hotline công ty: 1900 5307
- Violations: none

### CFC-FAQ-020 — Sầu riêng nhú đọt + trái non

- Question: `Cây sầu riêng đang nhú mũi giáo rải dòng nào để mập đọt mà không rụng trái non?`
- Intent: `PRICE_INQUIRY`
- Expected: Dạ chào bạn! Khi sầu riêng đang nhú 'mũi giáo' đồng thời đang mang trái non, bạn nên ưu tiên bón dòng Hữu cơ sinh học Cobanic kết hợp NPK cân bằng hàm lượng đạm vừa phải (như NPK Cò Bay 20-20-15 TE hoặc 16-16-16) với liều nhẹ, chia làm nhiều lần bón. Tránh rải đạm đơn hoặc NPK đạm cao vì sẽ gây phó…
- Actual: Dạ giá 1 bao phân tùy khu vực và số lượng nên bên em không báo số cụ thể trên chat ạ; bạn kinh doanh sẽ báo giá chính xác. Anh/chị có thể để lại số điện thoại để được liên hệ nha 🌾 ☎️ Trưởng phòng Kinh doanh Lê Trọng Nhơn: 0981 205 448 ☎️ Hotline công ty: 1900 5307
- Violations: none

### CFC-FAQ-021 — Chống rụng hoa, dai cuống

- Question: `Cây đang ra bông dùng loại phân nào để dai cuống chống rụng sinh lý?`
- Intent: `PRODUCT_INQUIRY`
- Expected: Dạ trong giai đoạn cây đang ra bông, để dai cuống và chống rụng hoa sinh lý, bạn nên bổ sung phân bón giàu Canxi, Bo và Kẽm kết hợp NPK Cò Bay hàm lượng Lân và Kali cao (như NPK Cò Bay 15-15-15 hoặc phân bón lá vi lượng chuyên hoa). Tuyệt đối hạn chế bón phân có hàm lượng Đạm cao lúc này để tránh c…
- Actual: Dạ hiện tại Cò Bay chưa tìm thấy mã sản phẩm phù hợp trong danh mục. Anh/chị cho bên mình xin thêm tên cụ thể hoặc nhu cầu sử dụng để bên mình hỗ trợ chi tiết nhé!
- Violations: none

### CFC-FAQ-022 — Giai đoạn xả nhụy, hãm đọt

- Question: `Giai đoạn xả nhụy nên bón gì để đậu trái đều mà hãm được đọt không cho phóng tược?`
- Intent: `AGRI_ADVICE`
- Expected: Dạ giai đoạn xả nhụy là thời điểm cực kỳ nhạy cảm! Để giúp đậu trái đều và chặn cây phóng đọt non, bạn nên giữ ẩm vừa phải, ngưng rải phân gốc đạm cao, ưu tiên phun qua lá các dòng Bo, Canxi hữu cơ kết hợp Kali trắng để dằn đọt. Khi trái đã chạy gai xanh ổn định mới bắt đầu nhử nhẹ NPK Cò Bay cân đ…
- Actual: Dạ Cò Bay cần thêm loại cây để tra đúng hướng dẫn đã được duyệt và tư vấn sát vườn mình ạ. ☎️ Khuyến nông Lê Thanh Đạm: 0353 857 516 ☎️ Hotline công ty: 1900 5307
- Violations: none

### CFC-FAQ-023 — Nuôi trái non, chống méo trái

- Question: `Trái non mới đậu rải NPK dòng nào để trái lớn nhanh như thổi mà không bị méo trái?`
- Intent: `PRODUCT_INQUIRY`
- Expected: Dạ khi trái non đã định hình (bằng quả trứng gà), để trái lớn nhanh, tròn đều và không bị giật hộc/méo trái, bạn nên dùng dòng NPK Cò Bay 20-20-15 TE hoặc NPK Cò Bay Ba Số Đều (15-15-15 / 16-16-16 TE) kết hợp bổ sung Trung - Vi lượng (Canxi, Magie). Nên chia nhỏ lượng bón định kỳ 10-12 ngày/lần. Bạ…
- Actual: Dạ hiện tại Cò Bay chưa tìm thấy mã sản phẩm phù hợp trong danh mục. Anh/chị cho bên mình xin thêm tên cụ thể hoặc nhu cầu sử dụng để bên mình hỗ trợ chi tiết nhé!
- Violations: none

### CFC-FAQ-024 — Vàng lá, rễ đen, thối rễ

- Question: `Vườn đang bị vàng lá rễ đen thui không ra rễ tơ tưới kích rễ loại nào cho cây tỉnh lại nhanh?`
- Intent: `AGRI_ADVICE`
- Expected: Dạ tình trạng rễ đen thui, không ra rễ tơ thường do đất bị chua (pH thấp) kết hợp nấm rễ tấn công. Quy trình cứu rễ chuẩn của Cò Bay gồm 3 bước: 1. Rải Lân nung chảy hoặc vôi để nâng pH đất lên > 5.5. 2. Xử lý nấm bệnh bằng hoạt chất trừ nấm hoặc vi sinh đối kháng Trichoderma/Bacillus. 3. Sau 5-7 n…
- Actual: Dạ Cò Bay cần thêm loại cây, giai đoạn cây để tra đúng hướng dẫn đã được duyệt và tư vấn sát vườn mình ạ. ☎️ Khuyến nông Cao Văn Được: 0939 852 529 ☎️ Hotline công ty: 1900 5307
- Violations: none

### CFC-FAQ-025 — Kali nuôi trái trước thu hoạch

- Question: `Sắp thu hoạch rồi đánh dòng Kali nào cho lên màu đẹp nặng ký nặng zem chắc hạt mà không cháy múi?`
- Intent: `PRODUCT_INQUIRY`
- Expected: Dạ trước khi thu hoạch 20-30 ngày, để trái lên màu cơm vàng đẹp, đậm vị, ngọt nước, chắc hạt (nặng zem) mà không gây cháy múi, bạn nên dùng dòng NPK Cò Bay chuyên nuôi trái chín có hàm lượng Kali Sunphat (Kali trắng) cao như NPK Cò Bay 15-5-20 TE, 16-6-18 TE hoặc Kali hữu cơ. Dòng Kali Sunphat giúp…
- Actual: Dạ hiện tại Cò Bay chưa tìm thấy mã sản phẩm phù hợp trong danh mục. Anh/chị cho bên mình xin thêm tên cụ thể hoặc nhu cầu sử dụng để bên mình hỗ trợ chi tiết nhé!
- Violations: none

### CFC-FAQ-026 — Chống sượng cơm, cháy múi, tích nước

- Question: `Làm sao để bón phân mà trái sầu riêng không bị sượng cơm cháy múi hay tích nước lúc mưa dầm?`
- Intent: `AGRI_ADVICE`
- Expected: Dạ hiện tượng sượng cơm, cháy múi và tích nước mùa mưa dầm thường do 3 nguyên nhân: thừa Đạm, thiếu Canxi - Bo - Magie và dư nước làm cây đi đọt non. Cách khắc phục: 1. Cắt giảm hoàn toàn Đạm từ 30 ngày trước cắt trái. 2. Bón NPK Cò Bay giàu Kali Sunphat (K2SO4) và bổ sung Canxi Bo định kỳ. 3. Làm …
- Actual: Dạ Cò Bay cần thêm loại cây, giai đoạn cây để tra đúng hướng dẫn đã được duyệt và tư vấn sát vườn mình ạ. ☎️ Khuyến nông Lê Thanh Đạm: 0353 857 516 ☎️ Hotline công ty: 1900 5307
- Violations: none

### CFC-FAQ-027 — Phục hồi cây sau thu hoạch

- Question: `Cây mới thu hoạch xong xơ xác quá rải hữu cơ nào kết hợp với đạm để bung đọt nhanh phục hồi lẹ cho vụ sau?`
- Intent: `PRODUCT_INQUIRY`
- Expected: Dạ sau thu hoạch cây bị kiệt sức, bạn cần tiến hành tỉa cành rửa vườn và phục hồi theo công thức: Bón gốc Hữu cơ Cobanic 30% (từ 3 - 5 kg/gốc tùy tuổi cây) kết hợp tưới kích rễ Humic, sau đó bón nhử NPK Cò Bay 20-20-15 TE hoặc 16-16-8 TE để kích đọt bung đồng loạt, lá dày bóng. Bộ đôi Hữu cơ Cobani…
- Actual: Dạ hiện tại Cò Bay chưa tìm thấy mã sản phẩm phù hợp trong danh mục. Anh/chị cho bên mình xin thêm tên cụ thể hoặc nhu cầu sử dụng để bên mình hỗ trợ chi tiết nhé!
- Violations: none

### CFC-FAQ-028 — Làm bông, tạo mầm hoa

- Question: `Sắp tới làm bông giờ bón Lân và Kali loại nào để ép cây phân hóa mầm hoa mạnh nhất?`
- Intent: `PRODUCT_INQUIRY`
- Expected: Dạ để ép cây tạo mầm hoa khỏe và ra hoa đồng loạt, công thức chuẩn là: 1. Dưới gốc: Bón Lân nung chảy kết hợp Kali Sunphat hoặc NPK Cò Bay công thức Lân cao (như NPK 10-50-10 hoặc 9-25-17). 2. Trên lá: Phun hoạt chất chặn đọt kết hợp MKP (Lân + Kali cao) để lá nhanh già lụa và hình thành mầm hoa. 3…
- Actual: Dạ hiện tại Cò Bay chưa tìm thấy mã sản phẩm phù hợp trong danh mục. Anh/chị cho bên mình xin thêm tên cụ thể hoặc nhu cầu sử dụng để bên mình hỗ trợ chi tiết nhé!
- Violations: none

### CFC-FAQ-029 — Kali trắng và Kali đỏ

- Question: `Cây đang nuôi trái lớn bón Kali trắng Kali Sunphat hay Kali đỏ thì êm hơn cho chất lượng trái xuất khẩu?`
- Intent: `PRODUCT_INQUIRY`
- Expected: Dạ với các dòng cây ăn trái nhạy cảm với gốc Clo (như sầu riêng, bưởi da xanh, mãng cầu, thuốc lá, tiêu) hoặc nông sản định hướng xuất khẩu, bạn **nên ưu tiên dùng Kali trắng (Kali Sunphat - K2SO4)**. Ưu điểm của Kali trắng: Không chứa gốc Clo gây sượng múi/cháy mép lá, giúp múi dẻo quánh, vỏ mỏng,…
- Actual: Dạ hiện tại Cò Bay chưa tìm thấy mã sản phẩm phù hợp trong danh mục. Anh/chị cho bên mình xin thêm tên cụ thể hoặc nhu cầu sử dụng để bên mình hỗ trợ chi tiết nhé!
- Violations: none

### CFC-FAQ-030 — Giá DAP, Urê và xu hướng giá

- Question: `Bao DAP Urê hôm nay giá bao nhiêu rồi tuần tới có nhích lên hay tuột xuống không?`
- Intent: `PRICE_INQUIRY`
- Expected: Dạ giá phân bón (DAP, Urê, NPK) biến động theo ngày theo giá nguyên liệu thế giới và chính sách vận chuyển từng khu vực. Để nhận thông báo bảng giá cập nhật sớm nhất hôm nay và dự báo xu hướng tuần tới từ Cò Bay, bạn vui lòng để lại số điện thoại và tỉnh/huyện đang canh tác. Chuyên viên kinh doanh …
- Actual: Dạ giá 1 bao phân tùy khu vực và số lượng nên bên em không báo số cụ thể trên chat ạ; bạn kinh doanh sẽ báo giá chính xác. Anh/chị có thể để lại số điện thoại để được liên hệ nha 🌾 ☎️ Trưởng phòng Kinh doanh Lê Trọng Nhơn: 0981 205 448 ☎️ Hotline công ty: 1900 5307
- Violations: none

### CFC-FAQ-031 — So sánh với phân nhập khẩu

- Question: `Loại phân Cò Bay này xài có êm bằng hàng ngoại cũ tui hay dùng không giá rẻ hơn nhiều không?`
- Intent: `PRICE_INQUIRY`
- Expected: Dạ phân bón CFC Cò Bay được sản xuất trên dây chuyền công nghệ Tháp Cao hiện đại, với nguồn nguyên liệu chọn lọc tương đương chuẩn quốc tế nhưng giá thành tiết kiệm hơn 15 - 25% do không phải chịu thuế nhập khẩu và chi phí vận chuyển biển cao. Đặc biệt, công thức phân Cò Bay được nghiên cứu chuyên …
- Actual: Dạ giá 1 bao phân tùy khu vực và số lượng nên bên em không báo số cụ thể trên chat ạ; bạn kinh doanh sẽ báo giá chính xác. Anh/chị có thể để lại số điện thoại để được liên hệ nha 🌾 ☎️ Trưởng phòng Kinh doanh Lê Trọng Nhơn: 0981 205 448 ☎️ Hotline công ty: 1900 5307
- Violations: none

### CFC-FAQ-032 — Định mức hữu cơ tiết kiệm chi phí

- Question: `Mua dòng hữu cơ vi sinh này tốn kém quá một gốc rải mấy ký là vừa túi tiền?`
- Intent: `PRICE_INQUIRY`
- Expected: Dạ để bón phân Hữu cơ Cobanic vừa khỏe cây vừa tiết kiệm chi phí tối đa, bạn nên áp dụng nguyên tắc: - Cây kiến thiết cơ bản (1-3 năm): 1 - 2 kg/gốc/đợt (mỗi năm 3-4 đợt). - Cây kinh doanh (nuôi trái): 3 - 5 kg/gốc sau khi thu hoạch để phục hồi bộ rễ. Mẹo tiết kiệm: Rải phân kết hợp cuốc xới nhẹ qu…
- Actual: Dạ giá 1 bao phân tùy khu vực và số lượng nên bên em không báo số cụ thể trên chat ạ; bạn kinh doanh sẽ báo giá chính xác. Anh/chị có thể để lại số điện thoại để được liên hệ nha 🌾 ☎️ Trưởng phòng Kinh doanh Lê Trọng Nhơn: 0981 205 448 ☎️ Hotline công ty: 1900 5307
- Violations: none

### CFC-FAQ-033 — Công nợ, ghi sổ cuối vụ

- Question: `Có cho ghi sổ không tới cuối vụ bán trái xong tui ra thanh toán một lượt nhé?`
- Intent: `PRICE_INQUIRY`
- Expected: Dạ chính sách công nợ (ghi sổ cuối vụ) sẽ do các Đại lý và Nhà phân phối Cò Bay tại địa phương trực tiếp xem xét và hỗ trợ cho bà con thân thiết. Công ty Cổ phần Phân bón & Hóa chất Cần Thơ (CFC) luôn có các chương trình trợ giá và liên kết đại lý để tạo điều kiện thuận lợi nhất cho nhà nông. Bạn đ…
- Actual: Dạ giá 1 bao phân tùy khu vực và số lượng nên bên em không báo số cụ thể trên chat ạ; bạn kinh doanh sẽ báo giá chính xác. Anh/chị có thể để lại số điện thoại để được liên hệ nha 🌾 ☎️ Trưởng phòng Kinh doanh Lê Trọng Nhơn: 0981 205 448 ☎️ Hotline công ty: 1900 5307
- Violations: none

### CFC-FAQ-034 — NPK Tháp Cao (phức hợp) khác phân trộn

- Question: `NPK này là hàng tháp cao phức hợp hay hàng trộn thủ công rải xuống có tan hết không?`
- Intent: `PRODUCT_INQUIRY`
- Expected: Dạ các dòng NPK chủ lực của Cò Bay được sản xuất bằng **Công nghệ Tháp Cao (Phức hợp)** tiên tiến nhất hiện nay! Khác biệt hoàn toàn với phân trộn 3 màu thủ công: 1. Từng hạt phân đều chứa đầy đủ N-P-K và vi lượng đồng nhất từ vỏ đến lõi, không bị phân lớp khi vận chuyển. 2. Hạt phân tròn bóng, độ …
- Actual: Dạ hiện tại Cò Bay chưa tìm thấy mã sản phẩm phù hợp trong danh mục. Anh/chị cho bên mình xin thêm tên cụ thể hoặc nhu cầu sử dụng để bên mình hỗ trợ chi tiết nhé!
- Violations: none

### CFC-FAQ-035 — Cách thử phân bón thật giả

- Question: `Cách thử phân bón thật giả tại nhà mẹo thử urê kali npk thật giả thử hòa tan urê vào nước có lạnh tay không`
- Intent: `AGRI_ADVICE`
- Expected: Dạ Cò Bay chia sẻ với bạn 3 mẹo kiểm tra phân bón thật - giả cực chuẩn ngay tại nhà: 1. **Thử Nước (Urê & Kali):** Urê thật tan rất nhanh và làm nước **lạnh buốt tay**. Kali đỏ thật tan hoàn toàn trong nước, nước có màu hồng/đỏ nhạt nhưng **không để lại lớp cặn bột gạch dày** ở đáy ly. 2. **Thử Lửa…
- Actual: Dạ Cò Bay cần thêm loại cây, giai đoạn cây để tra đúng hướng dẫn đã được duyệt và tư vấn sát vườn mình ạ. ☎️ Khuyến nông Cao Văn Được: 0939 852 529 ☎️ Hotline công ty: 1900 5307
- Violations: none

### CFC-FAQ-036 — Phân bị ẩm, vón cục; bảo quản

- Question: `Sao bao phân này mở ra thấy chảy nước bết dính vậy có bị rút ruột hàm lượng không?`
- Intent: `PRODUCT_INQUIRY`
- Expected: Dạ hiện tượng phân bón bị ẩm hoặc bết dính nhẹ thường do đặc tính hút ẩm tự nhiên của Đạm (Urê) và Kali khi tiếp xúc với không khí ẩm, hoàn toàn **không bị rút ruột hay giảm hàm lượng dinh dưỡng**. Cách bảo quản chuẩn: - Để bao phân trên pallet gỗ cách mặt đất 15-20cm, cách tường 20cm. - Bao đã mở …
- Actual: Dạ hiện tại Cò Bay chưa tìm thấy mã sản phẩm phù hợp trong danh mục. Anh/chị cho bên mình xin thêm tên cụ thể hoặc nhu cầu sử dụng để bên mình hỗ trợ chi tiết nhé!
- Violations: none

### CFC-FAQ-037 — Đất phèn mặn

- Question: `Đất vườn đang bị phèn mặn rải Lân nung chảy hay Canxi để hạ phèn trước khi bón NPK?`
- Intent: `PRODUCT_INQUIRY`
- Expected: Dạ khi đất bị nhiễm phèn hoặc hạn mặn, rễ cây bị bó và ngộ độc kim loại, bón NPK ngay sẽ làm rễ cháy nhanh hơn! Quy trình xử lý đất phèn mặn chuẩn: 1. **Hạ phèn:** Rải **Lân nung chảy** kết hợp Vôi/Canxi (từ 300 - 500 kg/ha) để cố định độc chất nhôm sắt, nâng pH đất lên mức an toàn (5.5 - 6.5). 2. …
- Actual: Dạ hiện tại Cò Bay chưa tìm thấy mã sản phẩm phù hợp trong danh mục. Anh/chị cho bên mình xin thêm tên cụ thể hoặc nhu cầu sử dụng để bên mình hỗ trợ chi tiết nhé!
- Violations: none

### CFC-FAQ-038 — Bón phân mùa mưa dầm

- Question: `Trời đang mưa dầm rải phân có sợ bị rửa trôi hết không có loại nào chậm tan không?`
- Intent: `AGRI_ADVICE`
- Expected: Dạ mùa mưa dầm nguy cơ thất thoát phân bón do rửa trôi và xói mòn rất lớn (lên tới 40 - 50%)! Bí quyết bón phân mùa mưa của Cò Bay: 1. **Chia nhỏ cữ bón:** Thay vì bón 1 lần nhiều phân, hãy chia làm 2-3 đợt bón cách nhau 10 ngày. 2. **Dùng Hữu cơ lót nền:** Rải Hữu cơ Cobanic giúp tăng dung tích hấ…
- Actual: Dạ Cò Bay cần thêm loại cây, giai đoạn cây để tra đúng hướng dẫn đã được duyệt và tư vấn sát vườn mình ạ. ☎️ Khuyến nông Cao Văn Được: 0939 852 529 ☎️ Hotline công ty: 1900 5307
- Violations: none

### CFC-FAQ-039 — Cải tạo đất chai cứng, bạc màu

- Question: `Đất đỏ bazan xài lâu năm bị chai cứng bón phân gì cho đất tơi xốp giữ nước tốt mùa khô?`
- Intent: `AGRI_ADVICE`
- Expected: Dạ đất đỏ bazan hoặc đất vườn canh tác lâu năm bị chai cứng là do mất đi lớp mùn hữu cơ và vi sinh vật bản địa. Giải pháp cải tạo đất bền vững của Cò Bay: 1. Bổ sung **Hữu cơ vi sinh Cobanic** định kỳ (3 - 5 tấn/ha/năm) để tái tạo kết cấu xốp như bọt biển cho đất, giúp giữ ẩm cực tốt qua 6 tháng mù…
- Actual: Dạ Cò Bay cần thêm loại cây, giai đoạn cây để tra đúng hướng dẫn đã được duyệt và tư vấn sát vườn mình ạ. ☎️ Khuyến nông Lê Thanh Đạm: 0353 857 516 ☎️ Hotline công ty: 1900 5307
- Violations: none

### CFC-FAQ-040 — Thiếu vi lượng TE, vàng lá gân xanh

- Question: `Cây bị vàng lá gân xanh có phải do thiếu vi lượng TE không?`
- Intent: `AGRI_ADVICE`
- Expected: Dạ hiện tượng 'vàng lá gân xanh' (thịt lá chuyển vàng nhưng gân lá vẫn giữ màu xanh) là dấu hiệu điển hình của việc cây bị **thiếu Trung - Vi lượng (Magiê, Kẽm, Sắt, Mangan, Bo)**. Cách xử lý nhanh: 1. Phun qua lá dung dịch vi lượng Chelate tổng hợp để lá hấp thụ tức thì sau 3-5 ngày. 2. Dưới gốc: …
- Actual: Dạ Cò Bay cần thêm loại cây, giai đoạn cây để tra đúng hướng dẫn đã được duyệt và tư vấn sát vườn mình ạ. ☎️ Khuyến nông Lê Thanh Đạm: 0353 857 516 ☎️ Hotline công ty: 1900 5307
- Violations: none

### CFC-FAQ-041 — Pha phân bón lá với thuốc BVTV

- Question: `Pha phân bón lá chung với thuốc sâu thuốc rầy xịt một lần có bị kết tủa đục nước không?`
- Intent: `PRODUCT_INQUIRY`
- Expected: Dạ bạn hoàn toàn có thể phối trộn phân bón lá với thuốc trừ sâu rầy để tiết kiệm công phun xịt, nhưng cần tuân thủ **Quy tắc thử nghiệm 3 phút**: 1. Múc 1 ca nước nhỏ, cho thuốc và phân bón lá vào khuấy đều. Nếu nước đồng nhất, không sủi bọt lạ, không kết tủa hay vón cục đóng cặn đáy ca thì phối tr…
- Actual: Dạ hiện tại Cò Bay chưa tìm thấy mã sản phẩm phù hợp trong danh mục. Anh/chị cho bên mình xin thêm tên cụ thể hoặc nhu cầu sử dụng để bên mình hỗ trợ chi tiết nhé!
- Violations: none

### CFC-FAQ-042 — Trộn NPK với phân hữu cơ

- Question: `Trộn NPK chung với phân hữu cơ rải một lượt luôn cho đỡ tốn công được không?`
- Intent: `PRODUCT_INQUIRY`
- Expected: Dạ bạn **HOÀN TOÀN CÓ THỂ** trộn NPK Cò Bay chung với Hữu cơ Cobanic để rải cùng một lần giúp tiết kiệm công lao động! Lợi ích: Chất hữu cơ sẽ bao bọc các hạt NPK, giảm thất thoát do bốc hơi và giữ phân tan từ từ quanh vùng rễ. **Nguyên tắc quan trọng:** - Trộn xong nên mang đi rải ngay trong ngày,…
- Actual: Dạ hiện tại Cò Bay chưa tìm thấy mã sản phẩm phù hợp trong danh mục. Anh/chị cho bên mình xin thêm tên cụ thể hoặc nhu cầu sử dụng để bên mình hỗ trợ chi tiết nhé!
- Violations: none

### CFC-FAQ-043 — Phân tưới nhỏ giọt (Fertigation)

- Question: `Phân Cò Bay có hòa tan 100% để tưới qua hệ thống nhỏ giọt mà không nghẹt béc không?`
- Intent: `PRODUCT_INQUIRY`
- Expected: Dạ Cò Bay có các dòng sản phẩm NPK Tháp Cao hòa tan nhanh và dòng phân bón tưới nhỏ giọt chuyên dụng (Fertigation)! Đặc điểm: Độ tinh khiết cực cao, tan 100% trong nước, không chứa tạp chất không tan hoặc cặn bã, giúp nước phân lưu thông mượt mà qua hệ thống dây nhỏ giọt và đầu béc bù áp mà không s…
- Actual: Dạ hiện tại Cò Bay chưa tìm thấy mã sản phẩm phù hợp trong danh mục. Anh/chị cho bên mình xin thêm tên cụ thể hoặc nhu cầu sử dụng để bên mình hỗ trợ chi tiết nhé!
- Violations: none

### CFC-FAQ-044 — Hữu cơ trước, hóa học sau

- Question: `Hữu cơ đi trước Hóa học theo sau là sao cách nhau bao nhiêu ngày là chuẩn?`
- Intent: `PRICE_INQUIRY`
- Expected: Dạ 'Hữu cơ đi trước, Hóa học theo sau' là quy tắc vàng trong canh tác nông nghiệp thông minh: 1. **Bón Hữu cơ trước (Ngày 1):** Bón Hữu cơ Cobanic để 'nuôi đất', kích hoạt hệ vi sinh vật và kích thích rễ non bung ra tạo mạng lưới rễ cám dày đặc. 2. **Bón NPK theo sau (Cách 7 - 10 ngày):** Khi rễ tơ…
- Actual: Dạ giá 1 bao phân tùy khu vực và số lượng nên bên em không báo số cụ thể trên chat ạ; bạn kinh doanh sẽ báo giá chính xác. Anh/chị có thể để lại số điện thoại để được liên hệ nha 🌾 ☎️ Trưởng phòng Kinh doanh Lê Trọng Nhơn: 0981 205 448 ☎️ Hotline công ty: 1900 5307
- Violations: none

### CFC-FAQ-045 — Dấu hiệu vi sinh hoạt động trong đất

- Question: `Làm sao biết mấy con vi sinh đang hoạt động dưới gốc có dấu hiệu gì nhìn thấy được không?`
- Intent: `AGRI_ADVICE`
- Expected: Dạ Cò Bay chia sẻ với bạn **5 dấu hiệu nhận biết mắt thường** cho thấy vi sinh vật đang hoạt động cực tốt quanh gốc sau khi bón Hữu cơ Cobanic: 1. **Tơ nấm trắng:** Xuất hiện các mảng tơ nấm trắng mỏng chằng chịt như mạng nhện dưới lớp lá mục/phân hữu cơ (đây là nấm có lợi phân hủy xenlulozo). 2. *…
- Actual: Dạ Cò Bay cần thêm loại cây, giai đoạn cây để tra đúng hướng dẫn đã được duyệt và tư vấn sát vườn mình ạ. ☎️ Khuyến nông Lê Thanh Đạm: 0353 857 516 ☎️ Hotline công ty: 1900 5307
- Violations: none

### CFC-FAQ-046 — Phân chuồng tươi có cần ủ hoai không

- Question: `Phân bò phân gà tươi bón trực tiếp có được không hay bắt buộc phải ủ hoai?`
- Intent: `PRODUCT_INQUIRY`
- Expected: Dạ bạn **TUYỆT ĐỐI KHÔNG NÊN** bón phân chuồng tươi (phân bò, phân gà tươi) trực tiếp vào gốc cây! Tác hại nghiêm trọng của phân tươi: 1. Sinh nhiệt độ cao (quá trình tự ủ dưới gốc) làm **cháy rễ non**. 2. Mang theo mầm bệnh tuyến trùng, nấm Phytophthora gây vàng lá thối rễ và hạt cỏ dại. 3. Tạo mô…
- Actual: Dạ hiện tại Cò Bay chưa tìm thấy mã sản phẩm phù hợp trong danh mục. Anh/chị cho bên mình xin thêm tên cụ thể hoặc nhu cầu sử dụng để bên mình hỗ trợ chi tiết nhé!
- Violations: none

### CFC-FAQ-047 — Vi sinh và thuốc trị nấm hóa học

- Question: `Vừa bón vi sinh xong mà đổ thuốc nấm hóa học xuống thì có phí tiền không?`
- Intent: `PRICE_INQUIRY`
- Expected: Dạ nếu vừa bón phân vi sinh xong mà tưới ngay thuốc trừ nấm hóa học (như Mancozeb, Ridomil, Hexaconazole...) thì thuốc sẽ **tiêu diệt toàn bộ vi sinh vật có lợi**, làm lãng phí 100% tiền mua phân vi sinh! **Quy tắc chuẩn:** - Nếu cây đang bị bệnh rễ nặng: Xử lý thuốc nấm hóa học trước để chặn đứng …
- Actual: Dạ giá 1 bao phân tùy khu vực và số lượng nên bên em không báo số cụ thể trên chat ạ; bạn kinh doanh sẽ báo giá chính xác. Anh/chị có thể để lại số điện thoại để được liên hệ nha 🌾 ☎️ Trưởng phòng Kinh doanh Lê Trọng Nhơn: 0981 205 448 ☎️ Hotline công ty: 1900 5307
- Violations: none
