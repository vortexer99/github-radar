from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from . import db
from .models import ScoredRepository
from .scorer import score_repositories
from .profile import build_interest_weights, score_interest
from .settings import load_settings
from .summarizer import summarize_repository


FEEDBACK_LABELS = {
    "liked": "喜欢",
    "saved": "收藏",
    "read": "已阅",
    "disliked": "不感兴趣",
    "hidden": "少看这类",
}

FEEDBACK_SIGNALS = {
    "liked": 1,
    "saved": 2,
    "read": 0,
    "disliked": -1,
    "hidden": -2,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export/import data for the static H5 reader.")
    parser.add_argument("--config", default="radar.toml")
    parser.add_argument("--out", default="web/radar.json")
    parser.add_argument("--feedback", default=None, help="Optional feedback JSON exported by reader.html.")
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args(argv)

    settings = load_settings(args.config)
    conn = db.connect(settings.db_path)
    db.init_db(conn)

    if args.feedback:
        import_feedback(conn, Path(args.feedback))

    repos = db.load_recent_repositories(conn, limit=args.limit)
    highlighted = score_repositories(conn, repos, settings)
    sections = {item.repo.full_name: item.section for item in highlighted}
    scored = score_all_for_export(conn, repos, settings, sections)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "feedback_labels": FEEDBACK_LABELS,
        "items": [serialize_item(item, latest_feedback(conn).get(item.repo.full_name)) for item in scored],
    }

    out_path = settings.project_root / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out_path)
    return 0


def import_feedback(conn, path: Path) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    feedback = payload.get("feedback", {})
    count = 0
    for full_name, tag in feedback.items():
        if tag not in FEEDBACK_SIGNALS:
            continue
        count += db.add_feedback(conn, [full_name], signal=FEEDBACK_SIGNALS[tag], tags=[tag])
    return count


def latest_feedback(conn) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in reversed(db.load_feedback(conn)):
        for tag in item.tags:
            if tag in FEEDBACK_LABELS:
                result[item.full_name] = tag
                break
    return result


def serialize_item(item: ScoredRepository, feedback: str | None) -> dict[str, Any]:
    repo = item.repo
    return {
        "full_name": repo.full_name,
        "html_url": repo.html_url,
        "description": repo.description,
        "summary": summarize_repository(repo),
        "language": repo.language or "未知",
        "stars": repo.stars,
        "forks": repo.forks,
        "watchers": repo.watchers,
        "open_issues": repo.open_issues,
        "topics": repo.topics,
        "created_at": repo.created_at,
        "pushed_at": repo.pushed_at,
        "section": item.section,
        "score": item.total_score,
        "heat_score": item.heat_score,
        "growth_score": item.growth_score,
        "recency_score": item.recency_score,
        "interest_score": item.interest_score,
        "star_delta": item.star_delta,
        "reasons": item.reasons,
        "feedback": feedback,
    }


def score_all_for_export(conn, repos, settings, sections: dict[str, str]) -> list[ScoredRepository]:
    weights = build_interest_weights(conn)
    items = []
    for repo in repos:
        heat_score = min(1.0, _log_scale(repo.stars, 5000))
        star_delta = db.star_delta_since(conn, repo.full_name, days=7)
        growth_score = min(1.0, _log_scale(star_delta, 800))
        recency_score = _recency(repo.pushed_at)
        interest_score, reasons = score_interest(repo, weights)
        total = (
            heat_score * 0.24
            + growth_score * 0.22
            + recency_score * 0.14
            + ((interest_score + 1.0) / 2.0) * 0.26
        )
        items.append(
            ScoredRepository(
                repo=repo,
                total_score=round(total, 4),
                heat_score=round(heat_score, 4),
                growth_score=round(growth_score, 4),
                recency_score=round(recency_score, 4),
                interest_score=round(interest_score, 4),
                star_delta=star_delta,
                reasons=reasons[:5],
                section=sections.get(repo.full_name, "other"),
            )
        )
    return sorted(items, key=lambda item: item.total_score, reverse=True)


def _log_scale(value: int, pivot: int) -> float:
    import math

    if value <= 0:
        return 0.0
    return math.log1p(value) / math.log1p(pivot)


def _recency(pushed_at: str) -> float:
    from datetime import datetime, timezone

    if not pushed_at:
        return 0.0
    try:
        pushed = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    days = max(0.0, (datetime.now(timezone.utc) - pushed).total_seconds() / 86400)
    return max(0.0, min(1.0, 1.0 - days / 30.0))


if __name__ == "__main__":
    raise SystemExit(main())
