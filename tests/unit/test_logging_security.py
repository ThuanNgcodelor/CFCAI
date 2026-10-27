import logging

from src.chatbot.core.logging import SensitiveDataFilter, redact_mapping, redact_text


def test_redact_text_masks_phone_and_credential_values() -> None:
    value = (
        "phone=0981205448 Authorization: Bearer bearer-secret "
        "access_token=page-token client_secret=crm-secret"
    )
    redacted = redact_text(value)
    assert "0981205448" not in redacted
    assert "bearer-secret" not in redacted
    assert "page-token" not in redacted
    assert "crm-secret" not in redacted


def test_redact_mapping_masks_nested_secrets_and_identifiers() -> None:
    redacted = redact_mapping(
        {"phone": "0981205448", "nested": {"client_secret": "secret-value"}}
    )
    assert redacted["phone"] == "***5448"
    assert redacted["nested"]["client_secret"] == "[REDACTED]"


def test_logging_filter_redacts_rendered_format_arguments() -> None:
    record = logging.LogRecord(
        "test",
        logging.ERROR,
        __file__,
        1,
        "failed for %s client_secret=%s",
        ("0981205448", "raw"),
        None,
    )
    assert SensitiveDataFilter().filter(record)
    assert "0981205448" not in str(record.msg)
    assert "raw" not in str(record.msg)
