"""Data-driven and model-driven Response Composer for CFC and ZEO.

Synthesizes natural, polite, warm Vietnamese agricultural responses guided by
retrieved product facts and ad context, without hardcoding product or crop names.
Enforces zero-price-hallucination invariant (INV-1).
"""

from __future__ import annotations

import re
from typing import Any, Protocol

from src.chatbot.shared.enums import PageCode


class ResponseGenerator(Protocol):
    def generate(self, context_payload: dict[str, Any]) -> str | None: ...


class ResponseComposer:
    def __init__(self, generator: ResponseGenerator | None = None) -> None:
        self.generator = generator

    @staticmethod
    def validate_no_price(text: str) -> str:
        """Enforce zero-price-hallucination invariant (INV-1).

        Ensures no currency amount or price quotes slip into outbound messages.
        Avoids false positives on quantity phrases like 'giá 1 bao'.
        """
        price_patterns = [
            r"\b\d+[\s.]*(?:nghìn|ngàn|triệu|k|đ|vnd|đồng)\b",
            r"\b(?:giá|khoảng)\s*[:=]?\s*\d+(?:[.,]\d+)?\s*(?:nghìn|ngàn|triệu|k|đ|vnd|đồng)\b",
            r"\b(?:giá|khoảng)\s*[:=]?\s*\d{4,}\b",
        ]
        for pattern in price_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return (
                    "Dạ giá sản phẩm tùy thuộc vào khu vực và số lượng lấy nên bên em không báo số cụ thể trên chat được ạ. "
                    "Bạn kinh doanh khu vực sẽ liên hệ báo giá chính xác và tốt nhất cho mình nha anh/chị 🌾"
                )
        return text

    def compose_price_response(
        self,
        page_id: PageCode,
        slots: dict[str, Any] | None = None,
        deadline_text: str = "sớm nhất",
        ad_title: str | None = None,
        customer_text: str = "",
    ) -> str:
        slots = slots or {}
        phone = slots.get("phone")

        # Try model generation first if available
        if self.generator:
            price_slots = {
                k: v for k, v in slots.items()
                if k in {"product", "crop", "quantity", "unit", "location", "province", "district", "area", "phone"}
                and v is not None
            }
            payload = {
                "page_id": page_id.value,
                "y_dinh": "PRICE_INQUIRY",
                "tin_nhan_khach": customer_text,
                "thong_tin_khach_hien_tai": price_slots,
                "bai_quang_cao": ad_title or "",
                "moc_hen_lien_he": deadline_text,
            }
            llm_reply = self.generator.generate(payload)
            if llm_reply:
                return self.validate_no_price(llm_reply)

        # Dynamic parameter-driven template fallback
        if phone:
            resp = (
                f"Dạ em đã ghi nhận thông tin của mình ạ! Em hẹn bạn kinh doanh khu vực sẽ liên hệ trực tiếp qua số {phone} "
                f"{deadline_text} để báo giá chi tiết và hỗ trợ ưu đãi tốt nhất cho mình nha anh/chị 🌾"
            )
            return self.validate_no_price(resp)

        crop_part = f" cho vườn {slots.get('crop')}" if slots.get("crop") else ""
        resp = (
            "Dạ giá 1 bao phân tùy khu vực và số lượng mình lấy nên em không báo số cụ thể được ạ, "
            "bạn kinh doanh sẽ báo giá chính xác cho mình.\n"
            f"Anh/chị cho em xin số điện thoại, mình ở huyện/tỉnh nào và đang trồng cây gì{crop_part} "
            f"hay cần loại phân nào, tầm mấy bao để em hẹn bạn kinh doanh gọi báo giá {deadline_text} nha 🌾"
        )
        return self.validate_no_price(resp)

    @staticmethod
    def _brand_name(page_id: PageCode) -> str:
        if page_id == PageCode.ZEO:
            return "ZeO"
        return "Cò Bay"

    def compose_product_response(
        self,
        page_id: PageCode,
        product_record: Any | None = None,
        slots: dict[str, Any] | None = None,
        ad_title: str | None = None,
        deadline_text: str = "sớm nhất",
        customer_text: str = "",
    ) -> str:
        slots = slots or {}
        brand = self._brand_name(page_id)
        product_title = getattr(product_record, "title", "") if product_record else ""
        product_content = getattr(product_record, "content", "") if product_record else ""

        # Try model generation first if available
        if self.generator and product_record:
            product_slots = {
                k: v for k, v in slots.items()
                if k in {"product", "crop", "location", "province", "district", "area", "phone"}
                and v is not None
            }
            payload = {
                "page_id": page_id.value,
                "y_dinh": "PRODUCT_INQUIRY",
                "tin_nhan_khach": customer_text,
                "thong_tin_san_pham": f"{product_title} | {product_content}",
                "thong_tin_khach_hien_tai": product_slots,
                "bai_quang_cao": ad_title or "",
                "moc_hen_lien_he": deadline_text,
            }
            llm_reply = self.generator.generate(payload)
            if llm_reply:
                return self.validate_no_price(llm_reply)

        # Dynamic parameter-driven template fallback
        if product_record:
            resp = (
                f"Dạ {brand} có sản phẩm này ạ:\n"
                f"🌱 {product_title}\n"
                f"Để em báo điểm bán gần nhất cho mình, anh/chị cho em xin mình ở tỉnh/huyện nào và số điện thoại "
                f"để em chuyển bạn kinh doanh hỗ trợ {deadline_text} nha!"
            )
            return self.validate_no_price(resp)

        resp = (
            f"Dạ hiện tại {brand} chưa tìm thấy mã sản phẩm phù hợp trong danh mục. "
            "Anh/chị cho bên mình xin thêm tên cụ thể hoặc nhu cầu sử dụng để bên mình hỗ trợ chi tiết nhé!"
        )
        return self.validate_no_price(resp)

    def compose_dealer_response(
        self,
        page_id: PageCode,
        dealers: list[Any] | None = None,
        slots: dict[str, Any] | None = None,
        deadline_text: str = "sớm nhất",
        customer_text: str = "",
    ) -> str:
        slots = slots or {}
        brand = self._brand_name(page_id)
        if dealers:
            dealer = dealers[0]
            title = getattr(dealer, "title", "").strip()
            content = getattr(dealer, "content", "").strip()
            address = ""
            if " — " in content:
                parts = content.split(" — ", 1)
                address = parts[1].strip()
            elif content and content != title:
                address = content.strip()

            map_url = None
            if address and address.lower() not in {"chưa cập nhật địa chỉ", "chưa cập nhật", "null", "none"}:
                import urllib.parse
                map_query = f"{title}, {address}".strip()
                map_url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote_plus(map_query)}"

            if self.generator:
                payload = {
                    "page_id": page_id.value,
                    "y_dinh": "DEALER_LOOKUP",
                    "tin_nhan_khach": customer_text,
                    "thong_tin_dai_ly": f"{title} (Địa chỉ: {address})" if address else title,
                    "link_ban_do": map_url or "chưa có",
                    "so_dien_thoai_khach": str(slots.get("phone") or ""),
                    "khu_vuc_khach": str(slots.get("location") or slots.get("area") or slots.get("province") or ""),
                    "moc_hen_lien_he": deadline_text,
                }
                llm_reply = self.generator.generate(payload)
                if llm_reply:
                    if map_url and map_url not in llm_reply:
                        llm_reply += f"\n📍 Xem vị trí trên Google Maps: {map_url}"
                    return self.validate_no_price(llm_reply)

            resp_lines = [
                f"Dạ, mình tìm thấy điểm phân phối {brand} tại khu vực của mình:",
                f"🌾 {title}",
            ]
            if address and address.lower() not in {"chưa cập nhật địa chỉ", "chưa cập nhật", "null", "none"}:
                resp_lines.append(f"🏠 Địa chỉ: {address}")
            if map_url:
                resp_lines.append(f"📍 Xem vị trí trên Google Maps: {map_url}")
            resp_lines.append("Anh/chị có thể ghé qua hoặc để lại số điện thoại để bạn phụ trách khu vực hỗ trợ kết nối trực tiếp nha!")
            return self.validate_no_price("\n".join(resp_lines))

        location = slots.get("location") or slots.get("province") or slots.get("district")
        product_needed = str(slots.get("product_mentions") or slots.get("product") or "")
        if self.generator:
            payload = {
                "page_id": page_id.value,
                "y_dinh": "DEALER_LOOKUP",
                "tin_nhan_khach": customer_text,
                "thong_tin_dai_ly": f"Chưa tìm thấy đại lý tại {location}" if location else "Khách chưa cung cấp khu vực/tỉnh/huyện để tra cứu",
                "link_ban_do": "chưa có",
                "so_dien_thoai_khach": str(slots.get("phone") or ""),
                "khu_vuc_khach": str(location or ""),
                "san_pham_quan_tam": product_needed,
                "moc_hen_lien_he": deadline_text,
            }
            llm_reply = self.generator.generate(payload)
            if llm_reply:
                return self.validate_no_price(llm_reply)

        if location:
            resp = (
                f"Dạ hiện tại bên em đang cập nhật dữ liệu đại lý tại khu vực {location}. "
                f"Anh/chị cho em xin số điện thoại để bạn kinh doanh khu vực liên hệ chỉ điểm giao hàng thuận tiện nhất {deadline_text} cho mình nha!"
            )
            return self.validate_no_price(resp)

        resp = (
            "Để em báo điểm bán gần nhất cho mình, anh/chị cho em xin mình ở tỉnh/huyện nào và số điện thoại "
            f"để em chuyển bạn kinh doanh hỗ trợ {deadline_text} ạ?"
        )
        return self.validate_no_price(resp)

    def compose_human_handoff_response(self, page_id: PageCode) -> str:
        return (
            "Dạ em đã chuyển tin nhắn của anh/chị đến nhân viên phụ trách fanpage rồi ạ. "
            "Bạn sẽ vào hỗ trợ mình ngay nhé! Cảm ơn anh/chị đã kiên nhẫn ạ 😊"
        )

    def compose_career_response(self) -> str:
        return (
            "Dạ về thông tin tuyển dụng, vị trí việc làm và nộp hồ sơ, anh/chị vui lòng xem và nhắn trực tiếp qua "
            "trang CFC Career tại https://www.facebook.com/cfccareer để bộ phận nhân sự hỗ trợ nhanh nhất nha!"
        )

    def compose_homecare_response(self) -> str:
        return (
            "Dạ các sản phẩm tiêu dùng gia đình (nước giặt, nước rửa chén ZeO, Oplus, Pano) là dòng sản phẩm gia dụng của công ty ạ. "
            "Anh/chị vui lòng nhắn qua fanpage ZeO Việt Nam để được tư vấn chu đáo nhất nha!"
        )

    def compose_greeting_response(self, page_id: PageCode, ad_title: str | None = None) -> str:
        if page_id == PageCode.ZEO:
            return "Dạ ZeO Homecare kính chào quý khách! ZeO có thể hỗ trợ gì cho mình hôm nay ạ?"

        return (
            "🌱 Phân bón Cò Bay kính chào bà con! "
            "Bà con cần tư vấn cách sử dụng hoặc tìm đại lý mua sản phẩm, Cò Bay rất sẵn lòng hỗ trợ ạ!"
        )

    def compose_order_response(
        self,
        page_id: PageCode,
        orders: list[dict[str, Any]] | None = None,
        order: dict[str, Any] | None = None,
        phone: str | None = None,
        order_code: str | None = None,
        deadline_text: str = "sớm nhất",
        customer_text: str = "",
    ) -> str:
        found_order = order or (orders[0] if orders else None)
        brand = self._brand_name(page_id)

        if self.generator and (found_order or orders):
            order_info = ""
            if found_order:
                order_info = f"Mã đơn: {found_order.get('order_code')}, Ngày đặt: {found_order.get('order_date')}, Trạng thái: {found_order.get('status')}"
            elif orders:
                order_info = "; ".join(f"Mã {o.get('order_code')}: {o.get('status')} (ngày {o.get('order_date')})" for o in orders[:3])
            payload = {
                "page_id": page_id.value,
                "y_dinh": "ORDER_TRACKING",
                "tin_nhan_khach": customer_text,
                "thong_tin_don_hang": order_info,
                "so_dien_thoai": phone or "",
                "ma_don_hang": order_code or "",
                "moc_hen_lien_he": deadline_text,
            }
            llm_reply = self.generator.generate(payload)
            if llm_reply:
                return self.validate_no_price(llm_reply)

        if found_order:
            code = found_order.get("order_code") or "N/A"
            status = found_order.get("status") or "Đang xử lý giao vận"
            date = found_order.get("order_date") or "gần đây"
            resp = (
                f"Dạ {brand} kiểm tra thấy đơn hàng của anh/chị ạ:\n"
                f"📦 Mã đơn: {code}\n"
                f"🗓️ Ngày đặt: {date}\n"
                f"🚚 Trạng thái: {status}\n"
                f"Nếu anh/chị cần hỗ trợ giao gấp hoặc hẹn lại thời gian nhận hàng, bên em sẽ liên hệ lại hỗ trợ {deadline_text} cho mình nha 🌾"
            )
            return self.validate_no_price(resp)

        if orders:
            lines = [f"• Mã {o.get('order_code')}: {o.get('status')} (ngày {o.get('order_date')})" for o in orders[:3]]
            resp = (
                f"Dạ {brand} tìm thấy các đơn hàng gắn với số điện thoại của mình:\n"
                + "\n".join(lines) + "\n"
                f"Anh/chị cần kiểm tra chi tiết đơn nào nhắn em nhé!"
            )
            return self.validate_no_price(resp)

        lookup_key = order_code or phone
        if lookup_key:
            resp = (
                f"Dạ {brand} kiểm tra trên hệ thống chưa thấy đơn hàng nào khớp với thông tin {lookup_key}. "
                f"Anh/chị kiểm tra lại xem có đặt bằng số điện thoại khác không, hoặc để lại lời nhắn để bạn phụ trách đơn hàng kiểm tra lại {deadline_text} cho mình nha!"
            )
            return self.validate_no_price(resp)

        resp = (
            "Dạ để em kiểm tra hành trình và tình trạng đơn hàng cho mình, "
            f"anh/chị cho em xin Số điện thoại đặt hàng hoặc Mã đơn hàng nhé ạ 🌾"
        )
        return self.validate_no_price(resp)

    def compose_image_inquiry_response(
        self,
        page_id: PageCode,
        slots: dict[str, Any] | None = None,
        deadline_text: str = "sớm nhất",
        customer_text: str = "",
    ) -> str:
        slots = slots or {}
        brand = self._brand_name(page_id)

        # Try model generation first if available
        if self.generator:
            payload = {
                "page_id": page_id.value,
                "y_dinh": "IMAGE_INQUIRY",
                "tin_nhan_khach": customer_text,
                "thong_tin_khach_hien_tai": slots,
                "moc_hen_lien_he": deadline_text,
            }
            llm_reply = self.generator.generate(payload)
            if llm_reply:
                return self.validate_no_price(llm_reply)

        crop = slots.get("crop")
        crop_part = f" đối với cây {crop}" if crop else ""
        if page_id == PageCode.ZEO:
            resp = (
                f"Dạ {brand} đã nhận được hình ảnh của anh/chị ạ 📸.\n"
                f"Để chuyên viên tư vấn hỗ trợ đúng nhu cầu cho mình, "
                f"anh/chị cho em xin thêm thông tin và số điện thoại để bên em liên hệ hỗ trợ {deadline_text} nha ✨"
            )
        else:
            resp = (
                f"Dạ {brand} đã nhận được hình ảnh của anh/chị ạ 📸.\n"
                f"Để kỹ sư nông nghiệp chẩn đoán chính xác tình trạng{crop_part} và tư vấn giải pháp/sản phẩm phù hợp nhất, "
                f"anh/chị cho em xin thêm thông tin: vườn mình ở tỉnh/huyện nào và số điện thoại để chuyên viên kỹ thuật gọi hỗ trợ xem vườn {deadline_text} nha 🌾"
            )
        return self.validate_no_price(resp)
