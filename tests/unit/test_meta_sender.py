import json

from src.chatbot.core.settings import settings
from src.chatbot.modules.channels.meta.sender import MetaSender
from src.chatbot.shared.enums import PageCode


def test_meta_sender_uses_page_scoped_token(monkeypatch) -> None:
    monkeypatch.setattr(settings, "CFC_PAGE_ID", "page-cfc")
    monkeypatch.setattr(settings, "CFC_PAGE_ACCESS_TOKEN", "token-cfc")
    captured: dict[str, object] = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"message_id": "mid-out"}).encode()

    def fake_open(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode())
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_open)
    assert (
        MetaSender("https://graph.test").send_text(PageCode.CFC, "psid-1", "Xin chào")
        == "mid-out"
    )
    assert "token-cfc" in str(captured["url"])
    assert captured["body"] == {
        "recipient": {"id": "psid-1"},
        "message": {"text": "Xin chào"},
        "messaging_type": "RESPONSE",
    }
