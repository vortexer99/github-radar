from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta, timezone

from .profile import build_interest_weights
from .settings import Settings, format_language_filter


MAX_PERSONALIZED_QUERIES = 8
MIN_PERSONALIZED_WEIGHT = 0.5
PERSONALIZED_TERM_LIMITS = {
    "topic": 5,
    "language": 2,
    "keyword": 2,
    "other": 1,
}
TERM_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]{1,48}$")
LANGUAGE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.+# -]{0,48}$")
SEARCH_STOP_WORDS = {
    "api",
    "application",
    "book",
    "built",
    "code",
    "coding",
    "engineering",
    "framework",
    "into",
    "list",
    "markdown",
    "mode",
    "modes",
    "paper",
    "pdf",
    "skill",
    "skills",
    "software",
    "through",
    "tool",
    "tools",
    "workspace",
}


def plan_collection_queries(
    settings: Settings,
    conn: sqlite3.Connection,
    now: datetime | None = None,
) -> list[str]:
    """Build the next collection batch from exploration plus learned interests."""
    now = now or datetime.now(timezone.utc)
    base_queries = settings.expanded_queries(now)
    if not settings.allow_interest_queries:
        return _dedupe(base_queries)

    broad_queries = [query for query in base_queries if not _is_topic_query(query)]
    configured_topic_queries = [query for query in base_queries if _is_topic_query(query)]
    personalized_queries = build_personalized_queries(settings, conn, now)

    if personalized_queries:
        return _dedupe(broad_queries + personalized_queries + configured_topic_queries)
    return _dedupe(base_queries)


def build_personalized_queries(
    settings: Settings,
    conn: sqlite3.Connection,
    now: datetime | None = None,
    *,
    limit: int = MAX_PERSONALIZED_QUERIES,
) -> list[str]:
    if not settings.allow_interest_queries:
        return []

    now = now or datetime.now(timezone.utc)
    weights = build_interest_weights(conn)
    positive_terms = sorted(
        ((term, weight) for term, weight in weights.items() if weight >= MIN_PERSONALIZED_WEIGHT),
        key=lambda item: (-item[1], _term_priority(item[0]), item[0]),
    )

    queries: list[str] = []
    selected_terms = _select_diverse_terms(positive_terms, limit=len(positive_terms))
    for term, _weight in selected_terms:
        query = _query_from_term(term, settings, now)
        if query:
            queries.append(query)
        if len(_dedupe(queries)) >= limit:
            break
    return _dedupe(queries)[:limit]


def _query_from_term(term: str, settings: Settings, now: datetime | None) -> str:
    pushed_since = _pushed_since(settings, now)
    stars = max(0, int(settings.min_stars))

    if term.startswith("topic:"):
        value = _clean_topic_value(term.removeprefix("topic:"))
        query = f"topic:{value} pushed:>{pushed_since} stars:>{stars}" if value else ""
        return _with_collection_constraints(query, settings)

    if term.startswith("language:"):
        value = _clean_language_value(term.removeprefix("language:"))
        language = format_language_filter(value)
        query = f"{language} pushed:>{pushed_since} stars:>{stars}" if language else ""
        return _with_collection_constraints(query, settings)

    if term.startswith("keyword:"):
        value = _clean_keyword_value(term.removeprefix("keyword:"))
        query = f"{value} pushed:>{pushed_since} stars:>{stars}" if value else ""
        return _with_collection_constraints(query, settings)

    if term.startswith("tag:"):
        return ""

    value = _clean_keyword_value(term)
    query = f"{value} pushed:>{pushed_since} stars:>{stars}" if value else ""
    return _with_collection_constraints(query, settings)


def _pushed_since(settings: Settings, now: datetime | None) -> str:
    now = now or datetime.now(timezone.utc)
    return (now - timedelta(days=settings.pushed_within_days)).date().isoformat()


def _clean_search_value(value: str) -> str:
    value = value.strip().lower()
    return value if TERM_PATTERN.fullmatch(value) else ""


def _clean_language_value(value: str) -> str:
    value = " ".join(value.strip().lower().split())
    return value if LANGUAGE_PATTERN.fullmatch(value) else ""


def _clean_keyword_value(value: str) -> str:
    value = _clean_search_value(value)
    if not value or value in SEARCH_STOP_WORDS:
        return ""
    if "-" not in value and len(value) < 6:
        return ""
    return value


def _with_collection_constraints(query: str, settings: Settings) -> str:
    if not query or not settings.languages:
        return query
    query_lower = query.lower()
    language_terms = [
        term for language in settings.languages if (term := format_language_filter(language))
        and term.lower() not in query_lower
    ]
    if not language_terms:
        return query
    return f"{query} {' '.join(language_terms)}"


def _select_diverse_terms(
    weighted_terms: list[tuple[str, float]],
    *,
    limit: int,
) -> list[tuple[str, float]]:
    selected: list[tuple[str, float]] = []
    counts: dict[str, int] = {}
    concepts: set[str] = set()
    deferred: list[tuple[str, float]] = []

    for term, weight in weighted_terms:
        kind = _term_kind(term)
        concept = _term_concept(term)
        if concept and concept in concepts:
            continue
        quota = PERSONALIZED_TERM_LIMITS.get(kind, PERSONALIZED_TERM_LIMITS["other"])
        if counts.get(kind, 0) >= quota:
            deferred.append((term, weight))
            continue
        selected.append((term, weight))
        counts[kind] = counts.get(kind, 0) + 1
        if concept:
            concepts.add(concept)
        if len(selected) >= limit:
            return selected

    for term, weight in deferred:
        concept = _term_concept(term)
        if concept and concept in concepts:
            continue
        selected.append((term, weight))
        if concept:
            concepts.add(concept)
        if len(selected) >= limit:
            break
    return selected


def _clean_topic_value(value: str) -> str:
    value = _clean_search_value(value)
    if not value or value in SEARCH_STOP_WORDS:
        return ""
    return value


def _term_priority(term: str) -> int:
    if term.startswith("topic:"):
        return 0
    if term.startswith("language:"):
        return 1
    if term.startswith("keyword:"):
        return 2
    if term.startswith("tag:"):
        return 4
    return 3


def _term_kind(term: str) -> str:
    prefix, separator, _value = term.partition(":")
    if separator == ":" and prefix in PERSONALIZED_TERM_LIMITS:
        return prefix
    return "other"


def _term_concept(term: str) -> str:
    prefix, separator, value = term.partition(":")
    if separator != ":" or not value:
        return ""
    if prefix in {"language", "topic", "keyword"}:
        return f"search:{value.lower()}"
    return f"{prefix}:{value.lower()}"


def _is_topic_query(query: str) -> bool:
    return query.lstrip().startswith("topic:")


def _dedupe(queries: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for query in queries:
        normalized = " ".join(query.split())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result
