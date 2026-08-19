"""WhatsAppChannel — the cloud egress path (WhatsApp Cloud API). DEFERRED (needs the Meta test number).

Behind the same ``Channel`` interface as ``LocalChannel``, so selecting ``channel_backend=cloud`` flips
the loop from record-and-relay to live transmission with no code change. Not built until Gate A (the
Meta Business test number + verified sender), so — like the other deferred cloud backends — it raises
loudly if selected before setup rather than pretending to send."""

from __future__ import annotations

from ...config import Settings, settings


class WhatsAppChannel:
    def __init__(self, cfg: Settings = settings) -> None:
        if not cfg.whatsapp_token or not cfg.whatsapp_phone_number_id:
            raise RuntimeError(
                "channel_backend=cloud (WhatsApp) is the DEFERRED path — set whatsapp_token + "
                "whatsapp_phone_number_id (the Meta test number, Gate A) before selecting it."
            )
        self._cfg = cfg

    async def send(self, *, recipient: str, text: str) -> str:  # pragma: no cover - deferred path
        raise NotImplementedError(
            "WhatsApp Cloud API send is deferred (Gate A). Use channel_backend=local for the PoC."
        )
