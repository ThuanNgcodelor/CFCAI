"""Unit tests for OutputPolicyValidator enforcing Phase F5 safety invariants."""

from src.chatbot.modules.workflows.policy_validator import OutputPolicyValidator
from src.chatbot.shared.enums import PageCode, WorkflowType


def test_validator_detects_price_and_returns_safe_fallback() -> None:
    text = "Dạ giá sản phẩm Cobanic là 350.000đ/bao 25kg nha anh/chị!"
    result = OutputPolicyValidator.validate(
        text,
        page_id=PageCode.CFC,
        workflow=WorkflowType.PRICE_HANDOFF,
        slots={"product": "Cobanic 25kg"},
        fallback="Dạ bạn kinh doanh sẽ liên hệ báo giá chi tiết cho mình nha anh/chị 🌾",
    )
    assert not result.is_valid
    assert "PRICE_HALLUCINATION_DETECTED" in result.reasons
    assert "350.000đ" not in result.text
    assert "đồng" not in result.text.lower()
    assert "báo giá" in result.text


def test_validator_detects_internal_jargon() -> None:
    text = "Dạ snapshot CRM hiện chưa cập nhật địa chỉ đại lý này trong database ạ."
    result = OutputPolicyValidator.validate(
        text,
        page_id=PageCode.CFC,
        workflow=WorkflowType.DEALER_LOOKUP,
        fallback="Dạ hiện tại hệ thống chưa có điểm bán tại khu vực này ạ.",
    )
    assert not result.is_valid
    assert any("INTERNAL_JARGON_DETECTED" in r for r in result.reasons)
    assert "snapshot crm" not in result.text.lower()
    assert "database" not in result.text.lower()


def test_validator_detects_unresolved_placeholders() -> None:
    text = "Dạ em gửi thông tin sản phẩm {{product_title}} cho mình ạ."
    result = OutputPolicyValidator.validate(
        text,
        page_id=PageCode.CFC,
        workflow=WorkflowType.PRODUCT_INQUIRY,
        fallback="Dạ em gửi thông tin sản phẩm cho anh/chị ạ.",
    )
    assert not result.is_valid
    assert any("UNRESOLVED_PLACEHOLDER" in r for r in result.reasons)
    assert "{{" not in result.text


def test_validator_sanitizes_deadline_placeholders_cleanly() -> None:
    text = "Nhân viên kinh doanh sẽ liên hệ trước [moc_hen_lien_he] để hỗ trợ anh/chị ạ."
    result = OutputPolicyValidator.validate(
        text,
        page_id=PageCode.CFC,
        workflow=WorkflowType.PRICE_HANDOFF,
        deadline_text="15h chiều nay",
        handoff_created=True,
    )
    assert result.is_valid
    assert "trước 15h chiều nay" in result.text
    assert "[moc_hen_lien_he]" not in result.text


def test_validator_detects_false_phone_confirmation_without_slot() -> None:
    # Customer never provided phone, but LLM claimed to have recorded it
    text = "Dạ em đã ghi nhận số điện thoại của anh/chị để bạn phụ trách gọi lại ạ!"
    result = OutputPolicyValidator.validate(
        text,
        page_id=PageCode.CFC,
        workflow=WorkflowType.PRICE_HANDOFF,
        slots={},  # no phone slot
        fallback="Dạ anh/chị cho em xin số điện thoại để bộ phận kinh doanh báo giá nha!",
    )
    assert not result.is_valid
    assert "FALSE_PHONE_CONFIRMATION_WITHOUT_SLOT" in result.reasons
    assert "anh/chị cho em xin số điện thoại" in result.text


def test_validator_never_returns_an_unsafe_fallback() -> None:
    result = OutputPolicyValidator.validate(
        "Anh/chị gọi 0999888777 để mua với giá 500.000đ ạ.",
        page_id=PageCode.CFC,
        workflow=WorkflowType.PRICE_HANDOFF,
        fallback="Bạn kinh doanh sẽ gọi 0999888777 và báo giá 500.000đ ạ.",
    )

    assert not result.is_valid
    assert "UNSAFE_FALLBACK_REJECTED" in result.reasons
    assert "0999888777" not in result.text
    assert "500.000" not in result.text
    assert "bạn" not in result.text.casefold()


def test_validator_rejects_false_handoff_confirmation() -> None:
    result = OutputPolicyValidator.validate(
        "Dạ em đã chuyển yêu cầu cho nhân viên phụ trách rồi ạ.",
        page_id=PageCode.CFC,
        workflow=WorkflowType.HUMAN_REQUEST,
        handoff_created=False,
    )

    assert not result.is_valid
    assert "FALSE_HANDOFF_CONFIRMATION" in result.reasons
    assert "đã chuyển" not in result.text.casefold()


def test_validator_requires_gps_evidence_for_nearest_claim() -> None:
    result = OutputPolicyValidator.validate(
        "Dạ đây là đại lý gần nhất tại Cần Thơ ạ.",
        page_id=PageCode.CFC,
        workflow=WorkflowType.DEALER_LOOKUP,
        slots={"dealer_match_scope": "EXACT_ADMIN_AREA"},
    )

    assert not result.is_valid
    assert "UNVERIFIED_NEAREST_DEALER_CLAIM" in result.reasons
    assert "gần nhất" not in result.text.casefold()


def test_validator_rejects_ungrounded_product_formula() -> None:
    result = OutputPolicyValidator.validate(
        "Dạ anh/chị dùng NPK 20-20-15 cho giai đoạn này ạ.",
        page_id=PageCode.CFC,
        workflow=WorkflowType.AGRICULTURE_ADVICE,
        grounding_texts=["Hướng dẫn hữu cơ đã duyệt, không nêu công thức NPK."],
    )

    assert not result.is_valid
    assert any(reason.startswith("UNGROUNDED_PRODUCT_FORMULA") for reason in result.reasons)
    assert "20-20-15" not in result.text


def test_validator_accepts_valid_phone_confirmation_when_slot_exists() -> None:
    text = "Dạ em đã ghi nhận số điện thoại 0918123456 của anh/chị ạ."
    result = OutputPolicyValidator.validate(
        text,
        page_id=PageCode.CFC,
        workflow=WorkflowType.PRICE_HANDOFF,
        slots={"phone": "0918123456"},
    )
    assert result.is_valid
    assert "0918123456" in result.text


def test_validator_blocks_unapproved_fabricated_phone_numbers() -> None:
    # Fabricated phone number not in customer slot and not in official contacts
    text = "Anh/chị vui lòng gọi số 0939999888 để gặp đại lý nha!"
    result = OutputPolicyValidator.validate(
        text,
        page_id=PageCode.CFC,
        workflow=WorkflowType.DEALER_LOOKUP,
        slots={},
        allowed_phones={"19005307", "0981205448"},
        fallback="Anh/chị có thể liên hệ hotline 1900 5307 để được hỗ trợ ạ.",
    )
    assert not result.is_valid
    assert any("UNAPPROVED_PHONE_NUMBER" in r for r in result.reasons)
    assert "0939999888" not in result.text


def test_validator_allows_official_hotline_phone_number() -> None:
    text = "Anh/chị vui lòng gọi hotline 1900 5307 để được hỗ trợ nhanh nhất ạ."
    result = OutputPolicyValidator.validate(
        text,
        page_id=PageCode.CFC,
        workflow=WorkflowType.CONTACT_SUPPORT,
        allowed_phones={"19005307", "0981205448"},
    )
    assert result.is_valid
    assert "1900 5307" in result.text


def test_validator_blocks_forbidden_persona_forms() -> None:
    # Addressing customer as 'bạn'
    result1 = OutputPolicyValidator.validate(
        "Chào bạn, bạn cho mình xin thông tin nhé!",
        page_id=PageCode.CFC,
        workflow=WorkflowType.FAQ_ANSWER,
        fallback="Dạ em chào anh/chị ạ, anh/chị cho em xin thêm thông tin nhé!",
    )
    assert not result1.is_valid
    assert any("FORBIDDEN_PERSONA" in r for r in result1.reasons)
    assert "anh/chị" in result1.text

    # Addressing customer as 'bà con'
    result2 = OutputPolicyValidator.validate(
        "Bà con cần tư vấn cách dùng phân cứ nhắn em nha!",
        page_id=PageCode.CFC,
        workflow=WorkflowType.AGRICULTURE_ADVICE,
        fallback="Dạ anh/chị cần tư vấn cứ nhắn em nha!",
    )
    assert not result2.is_valid
    assert any("FORBIDDEN_PERSONA" in r for r in result2.reasons)
    assert "bà con" not in result2.text.lower()
