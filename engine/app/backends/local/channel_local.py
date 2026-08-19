"""LocalChannel — the $0 PoC egress sink (owner override 2026-08-10: the PoC runs the local path).

There is no live conversational transport in the local PoC (WhatsApp needs the Meta test number, the
deferred cloud path). So "sending" here is record-and-relay: the durable audit is the ``outbound_message``
row the dispatch step writes; this backend only returns a deterministic local ref so the loop runs and
is testable end-to-end without Meta. Swapping in ``WhatsAppChannel`` (config ``channel_backend=cloud``)
makes the same loop transmit for real, with no code change (CLAUDE.md §4)."""

from __future__ import annotations

import hashlib

from ...config import Settings, settings


class LocalChannel:
    def __init__(self, cfg: Settings = settings) -> None:
        self._cfg = cfg

    async def send(self, *, recipient: str, text: str) -> str:
        # Deterministic ref (no side effect): the message is durably audited by the store, not here.
        digest = hashlib.sha256(f"{recipient}\x1f{text}".encode()).hexdigest()[:16]
        return f"local:{digest}"
