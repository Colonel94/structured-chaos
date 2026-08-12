"""Local backend impls — the PoC's primary path on the RTX 4070 (owner override 2026-08-10).

faster-whisper (ASR) · Ollama quantized instruct model (LLM) · BGE-M3 (embeddings); the blob
store (MinIO) is shared with the cloud path. Every call records `last_usage` (wall time + tokens /
audio-seconds) so the cost-per-case meter can attribute GPU cost/throughput to a case.
"""
