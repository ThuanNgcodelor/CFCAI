"""Data-driven and model-driven Response Composer for CFC and ZEO.

Synthesizes natural, polite, warm Vietnamese agricultural responses guided by
retrieved product facts and ad context, without hardcoding product or crop names.
Enforces zero-price-hallucination invariant (INV-1).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Protocol

from src.chatbot.modules.workflows.policy_validator import OutputPolicyValidator
from src.chatbot.modules.workflows.support_contacts import SupportContactDirectory
from src.chatbot.shared.enums import PageCode, WorkflowType


class ResponseGenerator(Protocol):
    def generate(self, context_payload: dict[str, Any]) -> str | None: ...


class ResponseComposer:
    _DEADLINE_TOKENS = frozenset(
        {
            "moc_hen_lien_he",
            "thoi_gian",
            "deadline",
            "deadline_text",
            "contact_deadline",
        }
    )
    _PLACEHOLDER_PATTERN = re.compile(
        r"""
        (?:
            \{\{\s*(?P<double_curly>[A-Za-z][A-Za-z0-9_\\.-]*)\s*\}\}
            |\$\{\s*(?P<dollar_curly>[A-Za-z][A-Za-z0-9_\\.-]*)\s*\}
            |\{\s*(?P<curly>[A-Za-z][A-Za-z0-9_\\.-]*)\s*\}
            |\[\s*(?P<square>[A-Za-z][A-Za-z0-9_\\.-]*)\s*\]
        )
        """,
        re.VERBOSE,
    )
    _PHONE_PATTERN = re.compile(
        r"(?<!\d)(?:(?:\+?84|0)(?:[\s.\-]?\d){9,10}|1900[\s.\-]?\d{4})(?!\d)"
    )
    _PHONE_CONFIRMATION_PATTERNS = (
        re.compile(
            r"\b(?:em|ben em|he thong)\s+(?:da|se|vua)\s+"
            r"(?:ghi nhan|luu|de lai|xac nhan|nhan duoc)\b.{0,80}"
            r"\b(?:so dien thoai|sdt)\b"
        ),
        re.compile(
            r"\b(?:da|vua)\s+(?:ghi nhan|luu|xac nhan|nhan duoc)\b.{0,80}"
            r"\b(?:so dien thoai|sdt)\b"
        ),
        re.compile(
            r"\b(?:nhan vien|ban kinh doanh|chuyen vien|ben em)\b.{0,60}"
            r"\b(?:se|da)\s+(?:goi|lien he)\b.{0,40}"
            r"\b(?:qua|theo)\s+(?:so|sdt)\b"
        ),
        re.compile(
            r"\bso dien thoai cua (?:anh|chi|anh chi|minh)\b.{0,30}\b(?:da|se)\b"
        ),
    )

    def __init__(
        self,
        generator: ResponseGenerator | None = None,
        contact_directory: SupportContactDirectory | None = None,
    ) -> None:
        self.generator = generator
        self.contact_directory = contact_directory

    @classmethod
    def _placeholder_token(cls, match: re.Match[str]) -> str:
        token = next(value for value in match.groupdict().values() if value is not None)
        return token.replace("\\_", "_").casefold()

    @classmethod
    def has_unresolved_placeholders(cls, text: str) -> bool:
        normalized = text.replace("\\_", "_")
        return any(
            cls._placeholder_token(match) not in cls._DEADLINE_TOKENS
            for match in cls._PLACEHOLDER_PATTERN.finditer(normalized)
        )

    @classmethod
    def sanitize_placeholders(cls, text: str, deadline_text: str = "sớm nhất") -> str:
        """Remove model template markers before a reply reaches the outbox."""
        normalized = text.replace("\\_", "_")

        def replace_marker(match: re.Match[str]) -> str:
            token = cls._placeholder_token(match)
            return deadline_text if token in cls._DEADLINE_TOKENS else ""

        sanitized = cls._PLACEHOLDER_PATTERN.sub(replace_marker, normalized)
        sanitized = re.sub(
            r"\b(?:moc_hen_lien_he|thoi_gian|deadline(?:_text)?|contact_deadline)\b",
            deadline_text,
            sanitized,
            flags=re.IGNORECASE,
        )
        sanitized = re.sub(r"\(\s*\)", "", sanitized)
        sanitized = re.sub(r"[ \t]{2,}", " ", sanitized)
        sanitized = re.sub(r"[ \t]*\n[ \t]*", "\n", sanitized)
        return re.sub(r"\s+([,.;!?])", r"\1", sanitized).strip()

    @staticmethod
    def _fold_validation_text(text: str) -> str:
        folded = unicodedata.normalize("NFD", text.casefold())
        folded = "".join(
            character
            for character in folded
            if unicodedata.category(character) != "Mn"
        )
        return folded.replace("đ", "d")

    @classmethod
    def _claims_customer_phone(cls, text: str) -> bool:
        folded = cls._fold_validation_text(text)
        return any(pattern.search(folded) for pattern in cls._PHONE_CONFIRMATION_PATTERNS)

    @classmethod
    def _contains_unapproved_phone(
        cls,
        text: str,
        slots: dict[str, Any],
    ) -> bool:
        approved = {
            re.sub(r"\D", "", str(slots.get("phone") or "")),
        }
        approved.discard("")
        for match in cls._PHONE_PATTERN.finditer(text):
            digits = re.sub(r"\D", "", match.group(0))
            if digits.startswith("84"):
                digits = "0" + digits[2:]
            if digits not in approved:
                return True
        return False

    @classmethod
    def validate_generated_reply(
        cls,
        text: str,
        *,
        slots: dict[str, Any],
        fallback: str,
        deadline_text: str,
        page_id: PageCode = PageCode.CFC,
        workflow: WorkflowType = WorkflowType.FAQ_ANSWER,
        allowed_phones: set[str] | None = None,
    ) -> str:
        """Accept model prose only when it is grounded in the supplied slots and passes policy."""
        result = OutputPolicyValidator.validate(
            text,
            page_id=page_id,
            workflow=workflow,
            slots=slots,
            allowed_phones=allowed_phones,
            deadline_text=deadline_text,
            fallback=fallback,
        )
        return result.text

    def _append_support_contact(
        self,
        response: str,
        *,
        page_id: PageCode,
        workflow: WorkflowType,
        customer_key: str,
        customer_text: str,
    ) -> str:
        if self.contact_directory is None:
            return response
        selection = self.contact_directory.select(
            page_id,
            workflow,
            customer_key=customer_key,
            customer_text=customer_text,
        )
        if selection is None:
            return response
        contact_block = self.contact_directory.render(selection)
        if not contact_block:
            return response
        return f"{response.rstrip()}\n{contact_block}"

    @classmethod
    def validate_no_price(cls, text: str, deadline_text: str = "sớm nhất") -> str:
        """Enforce zero-price-hallucination invariant (INV-1).

        Ensures no currency amount or price quotes slip into outbound messages.
        Avoids false positives on quantity phrases like 'giá 1 bao'.
        """
        text = cls.sanitize_placeholders(text, deadline_text)
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
        customer_key: str = "",
    ) -> str:
        slots = slots or {}
        phone = slots.get("phone")

        if phone:
            fallback = (
                f"Dạ em đã ghi nhận số điện thoại {phone} của mình ạ. "
                f"Bạn kinh doanh sẽ liên hệ {deadline_text} để báo giá chi tiết và tư vấn; "
                "anh/chị chưa đặt hàng ở bước này nha 🌾"
            )
        else:
            fallback = (
                "Dạ giá 1 bao phân tùy khu vực và số lượng nên bên em không báo số cụ thể trên chat ạ; "
                "bạn kinh doanh sẽ báo giá chính xác. Anh/chị có thể để lại số điện thoại để được liên hệ nha 🌾"
            )

        response = fallback

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
                response = self.validate_generated_reply(
                    llm_reply,
                    slots=price_slots,
                    fallback=fallback,
                    deadline_text=deadline_text,
                )

        response = self._append_support_contact(
            response,
            page_id=page_id,
            workflow=WorkflowType.PRICE_HANDOFF,
            customer_key=customer_key,
            customer_text=customer_text,
        )
        return self.validate_no_price(response, deadline_text)

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

        if product_record:
            fallback = (
                f"Dạ {brand} có sản phẩm này ạ:\n"
                f"🌱 {product_title}\n"
                f"Anh/chị cho em xin tỉnh/huyện nhận hàng để em kiểm tra điểm bán phù hợp {deadline_text} nha! "
                "Sau khi chốt khu vực, mình có thể để lại số điện thoại nếu cần nhân viên liên hệ."
            )
        else:
            fallback = (
                f"Dạ hiện tại {brand} chưa tìm thấy mã sản phẩm phù hợp trong danh mục. "
                "Anh/chị cho bên mình xin thêm tên cụ thể hoặc nhu cầu sử dụng để bên mình hỗ trợ chi tiết nhé!"
            )

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
                return self.validate_generated_reply(
                    llm_reply,
                    slots=product_slots,
                    fallback=fallback,
                    deadline_text=deadline_text,
                )

        return self.validate_no_price(fallback, deadline_text)

    def compose_agriculture_response(
        self,
        page_id: PageCode,
        advice_record: Any | None = None,
        slots: dict[str, Any] | None = None,
        deadline_text: str = "sớm nhất",
        customer_text: str = "",
        customer_key: str = "",
    ) -> str:
        """Compose only from an approved agriculture record and explicit slots."""
        slots = slots or {}
        brand = self._brand_name(page_id)
        crop = str(slots.get("crop") or "").strip()
        stage = str(slots.get("stage") or "").strip()
        problem = str(slots.get("problem") or "").strip()
        has_context = bool(crop and (stage or problem))

        missing = []
        if not crop:
            missing.append("loại cây")
        if not stage:
            missing.append("giai đoạn cây")
        if not problem:
            missing.append("tình trạng hoặc mục tiêu cần xử lý")
        requested = ", ".join(missing[:2]) if missing else "thông tin hiện trạng"
        fallback = (
            f"Dạ {brand} cần thêm {requested} để tra đúng hướng dẫn đã được duyệt "
            "và tư vấn sát vườn mình ạ."
        )
        if has_context and advice_record:
            approved_content = str(
                getattr(advice_record, "content", "") or ""
            ).strip()
            if approved_content:
                fallback = approved_content

        response = fallback

        if has_context and self.generator and advice_record:
            advice_slots = {
                key: value
                for key, value in slots.items()
                if key
                in {
                    "crop",
                    "stage",
                    "problem",
                    "product",
                    "location",
                    "province",
                    "district",
                    "phone",
                }
                and value not in (None, "")
            }
            payload = {
                "page_id": page_id.value,
                "y_dinh": "AGRI_ADVICE",
                "tin_nhan_khach": customer_text,
                "thong_tin_tu_van_da_duyet": {
                    "tieu_de": getattr(advice_record, "title", ""),
                    "noi_dung": getattr(advice_record, "content", ""),
                    "intent": getattr(advice_record, "intent", ""),
                    "category": getattr(advice_record, "category", ""),
                    "risk_level": getattr(advice_record, "risk_level", ""),
                },
                "thong_tin_khach_hien_tai": advice_slots,
                "moc_hen_lien_he": deadline_text,
            }
            llm_reply = self.generator.generate(payload)
            if llm_reply:
                response = self.validate_generated_reply(
                    llm_reply,
                    slots=advice_slots,
                    fallback=fallback,
                    deadline_text=deadline_text,
                )

        response = self._append_support_contact(
            response,
            page_id=page_id,
            workflow=WorkflowType.AGRICULTURE_ADVICE,
            customer_key=customer_key,
            customer_text=customer_text,
        )
        return self.validate_no_price(response, deadline_text)

    def compose_dealer_response(
        self,
        page_id: PageCode,
        dealers: list[Any] | None = None,
        slots: dict[str, Any] | None = None,
        deadline_text: str = "sớm nhất",
        customer_text: str = "",
        lookup_result: Any | None = None,
        previously_no_confirmed_match: bool = False,
    ) -> str:
        """Present only CRM-backed dealer addresses; never manufacture a map link.

        Dealer discovery is intentionally deterministic.  A text generator
        could turn a province-level hit into an unsupported "nearest" claim,
        so it is not used in this narrow, location-sensitive workflow.
        """
        slots = slots or {}
        brand = self._brand_name(page_id)
        location = (
            getattr(lookup_result, "area_label", None)
            or slots.get("location")
            or slots.get("district")
            or slots.get("ward")
            or slots.get("province")
        )
        scope = getattr(lookup_result, "match_scope", None)
        status = getattr(lookup_result, "status", None) or slots.get("dealer_search_status")
        visible_dealers: list[tuple[str, str]] = []
        for dealer in (dealers or [])[:3]:
            title = str(getattr(dealer, "title", "") or "").strip()
            content = str(getattr(dealer, "content", "") or "").strip()
            address = ""
            if " — " in content:
                _, address = content.split(" — ", 1)
                address = address.strip()
            elif content and content != title:
                address = content
            if title and address and address.casefold() not in {
                "chưa cập nhật địa chỉ",
                "chưa cập nhật",
                "null",
                "none",
            }:
                visible_dealers.append((title, address))

        if visible_dealers:
            if scope == "GPS_DISTANCE":
                heading = (
                    f"Dạ, đây là các điểm bán {brand} có địa chỉ đã ghi nhận gần {location}:"
                    if location
                    else f"Dạ, đây là các điểm bán {brand} có địa chỉ đã ghi nhận gần khu vực mình cung cấp:"
                )
            elif scope == "PROVINCE":
                heading = (
                    f"Dạ, đây là một số điểm bán {brand} có địa chỉ đã ghi nhận tại {location}:"
                    if location
                    else f"Dạ, đây là một số điểm bán {brand} có địa chỉ đã ghi nhận:"
                )
            elif scope == "EXACT_ADMIN_AREA":
                heading = (
                    f"Dạ, mình tìm được các điểm bán {brand} có địa chỉ tại {location}:"
                    if location
                    else f"Dạ, mình tìm được các điểm bán {brand} có địa chỉ phù hợp:"
                )
            else:
                heading = (
                    f"Dạ, mình tìm được các điểm bán {brand} có địa chỉ trùng khu vực {location}:"
                    if location
                    else f"Dạ, mình tìm được các điểm bán {brand} có địa chỉ phù hợp:"
                )
            response_lines = [heading]
            for index, (title, address) in enumerate(visible_dealers, start=1):
                response_lines.extend(
                    [
                        f"{index}. 🌾 {title}",
                        f"   🏠 Địa chỉ: {address}",
                    ]
                )
            response_lines.append(
                "Anh/chị có thể ghé qua hoặc cho em biết thêm nhu cầu để hỗ trợ kết nối phù hợp nha!"
            )
            return self.validate_no_price("\n".join(response_lines), deadline_text)

        if status == "NO_CONFIRMED_MATCH" or location:
            check_text = "Mình đã kiểm tra lại" if previously_no_confirmed_match else "Mình đã kiểm tra"
            area_text = f" khu vực {location}" if location else " khu vực mình cung cấp"
            response = (
                f"Dạ {check_text}{area_text}, nhưng hiện tại hệ thống chưa có điểm bán được xác nhận tại đây "
                "nên em không muốn chỉ nhầm địa chỉ. Anh/chị có thể cho em thêm xã/ấp cụ thể "
                "hoặc nhắn “gặp nhân viên” nếu cần kiểm tra thủ công ạ."
            )
            return self.validate_no_price(response, deadline_text)

        resp = (
            "Để em kiểm tra điểm bán gần nhất, anh/chị cho em xin tỉnh/huyện mình đang ở ạ? "
            "Sau khi có khu vực, mình có thể để lại số điện thoại nếu cần nhân viên hỗ trợ liên hệ."
        )
        return self.validate_no_price(resp, deadline_text)

    def compose_contact_response(
        self,
        page_id: PageCode,
        *,
        customer_key: str,
        customer_text: str = "",
    ) -> str:
        if self.contact_directory is not None:
            selection = self.contact_directory.select(
                page_id,
                WorkflowType.CONTACT_SUPPORT,
                customer_key=customer_key,
                customer_text=customer_text,
            )
            if selection is not None:
                contact_block = self.contact_directory.render(selection)
                if contact_block:
                    return self.validate_no_price(
                        f"Dạ, để {selection.label}, anh/chị có thể liên hệ trực tiếp:\n"
                        f"{contact_block}"
                    )
        return (
            "Dạ anh/chị cho em biết mình cần tư vấn giá, kỹ thuật cây trồng "
            "hay hỗ trợ nội dung nào để em chuyển đúng người phụ trách ạ?"
        )

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
            "🌱 Phân bón Cò Bay kính chào anh/chị ạ! "
            "Anh/chị cần tư vấn cách sử dụng hoặc tìm điểm bán mua sản phẩm, Cò Bay rất sẵn lòng hỗ trợ ạ!"
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

        if found_order:
            code = found_order.get("order_code") or "N/A"
            status = found_order.get("status") or "Đang xử lý giao vận"
            date = found_order.get("order_date") or "gần đây"
            fallback = (
                f"Dạ {brand} kiểm tra thấy đơn hàng của anh/chị ạ:\n"
                f"📦 Mã đơn: {code}\n"
                f"🗓️ Ngày đặt: {date}\n"
                f"🚚 Trạng thái: {status}\n"
                f"Nếu anh/chị cần hỗ trợ giao gấp hoặc hẹn lại thời gian nhận hàng, bên em sẽ liên hệ lại hỗ trợ {deadline_text} cho mình nha 🌾"
            )
        elif orders:
            lines = [
                f"• Mã {item.get('order_code')}: {item.get('status')} "
                f"(ngày {item.get('order_date')})"
                for item in orders[:3]
            ]
            fallback = (
                f"Dạ {brand} tìm thấy các đơn hàng gắn với số điện thoại của mình:\n"
                + "\n".join(lines)
                + "\nAnh/chị cần kiểm tra chi tiết đơn nào nhắn em nhé!"
            )
        else:
            lookup_key = order_code or phone
            if lookup_key:
                fallback = (
                    f"Dạ {brand} kiểm tra trên hệ thống chưa thấy đơn hàng nào khớp với thông tin {lookup_key}. "
                    f"Anh/chị kiểm tra lại xem có đặt bằng số điện thoại khác không, hoặc để lại lời nhắn để bạn phụ trách đơn hàng kiểm tra lại {deadline_text} cho mình nha!"
                )
            else:
                fallback = (
                    "Dạ để em kiểm tra hành trình và tình trạng đơn hàng cho mình, "
                    "anh/chị cho em xin Số điện thoại đặt hàng hoặc Mã đơn hàng nhé ạ 🌾"
                )

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
                return self.validate_generated_reply(
                    llm_reply,
                    slots={"phone": phone, "order_code": order_code},
                    fallback=fallback,
                    deadline_text=deadline_text,
                )

        return self.validate_no_price(fallback, deadline_text)

    def compose_image_inquiry_response(
        self,
        page_id: PageCode,
        slots: dict[str, Any] | None = None,
        deadline_text: str = "sớm nhất",
        customer_text: str = "",
    ) -> str:
        slots = slots or {}
        brand = self._brand_name(page_id)

        crop = slots.get("crop")
        crop_part = f" đối với cây {crop}" if crop else ""
        if page_id == PageCode.ZEO:
            fallback = (
                f"Dạ {brand} đã nhận được hình ảnh của anh/chị ạ 📸.\n"
                "Để chuyên viên tư vấn hỗ trợ đúng nhu cầu cho mình, "
                f"anh/chị cho em xin thêm thông tin và số điện thoại để bên em liên hệ hỗ trợ {deadline_text} nha ✨"
            )
        else:
            fallback = (
                f"Dạ {brand} đã nhận được hình ảnh của anh/chị ạ 📸.\n"
                f"Để kỹ sư nông nghiệp chẩn đoán chính xác tình trạng{crop_part} và tư vấn giải pháp/sản phẩm phù hợp nhất, "
                f"anh/chị cho em xin thêm thông tin: vườn mình ở tỉnh/huyện nào và số điện thoại để chuyên viên kỹ thuật gọi hỗ trợ xem vườn {deadline_text} nha 🌾"
            )

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
                return self.validate_generated_reply(
                    llm_reply,
                    slots=slots,
                    fallback=fallback,
                    deadline_text=deadline_text,
                )

        return self.validate_no_price(fallback, deadline_text)
