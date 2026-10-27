# CFC FAQ Phase F6 evaluation

Generated: `2026-10-27T01:47:07.357904+00:00`
Gate: **PASS**

## Summary

- Source retrieval Top-1: **119/119**
- Source retrieval Top-3: **119/119**
- Held-out Top-1: **28/28**
- Held-out Top-3: **28/28**
- Active runtime: **26/26**
- Runtime variants executed: **119**
- Failure taxonomy: `{'ROUTING': 32, 'WORKFLOW': 34}`
- Production: `{'status': 'CHECKED', 'active_approved_records': 8, 'import_batches': 1}`
- Gate failures: `[]`

Inactive rows are executed for audit but stay `NOT_GATED` until signed off.

## Active runtime cases

| Case | Q | Expected | Actual | Verdict | Failure | Reply |
|---|---:|---|---|---|---|---|
| CFC-FAQ-005 | 1 | SALES_LEAD | SALES_LEAD | PASS | — | Dạ anh/chị cho em xin tỉnh/huyện muốn kinh doanh và số điện thoại liên hệ để bên em chuyển đúng nhân viên phụ trách khu vực ạ. |
| CFC-FAQ-005 | 2 | SALES_LEAD | SALES_LEAD | PASS | — | Dạ anh/chị cho em xin tỉnh/huyện muốn kinh doanh và số điện thoại liên hệ để bên em chuyển đúng nhân viên phụ trách khu vực ạ. |
| CFC-FAQ-006 | 1 | HUMAN_REQUEST | HUMAN_REQUEST | PASS | — | Dạ em đã tạo yêu cầu hỗ trợ cho nhân viên phụ trách fanpage rồi ạ. Anh/chị vui lòng chờ yêu cầu được tiếp nhận nhé! |
| CFC-FAQ-011 | 1 | PRICE_INQUIRY | PRICE_INQUIRY | PASS | — | Dạ giá sản phẩm tùy khu vực và số lượng nên bên em không báo số cụ thể trên chat ạ. Em đã tạo yêu cầu báo giá cho bộ phận kinh doanh; anh/chị có thể để lại số … |
| CFC-FAQ-011 | 2 | PRICE_INQUIRY | PRICE_INQUIRY | PASS | — | Dạ giá sản phẩm tùy khu vực và số lượng nên bên em không báo số cụ thể trên chat ạ. Em đã tạo yêu cầu báo giá cho bộ phận kinh doanh; anh/chị có thể để lại số … |
| CFC-FAQ-011 | 3 | PRICE_INQUIRY | PRICE_INQUIRY | PASS | — | Dạ giá sản phẩm tùy khu vực và số lượng nên bên em không báo số cụ thể trên chat ạ. Em đã tạo yêu cầu báo giá cho bộ phận kinh doanh; anh/chị có thể để lại số … |
| CFC-FAQ-011 | 4 | PRICE_INQUIRY | PRICE_INQUIRY | PASS | — | Dạ giá sản phẩm tùy khu vực và số lượng nên bên em không báo số cụ thể trên chat ạ. Em đã tạo yêu cầu báo giá cho bộ phận kinh doanh; anh/chị có thể để lại số … |
| CFC-FAQ-011 | 5 | PRICE_INQUIRY | PRICE_INQUIRY | PASS | — | Dạ giá sản phẩm tùy khu vực và số lượng nên bên em không báo số cụ thể trên chat ạ. Em đã tạo yêu cầu báo giá cho bộ phận kinh doanh; anh/chị có thể để lại số … |
| CFC-FAQ-012 | 1 | DEALER_LOOKUP | DEALER_LOOKUP | PASS | — | Để em kiểm tra điểm bán gần nhất, anh/chị cho em xin tỉnh/huyện mình đang ở ạ? Sau khi có khu vực, mình có thể để lại số điện thoại nếu cần nhân viên hỗ trợ li… |
| CFC-FAQ-012 | 2 | DEALER_LOOKUP | DEALER_LOOKUP | PASS | — | Để em kiểm tra điểm bán gần nhất, anh/chị cho em xin tỉnh/huyện mình đang ở ạ? Sau khi có khu vực, mình có thể để lại số điện thoại nếu cần nhân viên hỗ trợ li… |
| CFC-FAQ-012 | 3 | DEALER_LOOKUP | DEALER_LOOKUP | PASS | — | Để em kiểm tra điểm bán gần nhất, anh/chị cho em xin tỉnh/huyện mình đang ở ạ? Sau khi có khu vực, mình có thể để lại số điện thoại nếu cần nhân viên hỗ trợ li… |
| CFC-FAQ-012 | 4 | DEALER_LOOKUP | DEALER_LOOKUP | PASS | — | Dạ Mình đã kiểm tra khu vực Cần Thơ, nhưng hiện tại hệ thống chưa có điểm bán được xác nhận tại đây nên em không muốn chỉ nhầm địa chỉ. Anh/chị có thể cho em t… |
| CFC-FAQ-013 | 1 | PRODUCT_INQUIRY | PRODUCT_INQUIRY | PASS | — | Dạ hiện tại Cò Bay chưa tìm thấy mã sản phẩm phù hợp trong danh mục. Anh/chị cho bên mình xin thêm tên cụ thể hoặc nhu cầu sử dụng để bên mình hỗ trợ chi tiết … |
| CFC-FAQ-013 | 2 | PRODUCT_INQUIRY | PRODUCT_INQUIRY | PASS | — | Dạ hiện tại Cò Bay chưa tìm thấy mã sản phẩm phù hợp trong danh mục. Anh/chị cho bên mình xin thêm tên cụ thể hoặc nhu cầu sử dụng để bên mình hỗ trợ chi tiết … |
| CFC-FAQ-015 | 1 | AGRI_ADVICE | AGRI_ADVICE | PASS | — | Dạ em chưa đủ dữ liệu đã duyệt để tư vấn chính xác. Anh/chị vui lòng cho em biết loại cây, giai đoạn và tình trạng hiện tại ạ. |
| CFC-FAQ-015 | 2 | AGRI_ADVICE | AGRI_ADVICE | PASS | — | Dạ em chưa đủ dữ liệu đã duyệt để tư vấn chính xác. Anh/chị vui lòng cho em biết loại cây, giai đoạn và tình trạng hiện tại ạ. |
| CFC-FAQ-015 | 3 | AGRI_ADVICE | AGRI_ADVICE | PASS | — | Dạ em chưa đủ dữ liệu đã duyệt để tư vấn chính xác. Anh/chị vui lòng cho em biết loại cây, giai đoạn và tình trạng hiện tại ạ. |
| CFC-FAQ-015 | 4 | AGRI_ADVICE | AGRI_ADVICE | PASS | — | Dạ em chưa đủ dữ liệu đã duyệt để tư vấn chính xác. Anh/chị vui lòng cho em biết loại cây, giai đoạn và tình trạng hiện tại ạ. |
| CFC-FAQ-015 | 5 | AGRI_ADVICE | AGRI_ADVICE | PASS | — | Dạ em chưa đủ dữ liệu đã duyệt để tư vấn chính xác. Anh/chị vui lòng cho em biết loại cây, giai đoạn và tình trạng hiện tại ạ. |
| CFC-FAQ-016 | 1 | AGRI_ADVICE | AGRI_ADVICE | PASS | — | Dạ em chưa đủ dữ liệu đã duyệt để tư vấn chính xác. Anh/chị vui lòng cho em biết loại cây, giai đoạn và tình trạng hiện tại ạ. |
| CFC-FAQ-016 | 2 | AGRI_ADVICE | AGRI_ADVICE | PASS | — | Dạ em chưa đủ dữ liệu đã duyệt để tư vấn chính xác. Anh/chị vui lòng cho em biết loại cây, giai đoạn và tình trạng hiện tại ạ. |
| CFC-FAQ-016 | 3 | AGRI_ADVICE | AGRI_ADVICE | PASS | — | Dạ em chưa đủ dữ liệu đã duyệt để tư vấn chính xác. Anh/chị vui lòng cho em biết loại cây, giai đoạn và tình trạng hiện tại ạ. |
| CFC-FAQ-016 | 4 | AGRI_ADVICE | AGRI_ADVICE | PASS | — | Dạ em chưa đủ dữ liệu đã duyệt để tư vấn chính xác. Anh/chị vui lòng cho em biết loại cây, giai đoạn và tình trạng hiện tại ạ. |
| CFC-FAQ-018 | 1 | CONTACT_REQUEST | CONTACT_REQUEST | PASS | — | Dạ, để hỗ trợ khách hàng, anh/chị có thể liên hệ trực tiếp: ☎️ Trưởng phòng Kinh doanh Lê Trọng Nhơn: 0981 205 448 ☎️ Hotline công ty: 1900 5307 |
| CFC-FAQ-018 | 2 | CONTACT_REQUEST | CONTACT_REQUEST | PASS | — | Dạ, để hỗ trợ khách hàng, anh/chị có thể liên hệ trực tiếp: ☎️ Trưởng phòng Kinh doanh Lê Trọng Nhơn: 0981 205 448 ☎️ Hotline công ty: 1900 5307 |
| CFC-FAQ-018 | 3 | CONTACT_REQUEST | CONTACT_REQUEST | PASS | — | Dạ, để hỗ trợ khách hàng, anh/chị có thể liên hệ trực tiếp: ☎️ Trưởng phòng Kinh doanh Lê Trọng Nhơn: 0981 205 448 ☎️ Hotline công ty: 1900 5307 |

## Retrieval/held-out Top-1 failures

No retrieval failures.
