"""GitHub repository ingestion for device knowledge."""
from __future__ import annotations

import base64
import os

import requests

import ingest
import netsetup
import secretmgr

netsetup.configure_tls()

_API = "https://api.github.com"
_TEXT_EXT = (".md", ".txt", ".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".go",
             ".rs", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".rst", ".sh")
_MAX_FILES = 60
_MAX_BYTES = 200_000


def token() -> str | None:
    return os.getenv("GITHUB_TOKEN") or secretmgr.get_secret("github_token")


def _headers() -> dict:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    tok = token()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    return headers


def _repo_info(owner: str, repo: str) -> dict:
    response = requests.get(f"{_API}/repos/{owner}/{repo}", headers=_headers(), timeout=20)
    if response.status_code == 404:
        hint = "" if token() else " No token is configured — add one in Integrations for private repos."
        raise ValueError(
            f"Repository '{owner}/{repo}' not found or not accessible (404).{hint} For a private org repo, "
            "ensure the token has the 'repo' scope AND is SSO-authorized for the organization "
            "(GitHub → Settings → Developer settings → PAT → Configure SSO).")
    if response.status_code == 401:
        raise ValueError("GitHub rejected the token (401). Check the token value and that it is still valid.")
    response.raise_for_status()
    return response.json()


def _default_branch(owner: str, repo: str) -> str:
    return _repo_info(owner, repo).get("default_branch", "main")


def _list_files(owner: str, repo: str, branch: str) -> list[dict]:
    url = f"{_API}/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
    response = requests.get(url, headers=_headers(), timeout=30)
    response.raise_for_status()
    tree = response.json().get("tree", [])
    return [item for item in tree if item.get("type") == "blob"
            and item.get("path", "").lower().endswith(_TEXT_EXT)
            and item.get("size", 0) <= _MAX_BYTES][:_MAX_FILES]


def _fetch_blob(owner: str, repo: str, sha: str) -> str:
    url = f"{_API}/repos/{owner}/{repo}/git/blobs/{sha}"
    response = requests.get(url, headers=_headers(), timeout=20)
    response.raise_for_status()
    payload = response.json()
    if payload.get("encoding") == "base64":
        return base64.b64decode(payload["content"]).decode("utf-8", errors="replace")
    return payload.get("content", "")


def parse_repo(repo_ref: str) -> tuple[str, str]:
    ref = repo_ref.strip().removeprefix("https://github.com/").removesuffix(".git").strip("/")
    parts = ref.split("/")
    if len(parts) < 2:
        raise ValueError("Use the form owner/repo or a GitHub URL.")
    return parts[0], parts[1]


def ingest_repo(device_id: str, repo_ref: str, branch: str | None = None) -> dict:
    owner, repo = parse_repo(repo_ref)
    branch = branch or _default_branch(owner, repo)
    files = _list_files(owner, repo, branch)
    if not files:
        raise ValueError("No ingestible text files found in that repository.")
    ingested, chunks = 0, 0
    for item in files:
        try:
            text = _fetch_blob(owner, repo, item["sha"])
        except requests.RequestException:
            continue
        if not text.strip():
            continue
        record = ingest.ingest_text(device_id, name=f"github:{owner}/{repo}/{item['path']}",
                                    kind="github", text=text)
        ingested += 1
        chunks += record["chunk_count"]
    return {"files": ingested, "chunks": chunks, "repo": f"{owner}/{repo}", "branch": branch}
