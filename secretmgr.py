"""Secret storage for device credentials and integration API keys.

Uses Google Secret Manager when configured; otherwise a local gitignored store.
Callers persist only a secret *reference id*, never the plaintext value.
"""
from __future__ import annotations

import os

import datastore

_LOCAL_SECRETS = "secrets"


def backend() -> str:
    return "secret-manager" if _enabled() else "local"


def _enabled() -> bool:
    return os.getenv("USE_SECRET_MANAGER") == "1" and bool(os.getenv("GOOGLE_CLOUD_PROJECT"))


def _client():
    from google.cloud import secretmanager
    return secretmanager.SecretManagerServiceClient()


def _project() -> str:
    return os.environ["GOOGLE_CLOUD_PROJECT"]


def put_secret(ref: str, value: str) -> str:
    """Store `value` under reference id `ref`; return the ref."""
    if _enabled():
        client = _client()
        parent = f"projects/{_project()}"
        secret_id = f"aegis-{ref}"
        try:
            client.create_secret(request={"parent": parent, "secret_id": secret_id,
                                           "secret": {"replication": {"automatic": {}}}})
        except Exception:
            pass  # Already exists; add a new version below.
        client.add_secret_version(request={"parent": f"{parent}/secrets/{secret_id}",
                                            "payload": {"data": value.encode()}})
        return ref
    datastore.set_doc(_LOCAL_SECRETS, ref, {"value": value})
    return ref


def get_secret(ref: str) -> str | None:
    if _enabled():
        client = _client()
        name = f"projects/{_project()}/secrets/aegis-{ref}/versions/latest"
        try:
            return client.access_secret_version(request={"name": name}).payload.data.decode()
        except Exception:
            return None
    record = datastore.get_doc(_LOCAL_SECRETS, ref)
    return record.get("value") if record else None


def delete_secret(ref: str) -> None:
    if _enabled():
        client = _client()
        name = f"projects/{_project()}/secrets/aegis-{ref}"
        try:
            client.delete_secret(request={"name": name})
        except Exception:
            pass
        return
    datastore.delete_doc(_LOCAL_SECRETS, ref)
