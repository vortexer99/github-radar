from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]


DEFAULT_QUERY_TEMPLATES = [
    "created:>{created_since} stars:>{min_stars}",
    "pushed:>{pushed_since} stars:>{min_stars}",
    "topic:ai pushed:>{pushed_since} stars:>{min_stars}",
    "topic:llm pushed:>{pushed_since} stars:>{min_stars}",
    "topic:developer-tools pushed:>{pushed_since} stars:>{min_stars}",
    "topic:security pushed:>{pushed_since} stars:>{min_stars}",
    "topic:database pushed:>{pushed_since} stars:>{min_stars}",
    "topic:cli pushed:>{pushed_since} stars:>{min_stars}",
]


@dataclass(frozen=True)
class Settings:
    project_root: Path
    db_path: Path
    report_dir: Path
    min_stars: int = 100
    per_page: int = 50
    created_within_days: int = 45
    pushed_within_days: int = 14
    exploration_ratio: float = 0.25
    languages: list[str] = field(default_factory=list)
    excluded_terms: list[str] = field(default_factory=list)
    query_templates: list[str] = field(default_factory=lambda: DEFAULT_QUERY_TEMPLATES.copy())

    def expanded_queries(self, now: datetime | None = None) -> list[str]:
        now = now or datetime.now(timezone.utc)
        created_since = (now - timedelta(days=self.created_within_days)).date().isoformat()
        pushed_since = (now - timedelta(days=self.pushed_within_days)).date().isoformat()
        queries = []
        for template in self.query_templates:
            query = template.format(
                created_since=created_since,
                pushed_since=pushed_since,
                min_stars=self.min_stars,
            )
            if self.languages:
                lang_terms = " ".join(f"language:{language}" for language in self.languages)
                query = f"{query} {lang_terms}"
            queries.append(query)
        return queries


def load_settings(config_path: str | Path | None = None) -> Settings:
    project_root = Path.cwd()
    path = Path(config_path) if config_path else project_root / "radar.toml"
    data: dict[str, Any] = {}
    if path.exists():
        if tomllib is None:
            raise RuntimeError("Python 3.10 needs a TOML parser. Use Python 3.11+ or install tomli.")
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        project_root = path.parent

    db_path = _resolve_path(project_root, data.get("db_path", "data/radar.db"))
    report_dir = _resolve_path(project_root, data.get("report_dir", "reports"))

    return Settings(
        project_root=project_root,
        db_path=db_path,
        report_dir=report_dir,
        min_stars=int(data.get("min_stars", 100)),
        per_page=int(data.get("per_page", 50)),
        created_within_days=int(data.get("created_within_days", 45)),
        pushed_within_days=int(data.get("pushed_within_days", 14)),
        exploration_ratio=float(data.get("exploration_ratio", 0.25)),
        languages=[str(item) for item in data.get("languages", [])],
        excluded_terms=[str(item).lower() for item in data.get("excluded_terms", [])],
        query_templates=[str(item) for item in data.get("query_templates", DEFAULT_QUERY_TEMPLATES)],
    )


def _resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path
