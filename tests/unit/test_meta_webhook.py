import hashlib
import hmac

from src.chatbot.infrastructure.messaging.inbox import DurableInboxStore
from src.chatbot.modules.channels.meta.normalizer import normalize_messenger_payload
from src.chatbot.modules.channels.meta.signature import verify_meta_signature
from src.chatbot.shared.enums import PageCode


def test_meta_hmac_signature_verification():
    secret = "test_meta_secret_key"
    payload = b'{"object":"page","entry":[]}'

    # Generate valid signature
    valid_sig = (
        "sha256="
        + hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    )
    assert verify_meta_signature(payload, valid_sig, secret) is True

    # Tampered payload
    tampered_payload = b'{"object":"page","entry":[{"tampered":true}]}'
    assert verify_meta_signature(tampered_payload, valid_sig, secret) is False

    # Wrong secret
    assert verify_meta_signature(payload, valid_sig, "wrong_secret") is False

    # Malformed signature header
    assert verify_meta_signature(payload, "invalid_header", secret) is False


def test_meta_payload_normalization():
    payload = {
        "object": "page",
        "entry": [
            {
                "id": "1000888999",
                "time": 1700000000000,
                "messaging": [
                    {
                        "sender": {"id": "user_psid_123"},
                        "recipient": {"id": "1000888999"},
                        "timestamp": 1700000000000,
                        "message": {
                            "mid": "mid.msg_001",
                            "text": "Cho mình hỏi giá Cobanic",
                        },
                    }
                ],
            }
        ],
    }

    events = normalize_messenger_payload(payload)
    assert len(events) == 1
    evt = events[0]
    assert evt.event_id == "mid.msg_001"
    assert evt.sender_id == "user_psid_123"
    assert evt.message.text == "Cho mình hỏi giá Cobanic"
    assert evt.page_id == PageCode.CFC


def test_durable_inbox_deduplication():
    # Case T09: Meta retries identical event
    inbox = DurableInboxStore()

    payload = {
        "object": "page",
        "entry": [
            {
                "id": "page_cfc",
                "time": 1700000000000,
                "messaging": [
                    {
                        "sender": {"id": "user_1"},
                        "recipient": {"id": "page_cfc"},
                        "message": {"mid": "mid.retry_123", "text": "Tin nhắn gửi lặp"},
                    }
                ],
            }
        ],
    }
    events = normalize_messenger_payload(payload)
    event = events[0]

    # First write -> Success
    assert inbox.record_event(event) is True
    assert inbox.count_events() == 1

    # Second write (Meta retry) -> Deduplicated & Ignored
    assert inbox.record_event(event) is False
    assert inbox.count_events() == 1
