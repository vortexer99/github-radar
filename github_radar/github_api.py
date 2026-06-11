from __future__ import annotations

import json
import os
import time
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .models import Repository


API_ROOT = "https://api.github.com"


class GitHubApiError(RuntimeError):
    pass


def search_repositories(
    queries: Iterable[str],
    *,
    per_page: int = 50,
    token: str | None = None,
    pause_seconds: float = 6.2,
) -> list[Repository]:
    token = token or os.getenv("GITHUB_TOKEN")
    seen: set[str] = set()
    repos: list[Repository] = []
    query_list = list(queries)

    for index, query in enumerate(query_list):
        payload = _request_json(
            "/search/repositories",
            {
                "q": query,
                "sort": "stars",
                "order": "desc",
                "per_page": str(per_page),
            },
            token=token,
        )
        for item in payload.get("items", []):
            full_name = item.get("full_name", "")
            if not full_name or full_name in seen:
                continue
            seen.add(full_name)
            repos.append(_repo_from_item(item, query))

        # Unauthenticated GitHub search is rate-limited to a small per-minute bucket.
        if token is None and index < len(query_list) - 1:
            time.sleep(pause_seconds)

    return repos


def fetch_repository(full_name: str, *, token: str | None = None) -> Repository:
    token = token or os.getenv("GITHUB_TOKEN")
    clean_name = full_name.strip().strip("/")
    if "/" not in clean_name:
        raise GitHubApiError("Repository must be in owner/name format.")
    owner, name = clean_name.split("/", 1)
    if not owner or not name:
        raise GitHubApiError("Repository must be in owner/name format.")
    payload = _request_json(
        f"/repos/{quote(owner, safe='')}/{quote(name, safe='')}",
        {},
        token=token,
    )
    return _repo_from_item(payload, f"manual:{payload.get('full_name', clean_name)}")


def _request_json(path: str, params: dict[str, str], *, token: str | None) -> dict:
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
        raise GitHubApiError(f"GitHub API returned {exc.code}: {body}") from exc
    except URLError as exc:
        raise GitHubApiError(f"GitHub API request failed: {exc}") from exc


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
