"""Local backend impls — the PoC's primary path on the RTX 4070 (owner override 2026-08-10).

faster-whisper (ASR) · Ollama quantized instruct model (LLM) · BGE-M3 (embeddings); the blob
store (MinIO) is shared with the cloud path. Every call records `last_usage` (wall time + tokens /
audio-seconds) so the cost-per-case meter can attribute GPU cost/throughput to a case.

**Single-flight contract (read this before wiring the meter in Phase 3):** `last_usage` is a
per-instance mutable attribute overwritten on each call. Obtain a backend **per unit of work**
(the registry returns a fresh instance every `get_*()` call) and read `last_usage` **immediately
after** the awaited call, within the same coroutine — never share one instance across concurrent
calls, or the usage of parallel calls will clobber each other and the meter will mis-attribute cost.
"""
