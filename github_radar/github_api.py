from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from dataclasses import dataclass
from typing import Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .models import Repository


API_ROOT = "https://api.github.com"
MAX_REQUEST_ATTEMPTS = 3
BASE_RETRY_SECONDS = 2.0
MAX_RETRY_SECONDS = 20.0
_LAST_AUTH_SOURCE = "anonymous API"


@dataclass(frozen=True)
class _CredentialCandidate:
    source: str
    token: str | None


class GitHubApiError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after: float | None = None,
        retriable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after
        self.retriable = retriable


def last_auth_source() -> str:
    return _LAST_AUTH_SOURCE


def search_repositories(
    queries: Iterable[str],
    *,
    per_page: int = 50,
    token: str | None = None,
    pause_seconds: float = 6.2,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> list[Repository]:
    candidates = _credential_candidates(token)
    active_token = candidates[0].token
    seen: set[str] = set()
    repos: list[Repository] = []
    query_list = list(queries)
    total = len(query_list)

    for index, query in enumerate(query_list):
        if progress_callback is not None:
            progress_callback(index, total, query)
        payload = _request_json(
            "/search/repositories",
            {
                "q": query,
                "sort": "stars",
                "order": "desc",
                "per_page": str(per_page),
            },
            candidates=candidates,
        )
        active_token = candidates[0].token
        for item in payload.get("items", []):
            full_name = item.get("full_name", "")
            if not full_name or full_name in seen:
                continue
            seen.add(full_name)
            repos.append(_repo_from_item(item, query))

        # Unauthenticated GitHub search is rate-limited to a small per-minute bucket.
        if active_token is None and index < len(query_list) - 1:
            time.sleep(pause_seconds)

    return repos


def fetch_repository(full_name: str, *, token: str | None = None) -> Repository:
    candidates = _credential_candidates(token)
    clean_name = full_name.strip().strip("/")
    if "/" not in clean_name:
        raise GitHubApiError("Repository must be in owner/name format.")
    owner, name = clean_name.split("/", 1)
    if not owner or not name:
        raise GitHubApiError("Repository must be in owner/name format.")
    payload = _request_json(
        f"/repos/{quote(owner, safe='')}/{quote(name, safe='')}",
        {},
        candidates=candidates,
    )
    return _repo_from_item(payload, f"manual:{payload.get('full_name', clean_name)}")


def fetch_latest_release(repo: str, *, token: str | None = None) -> dict:
    candidates = _credential_candidates(token)
    clean_name = repo.strip().strip("/")
    if "/" not in clean_name:
        raise GitHubApiError("Repository must be in owner/name format.")
    owner, name = clean_name.split("/", 1)
    if not owner or not name:
        raise GitHubApiError("Repository must be in owner/name format.")
    return _request_json(
        f"/repos/{quote(owner, safe='')}/{quote(name, safe='')}/releases/latest",
        {},
        candidates=candidates,
    )


def _request_json(path: str, params: dict[str, str], *, candidates: list[_CredentialCandidate]) -> dict:
    global _LAST_AUTH_SOURCE
    last_auth_error: GitHubApiError | None = None
    for candidate in list(candidates):
        _LAST_AUTH_SOURCE = candidate.source
        try:
            payload = _request_json_with_retries(path, params, token=candidate.token)
            if candidates and candidates[0] != candidate:
                candidates.remove(candidate)
                candidates.insert(0, candidate)
            return payload
        except GitHubApiError as exc:
            if not _can_try_next_credential(exc):
                raise
            last_auth_error = exc
            continue
    if last_auth_error is not None:
        raise last_auth_error
    raise GitHubApiError("No GitHub API credential candidates available.")


def _request_json_with_retries(path: str, params: dict[str, str], *, token: str | None) -> dict:
    last_error: GitHubApiError | None = None
    for attempt in range(1, MAX_REQUEST_ATTEMPTS + 1):
        try:
            return _request_json_with_token(path, params, token=token)
        except GitHubApiError as exc:
            last_error = exc
            if attempt >= MAX_REQUEST_ATTEMPTS or not exc.retriable:
                raise
            time.sleep(_retry_delay(exc, attempt))
    if last_error is not None:
        raise last_error
    raise GitHubApiError("GitHub API request failed before any attempt was made.")


def _request_json_with_token(path: str, params: dict[str, str], *, token: str | None) -> dict:
    query = f"?{urlencode(params)}" if params else ""
    url = f"{API_ROOT}{path}{query}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "github-radar-local",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise GitHubApiError(
            f"GitHub API returned {exc.code}: {body}",
            status_code=exc.code,
            retry_after=_parse_retry_after(exc.headers.get("Retry-After")),
            retriable=_is_retriable_http_error(exc.code, body),
        ) from exc
    except URLError as exc:
        raise GitHubApiError(f"GitHub API request failed: {exc}", retriable=True) from exc
    except (TimeoutError, socket.timeout) as exc:
        raise GitHubApiError(f"GitHub API request timed out: {exc}", retriable=True) from exc


def _credential_candidates(preferred_token: str | None) -> list[_CredentialCandidate]:
    candidates: list[_CredentialCandidate] = []
    seen: set[str] = set()

    def add(source: str, token: str | None) -> None:
        cleaned = token.strip() if token else ""
        if not cleaned:
            return
        if cleaned in seen:
            return
        seen.add(cleaned)
        candidates.append(_CredentialCandidate(source, cleaned))

    add("Settings token", preferred_token)
    add("GitHub CLI login", _gh_auth_token())
    add("GH_TOKEN environment variable", os.getenv("GH_TOKEN"))
    add("GITHUB_TOKEN environment variable", os.getenv("GITHUB_TOKEN"))
    candidates.append(_CredentialCandidate("anonymous API", None))
    return candidates


def _gh_auth_token() -> str | None:
    try:
        kwargs = {}
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        completed = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            **kwargs,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def _can_try_next_credential(error: GitHubApiError) -> bool:
    return error.status_code in {401, 403, 429}


def _is_retriable_http_error(status_code: int, body: str) -> bool:
    if status_code in {429, 500, 502, 503, 504}:
        return True
    if status_code != 403:
        return False
    lowered = body.lower()
    return any(
        marker in lowered
        for marker in (
            "rate limit",
            "secondary rate limit",
            "abuse detection",
            "try again later",
            "temporarily",
        )
    )


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    return max(0.0, seconds)


def _retry_delay(error: GitHubApiError, attempt: int) -> float:
    if error.retry_after is not None:
        return min(error.retry_after, MAX_RETRY_SECONDS)
    return min(BASE_RETRY_SECONDS * (2 ** (attempt - 1)), MAX_RETRY_SECONDS)


def _repo_from_item(item: dict, query: str) -> Repository:
    owner = item.get("owner") or {}
    return Repository(
        full_name=item.get("full_name", ""),
        html_url=item.get("html_url", ""),
        description=item.get("description") or "",
        language=item.get("language") or "",
        stars=int(item.get("stargazers_count") or 0),
        forks=int(item.get("forks_count") or 0),
        watchers=int(item.get("watchers_count") or 0),
        open_issues=int(item.get("open_issues_count") or 0),
        topics=list(item.get("topics") or []),
        created_at=item.get("created_at") or "",
        pushed_at=item.get("pushed_at") or "",
        owner=owner.get("login", ""),
        name=item.get("name", ""),
        query=query,
    )
