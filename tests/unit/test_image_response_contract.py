"""Attachment metadata is receipt evidence, not vision or a callback booking."""

import pytest

from src.chatbot.modules.llm.ollama import OllamaResponseGenerator
from src.chatbot.modules.orchestration.input_analyzer import VietnameseNormalizer
from src.chatbot.modules.workflows.composer import ResponseComposer
from src.chatbot.modules.workflows.policy_validator import OutputPolicyValidator
from src.chatbot.shared.enums import PageCode, WorkflowType


class CapturingGenerator:
    def __init__(self, reply):
        self.reply = reply
        self.payload = None

    def generate(self, payload):
        self.payload = payload
        return self.reply


@pytest.mark.parametrize("page", list(PageCode))
@pytest.mark.parametrize("reply", [
    "Anh/chị chụp ảnh vườn gửi em nhé, em sẽ liên hệ trước 15h30 chiều nay.",
    "Anh/chị gửi hình để em xem nhé.",
    "Anh/chị gửi lại ảnh vườn nhé.",
    "Dạ em sẽ liên hệ cho anh/chị.",
    "Dạ em đã chuyển thông tin cho kỹ sư.",
    "Em hẹn anh/chị ngày mai nhé.",
])
def test_image_rejects_repeated_requests_and_unbooked_callbacks(page, reply):
    generator = CapturingGenerator(reply)
    composer = ResponseComposer(generator=generator)
    answer = composer.compose_image_inquiry_response(
        page, customer_text="Nhờ tư vấn hình này", deadline_text="15h30 chiều nay"
    )
    assert "đã nhận được hình ảnh" in answer
    assert "15h30" not in answer
    assert "sẽ liên hệ" not in answer
    assert "chụp ảnh" not in answer
    assert "gửi hình" not in answer
    assert "moc_hen_lien_he" not in generator.payload
    assert generator.payload["attachment_context"] == {
        "received_types": ["image"], "content_analyzed": False,
    }
    assert generator.payload["contact_commitment_allowed"] is False
    assert generator.payload["handoff_created"] is False


def test_image_fallback_only_asks_missing_fields():
    generator = CapturingGenerator(None)
    composer = ResponseComposer(generator=generator)
    answer = composer.compose_image_inquiry_response(
        PageCode.CFC, slots={"crop": "mít", "stage": "nuôi trái"}
    )
    assert "loại cây" not in answer
    assert "giai đoạn" not in answer
    assert "tình trạng hoặc mục tiêu" in answer
    assert generator.payload["missing_information"] == ["tình trạng hoặc mục tiêu cần tư vấn"]


def test_image_with_complete_slots_does_not_invent_diagnosis():
    answer = ResponseComposer().compose_image_inquiry_response(
        PageCode.CFC, slots={"crop": "mít", "stage": "nuôi trái", "problem": "vàng lá"}
    )
    assert "chưa có kết quả phân tích" in answer
    assert "chuyên viên kỹ thuật" in answer
    assert "sẽ" not in answer


def test_grounded_image_acknowledgment_is_not_always_replaced():
    reply = "Dạ em đã nhận được hình ảnh. Anh/chị đang trồng cây gì ạ?"
    generator = CapturingGenerator(reply)
    assert ResponseComposer(generator=generator).compose_image_inquiry_response(PageCode.CFC) == reply


def test_attachment_guard_also_validates_fallback():
    result = OutputPolicyValidator.validate(
        "Anh/chị gửi ảnh nhé.", page_id=PageCode.CFC,
        workflow=WorkflowType.AGRICULTURE_ADVICE,
        fallback="Em sẽ liên hệ trước 15h30.",
        received_attachment_types=("image",), contact_commitment_allowed=False,
    )
    assert "REPEATED_IMAGE_REQUEST" in result.reasons
    assert "UNSAFE_FALLBACK_REJECTED" in result.reasons
    assert "15h30" not in result.text


@pytest.mark.parametrize("pronoun", ["a", "ac", "a/c", "anh", "chị", "em"])
def test_colloquial_pronouns_are_not_crop_names(pronoun):
    normalizer = VietnameseNormalizer("config/normalization/vi_intent.json")
    assert normalizer.normalize_crop_candidate(pronoun) is None
    assert normalizer.normalize_crop_candidate("mít") == "mít"


@pytest.mark.parametrize("page", ["CFC", "ZEO"])
def test_response_prompt_has_same_safety_contract_for_both_pages(page):
    prompt = OllamaResponseGenerator._build_system_prompt(page)
    assert "contact_commitment_allowed=false" in prompt
    assert "content_analyzed=false" in prompt
    assert "Tuyệt đối không báo giá" in prompt
    assert "anh/chị/em" not in prompt
    assert ("Phân bón Cò Bay" in prompt) == (page == "CFC")


def test_missing_response_prompt_falls_back_without_network(monkeypatch):
    def unavailable(_):
        raise FileNotFoundError
    monkeypatch.setattr(OllamaResponseGenerator, "_build_system_prompt", staticmethod(unavailable))
    assert OllamaResponseGenerator("http://unused", "unused").generate({}) is None
