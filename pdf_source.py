"""Safe, small GitHub PDF reader used by GA Studio.

No credentials are collected from viewers. A configured GITHUB_TOKEN remains
server-side and is sent only to api.github.com.
"""
from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import json
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

DEFAULT_REPO = "peterDataScientia/GA"
DEFAULT_PDF = "graphical_abstract.pdf"
LOCAL_REPO = Path(__file__).resolve().parent
MAX_PDF_BYTES = 40 * 1024 * 1024
_REPO_PART = re.compile(r"^[A-Za-z0-9_.-]+$")


class PdfSourceError(Exception):
    """The requested PDF could not be safely loaded."""


@dataclass(frozen=True)
class PdfDocument:
    content: bytes
    source: str
    reference: str
    blob_sha: str | None = None


def canonical_repo(value: str) -> str:
    """Accept owner/name or a github.com URL, never arbitrary hosts."""
    value = value.strip().rstrip("/")
    if value.startswith(("https://", "http://")):
        parsed = urlsplit(value)
        if parsed.scheme != "https" or parsed.hostname != "github.com":
            raise PdfSourceError("Use a github.com repository URL or owner/repository.")
        value = parsed.path.strip("/")
    if value.endswith(".git"):
        value = value[:-4]
    parts = value.split("/")
    if len(parts) != 2 or not all(_REPO_PART.fullmatch(p) for p in parts):
        raise PdfSourceError("Repository must be in owner/repository format.")
    if any(p in (".", "..") for p in parts):
        raise PdfSourceError("Invalid repository name.")
    return "/".join(parts)


def safe_pdf_path(value: str) -> str:
    value = value.strip()
    components = value.split("/")
    if not value.lower().endswith(".pdf") or any(p in ("", ".", "..") or "\\" in p for p in components):
        raise PdfSourceError("Specify a PDF filename or a relative PDF path in the repository.")
    return value


def validate_pdf(data: bytes) -> bytes:
    if not data.startswith(b"%PDF-"):
        raise PdfSourceError("Downloaded file is not a valid PDF.")
    if len(data) > MAX_PDF_BYTES:
        raise PdfSourceError("The PDF is too large to preview (40 MB limit).")
    return data


def load_bundled_pdf(repo: str, path: str) -> PdfDocument:
    if repo != DEFAULT_REPO or path != DEFAULT_PDF:
        raise PdfSourceError("Bundled preview is only available for the GA repository default PDF.")
    location = LOCAL_REPO / DEFAULT_PDF
    try:
        payload = location.read_bytes()
    except OSError as exc:
        raise PdfSourceError("Bundled PDF was not found in this app deployment.") from exc
    return PdfDocument(validate_pdf(payload), source="Repository copy", reference=str(location.name))


def _request_json(endpoint: str, token: str | None) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "GA-Studio-PDF-Viewer",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request("https://api.github.com" + endpoint, headers=headers)
    try:
        with urlopen(req, timeout=12) as response:
            data = response.read(55 * 1024 * 1024)
            return json.loads(data)
    except HTTPError as exc:
        if exc.code == 404:
            raise PdfSourceError("PDF not found on GitHub, or repository is private. Configure GITHUB_TOKEN for private repositories.") from exc
        if exc.code in (401, 403):
            raise PdfSourceError("GitHub access denied or API limit reached. Check server-side GITHUB_TOKEN permissions.") from exc
        raise PdfSourceError(f"GitHub returned HTTP {exc.code}.") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise PdfSourceError("Could not contact GitHub. Please try again.") from exc
    except (ValueError, UnicodeDecodeError) as exc:
        raise PdfSourceError("GitHub returned an unexpected response.") from exc


def _decode_github_payload(data: dict) -> bytes:
    content = data.get("content")
    if data.get("encoding") != "base64" or not isinstance(content, str):
        raise PdfSourceError("GitHub did not return base64 PDF content.")
    try:
        return validate_pdf(base64.b64decode(content, validate=False))
    except (binascii.Error, ValueError) as exc:
        raise PdfSourceError("Could not decode PDF from GitHub.") from exc


def load_github_pdf(repo: str, path: str, token: str | None = None) -> PdfDocument:
    repo = canonical_repo(repo)
    path = safe_pdf_path(path)
    endpoint = "/repos/" + "/".join(quote(p, safe="") for p in repo.split("/"))
    item = _request_json(endpoint + "/contents/" + quote(path, safe="/"), token)
    if item.get("type") != "file":
        raise PdfSourceError("That GitHub path does not refer to a file.")
    if item.get("encoding") == "base64" and item.get("content"):
        data = _decode_github_payload(item)
    else:
        # GitHub's Contents API omits inline base64 for files over 1 MB.
        sha = item.get("sha", "")
        if not re.fullmatch(r"[a-fA-F0-9]{40}", sha):
            raise PdfSourceError("GitHub returned no PDF data or valid blob ID.")
        data = _decode_github_payload(_request_json(endpoint + "/git/blobs/" + sha, token))
    return PdfDocument(data, source="GitHub latest", reference=f"{repo}/{path}", blob_sha=item.get("sha"))
