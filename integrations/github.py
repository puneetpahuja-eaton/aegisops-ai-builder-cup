"""GitHub repository ingestion for device knowledge."""
from __future__ import annotations

import base64
import os
from concurrent.futures import ThreadPoolExecutor

import requests

import ingest
import netsetup
import secretmgr

netsetup.configure_tls()

_API = "https://api.github.com"
_TEXT_EXT = (
    # docs
    ".md", ".markdown", ".rst", ".txt", ".adoc", ".tex",
    # config / build
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".properties",
    ".cmake", ".mk", ".mak", ".gradle", ".bazel", ".bzl", ".dox",
    # data
    ".csv", ".tsv", ".xml", ".html", ".css", ".scss",
    # code
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".kt", ".kts", ".scala",
    ".c", ".cc", ".cpp", ".cxx", ".ino", ".h", ".hh", ".hpp", ".hxx", ".inc",
    ".go", ".rs", ".swift", ".m", ".mm", ".rb", ".php", ".pl", ".lua", ".r",
    ".sql", ".proto", ".s", ".asm", ".sh", ".bat", ".ps1", ".psm1",
)
# Common extensionless text files found in firmware/build repos.
_TEXT_NAMES = frozenset({
    "makefile", "gnumakefile", "dockerfile", "cmakelists.txt", "kconfig",
    "kbuild", "readme", "license", "notice", "changelog",
})
_MAX_FILES = 500
_MAX_BYTES = 1_000_000


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
    if response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
        hint = " Add a GitHub token in Integrations to raise the limit to 5000/hour." if not token() else ""
        raise ValueError(f"GitHub API rate limit exceeded.{hint} Try again shortly.")
    response.raise_for_status()
    return response.json()


def _default_branch(owner: str, repo: str) -> str:
    return _repo_info(owner, repo).get("default_branch", "main")


def _is_text_path(path: str) -> bool:
    low = path.lower()
    name = low.rsplit("/", 1)[-1]
    return low.endswith(_TEXT_EXT) or name in _TEXT_NAMES


def _list_files(owner: str, repo: str, branch: str) -> tuple[list[dict], bool, int, str | None]:
    url = f"{_API}/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
    response = requests.get(url, headers=_headers(), timeout=30)
    response.raise_for_status()
    payload = response.json()
    truncated = bool(payload.get("truncated"))
    tree_sha = payload.get("sha")
    matched = [item for item in payload.get("tree", [])
               if item.get("type") == "blob" and _is_text_path(item.get("path", ""))
               and item.get("size", 0) <= _MAX_BYTES]
    return matched[:_MAX_FILES], truncated, len(matched), tree_sha


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


def fetch_file_bytes(repo_ref: str, path: str, branch: str | None = None) -> bytes:
    """Fetch a single file's raw bytes by repo path (supports binary files like .xlsm)."""
    owner, repo = parse_repo(repo_ref)
    branch = branch or _default_branch(owner, repo)
    clean = path.strip().lstrip("/")
    from urllib.parse import quote
    url = f"{_API}/repos/{owner}/{repo}/contents/{quote(clean)}?ref={branch}"
    response = requests.get(url, headers=_headers(), timeout=30)
    if response.status_code == 404:
        raise ValueError(f"File '{clean}' not found in {owner}/{repo}@{branch}. Check the exact path.")
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, list):
        raise ValueError(f"'{clean}' is a directory, not a file.")
    if payload.get("content") and payload.get("encoding") == "base64":
        return base64.b64decode(payload["content"])
    # Large files (>1 MB) return no inline content; fetch via the blob API.
    if payload.get("sha"):
        blob_url = f"{_API}/repos/{owner}/{repo}/git/blobs/{payload['sha']}"
        blob = requests.get(blob_url, headers=_headers(), timeout=30)
        blob.raise_for_status()
        body = blob.json()
        if body.get("encoding") == "base64":
            return base64.b64decode(body["content"])
    raise ValueError(f"Could not read content of '{clean}'.")


def repo_listing(repo_ref: str, branch: str | None = None) -> dict:
    """List matching files with their blob SHAs plus the repo's root tree SHA."""
    owner, repo = parse_repo(repo_ref)
    branch = branch or _default_branch(owner, repo)
    files, truncated, matched, tree_sha = _list_files(owner, repo, branch)
    return {"owner": owner, "repo": repo, "branch": branch, "tree_sha": tree_sha,
            "files": files, "truncated": truncated, "matched": matched}


def ingest_items(device_id: str, owner: str, repo: str, items: list[dict], link_id: str | None = None,
                 on_progress=None, done_offset: int = 0, total: int | None = None) -> tuple[int, int]:
    """Fetch the given tree items in parallel and embed them in one batched pass.

    Returns (files_ingested, chunk_count). Fetching is concurrent (network-bound);
    embedding is batched with backoff so bulk ingests tolerate per-minute quotas.
    """
    total = total if total is not None else len(items)

    def _fetch(item: dict) -> tuple[dict, str | None]:
        try:
            return item, _fetch_blob(owner, repo, item["sha"])
        except requests.RequestException:
            return item, None

    sources, done = [], done_offset
    with ThreadPoolExecutor(max_workers=8) as pool:
        for item, text in pool.map(_fetch, items):
            done += 1
            if text and text.strip():
                sources.append({"name": f"github:{owner}/{repo}/{item['path']}", "kind": "github",
                                "text": text, "meta": {"path": item["path"], "blob_sha": item["sha"]}})
            if on_progress:
                on_progress(done, total, f"fetch {item['path']}")

    if on_progress and sources:
        on_progress(done, total, f"embedding {len(sources)} files…")
    result = ingest.ingest_many(device_id, sources, link_id=link_id, on_progress=on_progress)
    return result["files"], result["chunks"]


def ingest_repo(device_id: str, repo_ref: str, branch: str | None = None,
                link_id: str | None = None, on_progress=None) -> dict:
    """Full ingest (first time or forced). For incremental sync use knowledge.add_or_refresh."""
    listing = repo_listing(repo_ref, branch)
    files = listing["files"]
    if not files:
        raise ValueError("No ingestible text files found in that repository.")
    if on_progress:
        on_progress(0, len(files), "listing files")
    ingested, chunks = ingest_items(device_id, listing["owner"], listing["repo"], files,
                                    link_id=link_id, on_progress=on_progress, total=len(files))
    return {"files": ingested, "chunks": chunks, "repo": f"{listing['owner']}/{listing['repo']}",
            "branch": listing["branch"], "matched": listing["matched"],
            "capped": listing["matched"] > len(files), "tree_truncated": listing["truncated"],
            "tree_sha": listing["tree_sha"],
            "file_shas": {item["path"]: item["sha"] for item in files}}
