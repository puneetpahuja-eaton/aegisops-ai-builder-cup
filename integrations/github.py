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


def _list_files(owner: str, repo: str, branch: str) -> tuple[list[dict], bool, int]:
    url = f"{_API}/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
    response = requests.get(url, headers=_headers(), timeout=30)
    response.raise_for_status()
    payload = response.json()
    truncated = bool(payload.get("truncated"))
    matched = [item for item in payload.get("tree", [])
               if item.get("type") == "blob" and _is_text_path(item.get("path", ""))
               and item.get("size", 0) <= _MAX_BYTES]
    return matched[:_MAX_FILES], truncated, len(matched)


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


def ingest_repo(device_id: str, repo_ref: str, branch: str | None = None,
                link_id: str | None = None) -> dict:
    owner, repo = parse_repo(repo_ref)
    branch = branch or _default_branch(owner, repo)
    files, truncated, matched = _list_files(owner, repo, branch)
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
                                    kind="github", text=text, link_id=link_id)
        ingested += 1
        chunks += record["chunk_count"]
    return {"files": ingested, "chunks": chunks, "repo": f"{owner}/{repo}", "branch": branch,
            "matched": matched, "capped": matched > len(files), "tree_truncated": truncated}
