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
        "tree_sha": result.get("tree_sha"), "file_shas": result.get("file_shas"),
        "version": result.get("version"),
        "detail": {k: v for k, v in result.items() if k != "file_shas"},
    })


def _sync_github(device_id: str, link_id: str, ref: str, branch: str | None,
                 existing: dict, on_progress, force: bool) -> dict:
    listing = github.repo_listing(ref, branch)
    files = listing["files"]
    if not files:
        raise ValueError("No ingestible text files found in that repository.")
    repo_name = f"{listing['owner']}/{listing['repo']}"
    current_shas = {item["path"]: item["sha"] for item in files}
    prev_shas = {} if force else (existing.get("file_shas") or {})

    base = {"repo": repo_name, "branch": listing["branch"], "matched": listing["matched"],
            "capped": listing["matched"] > len(files), "tree_truncated": listing["truncated"],
            "tree_sha": listing["tree_sha"], "file_shas": current_shas}

    # Fast path: the whole repo is unchanged.
    if not force and existing.get("tree_sha") and existing["tree_sha"] == listing["tree_sha"]:
        return {**base, "files": 0, "chunks": existing.get("chunk_count", 0),
                "added": 0, "updated": 0, "removed": 0, "unchanged": len(files), "skipped": True}

    if force:
        ingest.delete_by_link(device_id, link_id)

    changed = [item for item in files if prev_shas.get(item["path"]) != item["sha"]]
    removed_paths = set(prev_shas) - set(current_shas)
    ingest.delete_sources_for_paths(device_id, link_id,
                                    {item["path"] for item in changed} | removed_paths)
    ingested, _ = github.ingest_items(device_id, listing["owner"], listing["repo"], changed,
                                      link_id=link_id, on_progress=on_progress, total=len(changed))
    total_chunks = sum(s.get("chunk_count", 0) for s in ingest.sources_by_link(device_id, link_id))
    added = sum(1 for item in changed if item["path"] not in prev_shas)
    return {**base, "files": ingested, "chunks": total_chunks,
            "added": added, "updated": len(changed) - added, "removed": len(removed_paths),
            "unchanged": len(files) - len(changed), "skipped": False}


def _sync_confluence(device_id: str, link_id: str, ref: str, existing: dict,
                     on_progress, force: bool) -> dict:
    page = confluence.fetch_page(ref)
    if not force and existing.get("version") is not None and existing["version"] == page["version"]:
        return {"title": page["title"], "chunks": existing.get("chunk_count", 0),
                "page_id": page["page_id"], "version": page["version"], "skipped": True}
    ingest.delete_by_link(device_id, link_id)
    if on_progress:
        on_progress(0, 1, "embedding page")
    record = ingest.ingest_text(device_id, name=f"confluence:{page['title']}", kind="confluence",
                                text=page["text"], link_id=link_id, meta={"version": page["version"]})
    if on_progress:
        on_progress(1, 1, page["title"])
    return {"title": page["title"], "chunks": record["chunk_count"], "page_id": page["page_id"],
            "version": page["version"], "skipped": False}


def add_or_refresh(device_id: str, kind: str, ref: str, branch: str | None = None,
                   on_progress=None, force: bool = False) -> dict:
    """Ingest or incrementally refresh a GitHub repo / Confluence page and register it.

    Incremental: only files whose content SHA changed are re-fetched and re-embedded
    (the repo is skipped entirely if its root tree SHA is unchanged). A Confluence page
    is skipped if its version is unchanged. `force=True` does a full re-ingest.
    `on_progress(done, total, label)` drives a progress bar.
    """
    if kind not in LINK_KINDS:
        raise ValueError("Unsupported link kind.")
    ref = ref.strip()
    link_id = _link_id(kind, ref)
    existing = datastore.get_doc(devices.links_path(device_id), link_id) or {}
    if kind == "github":
        result = _sync_github(device_id, link_id, ref, branch, existing, on_progress, force)
    else:
        result = _sync_confluence(device_id, link_id, ref, existing, on_progress, force)
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
