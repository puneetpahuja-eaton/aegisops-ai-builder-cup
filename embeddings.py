"""Text embeddings via Vertex AI, with a deterministic offline fallback.

Live mode uses Vertex AI `text-embedding-004` through the google-genai client.
Offline mode uses a deterministic hashed bag-of-words vector so retrieval still
works (keyword overlap) for local development and tests without any credentials.

Requests are batched and retried with exponential backoff so bulk ingestion
tolerates per-minute embedding quota limits (HTTP 429 RESOURCE_EXHAUSTED).
"""
from __future__ import annotations

import hashlib
import math
import os
import re
import time

from gemini_client import is_live

_DIM = 256
_MODEL = os.getenv("EMBED_MODEL", "text-embedding-004")
_TOKEN = re.compile(r"[a-z0-9]+")
_BATCH = int(os.getenv("EMBED_BATCH", "16"))
_MAX_RETRIES = int(os.getenv("EMBED_MAX_RETRIES", "6"))


def backend() -> str:
    return f"vertex:{_MODEL}" if is_live() else "offline-hashed"


def _offline_embed(text: str) -> list[float]:
    vector = [0.0] * _DIM
    for token in _TOKEN.findall(text.lower()):
        index = int(hashlib.md5(token.encode()).hexdigest()[:8], 16) % _DIM
        vector[index] += 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    if norm:
        vector = [value / norm for value in vector]
    return vector


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    if not is_live():
        return [_offline_embed(text) for text in texts]
    from gemini_client import _client  # Reuse the configured Vertex/AI-Studio client.
    from google.genai import errors

    out: list[list[float]] = []
    with _client() as client:
        for start in range(0, len(texts), _BATCH):
            batch = texts[start:start + _BATCH]
            for attempt in range(_MAX_RETRIES):
                try:
                    result = client.models.embed_content(model=_MODEL, contents=batch)
                    out.extend([list(embedding.values) for embedding in result.embeddings])
                    break
                except errors.APIError as error:
                    retryable = error.code in (429, 500, 503)
                    if retryable and attempt < _MAX_RETRIES - 1:
                        time.sleep(min(60, 8 * (attempt + 1)))  # Back off on quota/rate limits.
                        continue
                    raise
    return out


def embed_text(text: str) -> list[float]:
    return embed_texts([text])[0]
