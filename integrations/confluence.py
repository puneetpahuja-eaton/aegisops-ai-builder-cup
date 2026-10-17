"""Confluence Cloud page ingestion for device knowledge."""
from __future__ import annotations

import os
import re

import requests

import ingest
import netsetup
import secretmgr

netsetup.configure_tls()


def _config() -> tuple[str, str, str]:
    base = os.getenv("CONFLUENCE_BASE_URL") or secretmgr.get_secret("confluence_base_url") or ""
    email = os.getenv("CONFLUENCE_EMAIL") or secretmgr.get_secret("confluence_email") or ""
    api_token = os.getenv("CONFLUENCE_API_TOKEN") or secretmgr.get_secret("confluence_api_token") or ""
    if not (base and email and api_token):
        raise ValueError("Confluence is not configured. Set base URL, email and API token in Integrations.")
    return base.rstrip("/"), email, api_token


def _auth(email: str, api_token: str) -> tuple[str, str]:
    return (email, api_token)


def page_id_from(ref: str) -> str:
    ref = ref.strip()
    if ref.isdigit():
        return ref
    match = re.search(r"/pages/(\d+)", ref)
    if match:
        return match.group(1)
    raise ValueError("Provide a numeric Confluence page ID or a page URL containing /pages/<id>.")


def _html_to_text(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html)
    text = re.sub(r"</(p|div|li|h[1-6]|tr)>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def ingest_page(device_id: str, page_ref: str) -> dict:
    base, email, api_token = _config()
    page_id = page_id_from(page_ref)
    url = f"{base}/wiki/rest/api/content/{page_id}?expand=body.storage,title"
    response = requests.get(url, auth=_auth(email, api_token), timeout=20,
                            headers={"Accept": "application/json"})
    response.raise_for_status()
    payload = response.json()
    title = payload.get("title", f"page-{page_id}")
    html = payload.get("body", {}).get("storage", {}).get("value", "")
    text = _html_to_text(html)
    if not text.strip():
        raise ValueError("The Confluence page returned no readable content.")
    record = ingest.ingest_text(device_id, name=f"confluence:{title}", kind="confluence", text=text)
    return {"title": title, "chunks": record["chunk_count"], "page_id": page_id}
