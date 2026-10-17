"""Document store with a Firestore backend and a local-JSON fallback.

Mirrors the repo's existing pattern (storage.py / gemini_client.py): real Google
Cloud when configured, a deterministic local fallback otherwise so the platform
runs and is testable without any cloud credentials.

Collections are addressed by path strings, including subcollections, e.g.:
  "users", "devices", "devices/<id>/sources", "devices/<id>/chunks".

Vector similarity is computed in-process (bounded per-device corpora), which is
robust for a demo and avoids fragile managed vector-index provisioning.
"""
from __future__ import annotations

import json
import math
import os
import threading
from pathlib import Path
from typing import Any, Iterable

_LOCK = threading.RLock()


def _local_file() -> Path:
    base = Path(os.getenv("AEGIS_LOCAL_STORE", Path(__file__).parent / ".localstore"))
    return base / "db.json"


def is_firestore() -> bool:
    return bool(os.getenv("FIRESTORE_PROJECT") or (os.getenv("USE_FIRESTORE") == "1" and os.getenv("GOOGLE_CLOUD_PROJECT")))


def backend() -> str:
    return "firestore" if is_firestore() else "local"


# --------------------------------------------------------------------------- #
# Firestore backend
# --------------------------------------------------------------------------- #
def _project() -> str:
    return os.getenv("FIRESTORE_PROJECT") or os.environ["GOOGLE_CLOUD_PROJECT"]


def _fs_client():
    from google.cloud import firestore

    credentials = None
    if os.getenv("GOOGLE_OAUTH_ACCESS_TOKEN"):
        from google.oauth2.credentials import Credentials
        credentials = Credentials(os.environ["GOOGLE_OAUTH_ACCESS_TOKEN"])
    database = os.getenv("FIRESTORE_DATABASE", "(default)")
    return firestore.Client(project=_project(), credentials=credentials, database=database)


def _fs_collection(path: str):
    # Path alternates collection/doc/collection/...; an odd number of parts is a collection.
    parts = path.strip("/").split("/")
    if len(parts) % 2 == 0:
        raise ValueError(f"Not a collection path: {path}")
    ref = _fs_client()
    for index, part in enumerate(parts):
        ref = ref.collection(part) if index % 2 == 0 else ref.document(part)
    return ref


# --------------------------------------------------------------------------- #
# Local JSON backend
# --------------------------------------------------------------------------- #
def _load_local() -> dict:
    with _LOCK:
        path = _local_file()
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {}


def _save_local(data: dict) -> None:
    with _LOCK:
        path = _local_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def set_doc(collection: str, doc_id: str, data: dict) -> None:
    if is_firestore():
        _fs_collection(collection).document(doc_id).set(data)
        return
    with _LOCK:
        db = _load_local()
        db.setdefault(collection, {})[doc_id] = data
        _save_local(db)


def update_doc(collection: str, doc_id: str, data: dict) -> None:
    if is_firestore():
        _fs_collection(collection).document(doc_id).set(data, merge=True)
        return
    with _LOCK:
        db = _load_local()
        current = db.setdefault(collection, {}).get(doc_id, {})
        current.update(data)
        db[collection][doc_id] = current
        _save_local(db)


def get_doc(collection: str, doc_id: str) -> dict | None:
    if is_firestore():
        snapshot = _fs_collection(collection).document(doc_id).get()
        return snapshot.to_dict() if snapshot.exists else None
    with _LOCK:
        return _load_local().get(collection, {}).get(doc_id)


def list_docs(collection: str) -> list[dict]:
    if is_firestore():
        return [{"id": snap.id, **(snap.to_dict() or {})} for snap in _fs_collection(collection).stream()]
    with _LOCK:
        return [{"id": doc_id, **data} for doc_id, data in _load_local().get(collection, {}).items()]


def delete_doc(collection: str, doc_id: str) -> None:
    if is_firestore():
        _fs_collection(collection).document(doc_id).delete()
        return
    with _LOCK:
        db = _load_local()
        db.get(collection, {}).pop(doc_id, None)
        _save_local(db)


def count_docs(collection: str) -> int:
    return len(list_docs(collection))


# --------------------------------------------------------------------------- #
# Vector similarity (in-process cosine over a bounded corpus)
# --------------------------------------------------------------------------- #
def _cosine(a: Iterable[float], b: Iterable[float]) -> float:
    a = list(a)
    b = list(b)
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def nearest(collection: str, query_embedding: list[float], top_k: int = 6) -> list[dict]:
    """Return the top_k documents in `collection` closest to the query embedding.

    Each document must contain an `embedding` list field. Scores are attached as
    `_score`. Documents without an embedding are ignored.
    """
    scored: list[tuple[float, dict]] = []
    for doc in list_docs(collection):
        embedding = doc.get("embedding")
        if not embedding:
            continue
        scored.append((_cosine(query_embedding, embedding), doc))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    results = []
    for score, doc in scored[:top_k]:
        item = dict(doc)
        item["_score"] = round(score, 4)
        results.append(item)
    return results
