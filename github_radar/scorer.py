from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timezone

from . import db
from .models import Repository, ScoredRepository
from .profile import build_interest_weights, score_interest
from .settings import Settings


def score_repositories(
    conn: sqlite3.Connection,
    repos: list[Repository],
    settings: Settings,
) -> list[ScoredRepository]:
    weights = build_interest_weights(conn)
    scored = [_score_one(conn, repo, settings, weights) for repo in repos]
    scored.sort(key=lambda item: item.total_score, reverse=True)
    return assign_sections(scored, exploration_ratio=settings.exploration_ratio)


def score_all_repositories(
    conn: sqlite3.Connection,
    repos: list[Repository],
    settings: Settings,
) -> list[ScoredRepository]:
    weights = build_interest_weights(conn)
    scored = [_score_one(conn, repo, settings, weights) for repo in repos]
    scored.sort(key=lambda item: item.total_score, reverse=True)
    section_by_name = {
        item.repo.full_name: item.section
        for item in assign_sections(scored, exploration_ratio=settings.exploration_ratio)
    }
    return [
        ScoredRepository(
            repo=item.repo,
            total_score=item.total_score,
            heat_score=item.heat_score,
            growth_score=item.growth_score,
            recency_score=item.recency_score,
            interest_score=item.interest_score,
            star_delta=item.star_delta,
            reasons=item.reasons,
            section=section_by_name.get(item.repo.full_name, "other"),
        )
        for item in scored
    ]


def assign_sections(
    scored: list[ScoredRepository],
    *,
    personalized_count: int = 10,
    exploration_count: int = 10,
    other_count: int = 20,
    exploration_ratio: float = 0.25,
) -> list[ScoredRepository]:
    if not scored:
        return []

    positive_interest = [item for item in scored if item.interest_score > 0.05]
    personalized = positive_interest[:personalized_count]
    used = {item.repo.full_name for item in personalized}

    remaining = [item for item in scored if item.repo.full_name not in used]
    explore_target = max(exploration_count, int(len(scored) * exploration_ratio))
    explore_target = min(explore_target, exploration_count)
    exploration = sorted(
        remaining,
        key=lambda item: (item.recency_score + item.growth_score, item.heat_score),
        reverse=True,
    )[:explore_target]
    used.update(item.repo.full_name for item in exploration)

    other = [item for item in scored if item.repo.full_name not in used][:other_count]

    result: list[ScoredRepository] = []
    result.extend(_with_section(personalized, "personalized"))
    result.extend(_with_section(exploration, "exploration"))
    result.extend(_with_section(other, "other"))

    if not personalized:
        warmup = sorted(
            scored,
            key=lambda item: (
                _newness(item.repo.created_at),
                item.recency_score + item.growth_score,
                item.heat_score,
            ),
            reverse=True,
        )[: min(8, len(scored))]
        warmup_names = {item.repo.full_name for item in warmup}
        result = _with_section(warmup, "personalized") + [
            item for item in result if item.repo.full_name not in warmup_names
        ]
    return result


def _score_one(
    conn: sqlite3.Connection,
    repo: Repository,
    settings: Settings,
    weights: dict[str, float],
) -> ScoredRepository:
    heat_score = _log_scale(repo.stars, pivot=5000)
    star_delta = db.star_delta_since(conn, repo.full_name, days=7)
    growth_score = _log_scale(star_delta, pivot=800)
    recency_score = _recency(repo.pushed_at)
    newness_score = _newness(repo.created_at)
    interest_score, interest_reasons = score_interest(repo, weights)
    excluded_penalty = _excluded_penalty(repo, settings.excluded_terms)

    total = (
        heat_score * 0.24
        + growth_score * 0.22
        + recency_score * 0.14
        + newness_score * 0.14
        + ((interest_score + 1.0) / 2.0) * 0.26
        - excluded_penalty
    )

    reasons = []
    if repo.stars >= 10000:
        reasons.append(f"高热度：{repo.stars:,} stars")
    elif repo.stars >= 1000:
        reasons.append(f"已有关注：{repo.stars:,} stars")
    if star_delta > 0:
        reasons.append(f"近 7 天约 +{star_delta:,} stars")
    if recency_score > 0.7:
        reasons.append("近期仍活跃")
    if newness_score > 0.7:
        reasons.append("近期创建，适合观察早期趋势")
    reasons.extend(interest_reasons)

    return ScoredRepository(
        repo=repo,
        total_score=round(total, 4),
        heat_score=round(heat_score, 4),
        growth_score=round(growth_score, 4),
        recency_score=round(recency_score, 4),
        interest_score=round(interest_score, 4),
        star_delta=star_delta,
        reasons=reasons[:5],
    )


def _with_section(items: list[ScoredRepository], section: str) -> list[ScoredRepository]:
    return [
        ScoredRepository(
            repo=item.repo,
            total_score=item.total_score,
            heat_score=item.heat_score,
            growth_score=item.growth_score,
            recency_score=item.recency_score,
            interest_score=item.interest_score,
            star_delta=item.star_delta,
            reasons=item.reasons,
            section=section,
        )
        for item in items
    ]


def _log_scale(value: int, *, pivot: int) -> float:
    if value <= 0:
        return 0.0
    return min(1.0, math.log1p(value) / math.log1p(pivot))


def _recency(pushed_at: str) -> float:
    if not pushed_at:
        return 0.0
    try:
        pushed = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    days = max(0.0, (datetime.now(timezone.utc) - pushed).total_seconds() / 86400)
    return max(0.0, min(1.0, 1.0 - days / 30.0))


def _newness(created_at: str) -> float:
    if not created_at:
        return 0.0
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    days = max(0.0, (datetime.now(timezone.utc) - created).total_seconds() / 86400)
    return max(0.0, min(1.0, 1.0 - days / 60.0))


def _excluded_penalty(repo: Repository, excluded_terms: list[str]) -> float:
    if not excluded_terms:
        return 0.0
    haystack = " ".join(
        [repo.full_name, repo.description, repo.language, " ".join(repo.topics)]
    ).lower()
    matches = sum(1 for term in excluded_terms if term and term in haystack)
    return min(0.6, matches * 0.25)
