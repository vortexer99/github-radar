from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Repository:
    full_name: str
    html_url: str
    description: str
    language: str
    stars: int
    forks: int
    watchers: int
    open_issues: int
    topics: list[str] = field(default_factory=list)
    created_at: str = ""
    pushed_at: str = ""
    first_seen_at: str = ""
    last_seen_at: str = ""
    owner: str = ""
    name: str = ""
    query: str = ""


@dataclass(frozen=True)
class ScoredRepository:
    repo: Repository
    total_score: float
    heat_score: float
    growth_score: float
    recency_score: float
    interest_score: float
    star_delta: int
    reasons: list[str]
    section: str = "other"


@dataclass(frozen=True)
class Feedback:
    full_name: str
    signal: int
    note: str
    tags: list[str]
    created_at: datetime
