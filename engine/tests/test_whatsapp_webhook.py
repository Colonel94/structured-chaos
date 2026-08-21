"""WhatsApp Cloud API webhook + send — the live receive/reply path (host-safe; no DB, no network).

Covers the parts that must be right before a real message ever arrives: Meta's verification handshake,
the HMAC signature gate, payload parsing (ignoring status receipts), and the Cloud API send request shape.
The end-to-end pipeline (inbound → structured case → reply) reuses the already-tested ingest/elicit/
dispatch path and is exercised live on the GPU, not re-mocked here.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Self

import httpx
import pytest
from fastapi.testclient import TestClient

import app.config as config_mod
from app.api.whatsapp import _extract_text_messages
from app.backends.cloud.channel_whatsapp import WhatsAppChannel
from app.config import Settings
from app.main import app

client = TestClient(app)


# --------------------------------------------------------------------- GET verification handshake


def test_verify_echoes_challenge_with_correct_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config_mod.settings, "whatsapp_verify_token", "the-verify-token")
    r = client.get(
        "/api/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "the-verify-token",
            "hub.challenge": "1234567890",
        },
    )
    assert r.status_code == 200 and r.text == "1234567890"


def test_verify_rejects_wrong_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config_mod.settings, "whatsapp_verify_token", "the-verify-token")
    r = client.get(
        "/api/whatsapp/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": "WRONG", "hub.challenge": "x"},
    )
    assert r.status_code == 403


# --------------------------------------------------------------------- POST signature gate + ACK


def _sign(secret: str, raw: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def test_post_rejects_bad_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config_mod.settings, "whatsapp_app_secret", "app-secret")
    monkeypatch.setattr(config_mod.settings, "whatsapp_tenant_id", "")  # no processing either way
    body = json.dumps({"entry": []}).encode()
    r = client.post(
        "/api/whatsapp/webhook", content=body, headers={"X-Hub-Signature-256": "sha256=deadbeef"}
    )
    assert r.status_code == 403


def test_post_acks_valid_signature_without_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config_mod.settings, "whatsapp_app_secret", "app-secret")
    monkeypatch.setattr(
        config_mod.settings, "whatsapp_tenant_id", ""
    )  # unconfigured → ACK, no work
    body = json.dumps({"object": "whatsapp_business_account", "entry": []}).encode()
    r = client.post(
        "/api/whatsapp/webhook",
        content=body,
        headers={"X-Hub-Signature-256": _sign("app-secret", body)},
    )
    assert r.status_code == 200


# --------------------------------------------------------------------- payload parsing


def test_extract_text_messages_parses_and_ignores_non_text() -> None:
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [{"wa_id": "447700900001"}],
                            "messages": [
                                {
                                    "from": "447700900001",
                                    "type": "text",
                                    "text": {"body": "the cake was late and squashed"},
                                }
                            ],
                        }
                    },
                    # a delivery/read status event carries no text message → must be ignored
                    {"value": {"statuses": [{"id": "wamid.x", "status": "delivered"}]}},
                ]
            }
        ]
    }
    assert _extract_text_messages(payload) == [("447700900001", "the cake was late and squashed")]


def test_extract_ignores_media_only_messages() -> None:
    payload = {
        "entry": [{"changes": [{"value": {"messages": [{"from": "44x", "type": "image"}]}}]}]
    }
    assert _extract_text_messages(payload) == []


# --------------------------------------------------------------------- Cloud API send request shape


def test_send_posts_to_cloud_api_and_returns_message_id(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _Resp:
        def raise_for_status(self) -> None: ...
        def json(self) -> dict[str, object]:
            return {"messages": [{"id": "wamid.SENT123"}]}

    class _FakeClient:
        def __init__(self, *a: object, **k: object) -> None: ...
        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *a: object) -> bool:
            return False

        async def post(self, url: str, **kw: object) -> _Resp:
            captured["url"] = url
            captured["kw"] = kw
            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
    cfg = Settings(
        whatsapp_token="TOKEN",
        whatsapp_phone_number_id="PHONE_ID",
        whatsapp_api_version="v21.0",
    )
    chan = WhatsAppChannel(cfg)

    import asyncio

    ref = asyncio.run(chan.send(recipient="447700900001", text="We've found your order BK-1001…"))

    assert ref == "wamid.SENT123"
    assert captured["url"] == "https://graph.facebook.com/v21.0/PHONE_ID/messages"
    kw = captured["kw"]
    assert kw["headers"]["Authorization"] == "Bearer TOKEN"  # type: ignore[index]
    assert kw["json"]["to"] == "447700900001"  # type: ignore[index]
    assert kw["json"]["text"]["body"].startswith("We've found your order")  # type: ignore[index]


def test_channel_raises_without_credentials() -> None:
    with pytest.raises(RuntimeError, match="Meta test number"):
        WhatsAppChannel(Settings(whatsapp_token="", whatsapp_phone_number_id=""))
