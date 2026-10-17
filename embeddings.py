"""Text embeddings via Vertex AI, with a deterministic offline fallback.

Live mode uses Vertex AI `text-embedding-004` through the google-genai client.
Offline mode uses a deterministic hashed bag-of-words vector so retrieval still
works (keyword overlap) for local development and tests without any credentials.
"""
from __future__ import annotations

import hashlib
import math
import os
import re

from gemini_client import is_live

_DIM = 256
_MODEL = os.getenv("EMBED_MODEL", "text-embedding-004")
_TOKEN = re.compile(r"[a-z0-9]+")


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

    with _client() as client:
        result = client.models.embed_content(model=_MODEL, contents=texts)
    return [list(embedding.values) for embedding in result.embeddings]


def embed_text(text: str) -> list[float]:
    return embed_texts([text])[0]
