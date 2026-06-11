from __future__ import annotations

import math
import re
import sqlite3
from collections import Counter

from . import db
from .models import Repository


STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
    "your",
    "you",
}


def build_interest_weights(conn: sqlite3.Connection) -> dict[str, float]:
    repos = {repo.full_name: repo for repo in db.load_recent_repositories(conn, limit=1000)}
    weights: Counter[str] = Counter()

    latest_feedback = {}
    for item in db.load_feedback(conn):
        latest_feedback.setdefault(item.full_name, item)

    for item in latest_feedback.values():
        if not item.tags:
            continue
        repo = repos.get(item.full_name)
        if repo is None:
            continue
        signal = max(-2, min(2, item.signal))
        for token in extract_terms(repo):
            weights[token] += signal
        for tag in item.tags:
            weights[f"tag:{tag.lower()}"] += signal * 1.5

    for term, weight in db.load_profile_terms(conn).items():
        weights[term] += weight
        if not term.startswith(("language:", "topic:", "keyword:", "tag:")):
            weights[f"keyword:{term}"] += weight

    return {term: float(weight) for term, weight in weights.items() if abs(weight) >= 0.1}


def score_interest(repo: Repository, weights: dict[str, float]) -> tuple[float, list[str]]:
    if not weights:
        return 0.0, ["冷启动：先按热度和新鲜度探索"]

    terms = extract_terms(repo)
    raw = sum(weights.get(term, 0.0) for term in terms)
    matched = sorted(
        ((term, weights[term]) for term in terms if term in weights),
        key=lambda item: abs(item[1]),
        reverse=True,
    )

    score = math.tanh(raw / 6.0)
    reasons = [_human_reason(term, weight) for term, weight in matched[:3]]
    if not reasons:
        reasons = ["和已知偏好关联较弱，作为探索样本"]
    return score, reasons


def extract_terms(repo: Repository) -> set[str]:
    terms: set[str] = set()
    if repo.language:
        terms.add(f"language:{repo.language.lower()}")
    for topic in repo.topics:
        terms.add(f"topic:{topic.lower()}")
        terms.add(f"keyword:{topic.lower()}")

    text = " ".join([repo.name, repo.full_name, repo.description])
    for word in re.findall(r"[A-Za-z][A-Za-z0-9_\-]{2,}", text.lower()):
        word = word.replace("_", "-")
        if word not in STOP_WORDS:
            terms.add(f"keyword:{word}")
    return terms


def _human_reason(term: str, weight: float) -> str:
    label = term.split(":", 1)[1] if ":" in term else term
    direction = "匹配" if weight > 0 else "被降权"
    if term.startswith("language:"):
        return f"{direction}语言偏好：{label}"
    if term.startswith("topic:"):
        return f"{direction}主题偏好：{label}"
    if term.startswith("tag:"):
        return f"{direction}手动标签：{label}"
    return f"{direction}关键词：{label}"
