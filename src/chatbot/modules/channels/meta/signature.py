import hashlib
import hmac
import logging
from typing import Optional

logger = logging.getLogger(__name__)

def verify_meta_signature(payload_bytes: bytes, signature_header: Optional[str], app_secret: str) -> bool:
    """
    Verifies X-Hub-Signature-256 header sent by Meta Webhook.
    Signature header format: sha256=<hex_digest>
    """
    if not signature_header or not signature_header.startswith("sha256="):
        logger.warning("[Meta Signature] Missing or invalid signature header format.")
        return False

    if not app_secret:
        logger.error("[Meta Signature] App secret not configured.")
        return False

    expected_sig = signature_header[7:]  # strip 'sha256='
    computed_sig = hmac.new(
        key=app_secret.encode("utf-8"),
        msg=payload_bytes,
        digestmod=hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(computed_sig, expected_sig)
