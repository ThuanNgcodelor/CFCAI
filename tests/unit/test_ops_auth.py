# pyrefly: ignore[missing-import]
import pytest

from src.chatbot.modules.ops.auth import (
    parse_role_tokens,
    role_allows_path,
    role_for_token,
)


def test_role_tokens_are_scoped_to_their_admin_paths() -> None:
    tokens = '{"operator":"ops-secret","publisher":"publish-secret"}'
    assert (
        role_for_token(
            "ops-secret", administrator_token="admin-secret", role_tokens_json=tokens
        )
        == "operator"
    )
    assert role_allows_path("operator", "/admin/ops/CFC/pause")
    assert not role_allows_path("operator", "/admin/catalog/import-excel")
    assert role_allows_path("publisher", "/admin/catalog/import-excel")


def test_invalid_role_token_config_is_rejected_without_echoing_a_secret() -> None:
    with pytest.raises((TypeError, ValueError), match="JSON object"):
        parse_role_tokens("not-json-secret-value")
