"""Audio normalisation — voice notes → transcript with segment-level provenance (EDD §4, §2.3).

Decode (ffmpeg, invoked inside faster-whisper) → VAD (bundled silero, ``vad_filter=True``) → ASR.
Each transcript segment becomes one ``audio_segment`` span whose locator is the ``{t_start, t_end}``
utterance window — the PoC's audio provenance granularity (cloud ASR has no word timestamps; the
review screen plays that utterance when a value is clicked, TECH-SPEC §12). Word-level alignment is
the deferred local-stack upgrade (§16.9), not built now.

The ASR backend is injected so this stays backend-agnostic (local faster-whisper today, a cloud
backend behind the same interface tomorrow — zero code change here).
"""

from __future__ import annotations

from ..backends.interfaces import ASRBackend
from ..config import settings
from .models import NormalisedContent, NormalisedSpan


async def normalise_audio(
    source_document_id: str, data: bytes, mime: str, *, asr: ASRBackend
) -> NormalisedContent:
    """Transcribe one voice note into anchored text. Empty/undetected audio yields empty text with
    no spans rather than raising — a silent clip is a real, recordable outcome, not an error."""
    transcript = await asr.transcribe(data, mime=mime)
    spans = [
        NormalisedSpan(
            text=seg.text,
            kind="audio_segment",
            locator={"t_start": seg.t_start, "t_end": seg.t_end},
        )
        for seg in transcript.segments
        if seg.text
    ]
    # last_usage (wall_ms / audio_seconds) is read here, on the same instance we just awaited, so the
    # pipeline can meter this ASR call against the case (cost-per-case, EDD/BUILD-PLAN Phase 2).
    usage = dict(getattr(asr, "last_usage", {}) or {})
    return NormalisedContent(
        source_document_id=source_document_id,
        text=" ".join(s.text for s in spans),
        language=transcript.language,
        spans=spans,
        stage="normalise.audio",
        model="faster-whisper",
        model_version=settings.whisper_model,
        usage=usage,
        interface="asr",
    )
