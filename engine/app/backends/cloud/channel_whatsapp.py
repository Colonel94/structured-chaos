"""WhatsAppChannel — the cloud egress path (WhatsApp Cloud API).

Behind the same ``Channel`` interface as ``LocalChannel``, so selecting ``channel_backend=cloud`` flips
the loop from record-and-relay to live transmission with no code change. Sends a free-form text reply to
the customer over the WhatsApp Cloud API — valid because the customer messaged us first, so the case is
inside the 24h customer-service window (no template required). Requires the Meta test number
credentials; raises loudly if selected without them rather than pretending to send.
"""

from __future__ import annotations

import httpx

from ...config import Settings, settings


class WhatsAppChannel:
    def __init__(self, cfg: Settings = settings) -> None:
        if not cfg.whatsapp_token or not cfg.whatsapp_phone_number_id:
            raise RuntimeError(
                "channel_backend=cloud (WhatsApp) needs the Meta test number — set whatsapp_token + "
                "whatsapp_phone_number_id (see docs/WHATSAPP-SETUP.md) before selecting it."
            )
        self._cfg = cfg

    async def send(self, *, recipient: str, text: str) -> str:
        """POST a text message to ``recipient`` (their wa_id / phone) and return the Cloud API message id
        (the durable external ref the outbound ledger records). Raises on a non-2xx so a send failure
        rolls the dispatch claim back and a retry re-sends (dispatch.py's transaction guarantee)."""
        url = (
            f"https://graph.facebook.com/{self._cfg.whatsapp_api_version}"
            f"/{self._cfg.whatsapp_phone_number_id}/messages"
        )
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {self._cfg.whatsapp_token}"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        # {"messages":[{"id":"wamid...."}], ...}
        return str(data.get("messages", [{}])[0].get("id", ""))
