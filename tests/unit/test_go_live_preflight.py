from scripts.verify_go_live import delivery_checks
from src.chatbot.core.settings import Settings


def test_preflight_blocks_delivery_without_explicit_mode_or_admin_token() -> None:
    config = Settings(_env_file=None, DELIVERY_MODE="disabled", ADMIN_API_TOKEN="")
    statuses = {check.name: check.status for check in delivery_checks(config)}
    assert statuses == {"admin_auth": "BLOCKED", "delivery_mode": "BLOCKED"}


def test_preflight_accepts_explicit_canary_scope() -> None:
    config = Settings(
        _env_file=None,
        ADMIN_API_TOKEN="admin-token",
        DELIVERY_MODE="canary",
        CANARY_PAGE_IDS="CFC",
        CANARY_WORKFLOWS="FAQ_ANSWER",
        CANARY_PERCENT=5,
        CANARY_SEND_APPROVED=True,
        DELIVERY_NOT_BEFORE="2000-01-01T00:00:00+00:00",
    )
    statuses = {check.name: check.status for check in delivery_checks(config)}
    assert statuses == {
        "admin_auth": "PASS",
        "delivery_mode": "PASS",
        "canary_scope": "PASS",
        "release_fence": "PASS",
    }


def test_release_debug_marker_is_fail_safe_false() -> None:
    config = Settings(_env_file=None, DEBUG="release")
    assert config.DEBUG is False
