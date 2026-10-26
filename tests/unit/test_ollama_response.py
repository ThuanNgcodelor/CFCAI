import pytest
from pydantic import ValidationError

from src.chatbot.modules.llm.ollama import GeneratedReply


def test_generated_reply_schema_requires_only_nonempty_reply() -> None:
    assert GeneratedReply.model_validate({"reply": "Dạ em đã nhận thông tin ạ."}).reply

    with pytest.raises(ValidationError):
        GeneratedReply.model_validate({"reply": ""})

    with pytest.raises(ValidationError):
        GeneratedReply.model_validate(
            {"reply": "Nội dung", "so_dien_thoai_khach": "{placeholder}"}
        )
