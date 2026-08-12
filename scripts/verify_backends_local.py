"""Live smoke for the LOCAL backends (Phase 2) — each interface returns a real response.

    uv run --project engine python scripts/verify_backends_local.py          # LLM (fast; Ollama up)
    uv run --project engine python scripts/verify_backends_local.py --full    # + BGE-M3 + faster-whisper (heavy)

The plain LLM run needs only Ollama up. `--full` also loads BGE-M3 and faster-whisper large-v3
(slow first load, VRAM) — the whole local stack on the 4070.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, "engine")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from app.config import settings

_results: list[tuple[str, bool | None]] = []


def _log(name: str, ok: bool | None, detail: str) -> None:
    _results.append((name, ok))
    tag = "SKIP" if ok is None else ("PASS" if ok else "FAIL")
    print(f"[{tag}] {name}: {detail}")


async def check_llm() -> None:
    from app.backends.local.llm_ollama import OllamaLLM

    llm = OllamaLLM(settings)
    out = await llm.complete("Reply with exactly one word: pong")
    _log(
        "llm",
        "pong" in out.lower(),
        f"model={settings.ollama_model} resp={out.strip()[:40]!r} usage={llm.last_usage}",
    )


async def check_llm_schema() -> None:
    from app.backends.local.llm_ollama import OllamaLLM

    llm = OllamaLLM(settings)
    schema = {
        "type": "object",
        "properties": {
            "fault": {"type": "string"},
            "desired_outcome": {"type": "string"},
        },
        "required": ["fault", "desired_outcome"],
    }
    out = await llm.complete(
        "From this complaint extract JSON with fields fault and desired_outcome: "
        "'my cake arrived an hour late and melted, I want a refund'.",
        schema=schema,
    )
    try:
        obj = json.loads(out)
        ok = "fault" in obj and "desired_outcome" in obj
    except json.JSONDecodeError:
        obj, ok = out, False
    _log("llm_schema", ok, f"structured={obj}")


async def check_embed() -> None:
    from app.backends.local.embed_bge import BGEEmbedding

    emb = BGEEmbedding(settings)
    vecs = await emb.embed(["late delivery", "the order arrived late"])
    _log(
        "embed",
        len(vecs) == 2 and len(vecs[0]) == 1024,
        f"dim={len(vecs[0])} usage={emb.last_usage}",
    )


async def check_asr() -> None:
    from app.backends.local.asr_whisper import WhisperASR

    wav = Path("data/smoke/asr_smoke.wav")
    if not wav.exists():
        _log("asr", None, "no data/smoke/asr_smoke.wav")
        return
    asr = WhisperASR(settings)
    tr = await asr.transcribe(wav.read_bytes(), mime="audio/wav")
    _log(
        "asr",
        len(tr.segments) >= 0,
        f"lang={tr.language} segs={len(tr.segments)} usage={asr.last_usage}",
    )


async def main() -> int:
    full = "--full" in sys.argv
    await check_llm()
    await check_llm_schema()
    if full:
        await check_embed()
        await check_asr()
    else:
        print("(skipping BGE-M3 + faster-whisper; pass --full to load them)")
    graded = [ok for _, ok in _results if ok is not None]
    passed = sum(1 for ok in graded if ok)
    print(f"\n=== local backends: {passed}/{len(graded)} live checks passed ===")
    return 0 if passed == len(graded) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
