"""Persistent per-device knowledge-link registry (GitHub repos, Confluence pages).

Links are stored in the datastore so they survive logins/logouts and deployments
(with Firestore). Re-ingesting a link refreshes its chunks instead of duplicating
them, so the device's knowledge accumulates cleanly across different sources and
stays current for any single source.
"""
from __future__ import annotations

import datetime
import hashlib

import datastore
import devices
import ingest
from integrations import confluence, github

LINK_KINDS = ("github", "confluence")


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _link_id(kind: str, ref: str) -> str:
    return f"{kind}-{hashlib.md5(ref.strip().lower().encode()).hexdigest()[:12]}"


def list_links(device_id: str) -> list[dict]:
    return sorted(datastore.list_docs(devices.links_path(device_id)),
                  key=lambda item: item.get("added_at", ""))


def _save_link(device_id: str, link_id: str, kind: str, ref: str, result: dict) -> None:
    existing = datastore.get_doc(devices.links_path(device_id), link_id) or {}
    datastore.set_doc(devices.links_path(device_id), link_id, {
        "id": link_id, "kind": kind, "ref": ref,
        "added_at": existing.get("added_at", _now()), "last_ingested": _now(),
        "chunk_count": result.get("chunks", 0), "file_count": result.get("files"),
        "detail": result,
    })


def add_or_refresh(device_id: str, kind: str, ref: str, branch: str | None = None) -> dict:
    """Ingest a GitHub repo or Confluence page and register it for persistence.

    Refreshes any prior ingestion of the same link so chunks are current, not duplicated.
    """
    if kind not in LINK_KINDS:
        raise ValueError("Unsupported link kind.")
    ref = ref.strip()
    link_id = _link_id(kind, ref if kind == "confluence" else ref)
    ingest.delete_by_link(device_id, link_id)
    if kind == "github":
        result = github.ingest_repo(device_id, ref, branch, link_id=link_id)
    else:
        result = confluence.ingest_page(device_id, ref, link_id=link_id)
    _save_link(device_id, link_id, kind, ref, result)
    return result


def reingest_all(device_id: str) -> list[dict]:
    """Re-pull every saved link so the agent is retrained on the latest content."""
    outcomes = []
    for link in list_links(device_id):
        try:
            result = add_or_refresh(device_id, link["kind"], link["ref"])
            outcomes.append({"ref": link["ref"], "ok": True, **result})
        except Exception as error:  # noqa: BLE001
            outcomes.append({"ref": link["ref"], "ok": False, "error": str(error)})
    return outcomes


def delete_link(device_id: str, link_id: str, *, purge: bool = True) -> None:
    if purge:
        ingest.delete_by_link(device_id, link_id)
    datastore.delete_doc(devices.links_path(device_id), link_id)
