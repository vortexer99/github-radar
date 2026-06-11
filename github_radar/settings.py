from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import os
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
    github_token: str = ""

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

    load_project_env(project_root / ".env")
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
        github_token=os.getenv("GITHUB_TOKEN", ""),
    )


def _resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def load_project_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = _decode_env_value(value.strip())


def save_github_token(project_root: Path, token: str) -> None:
    env_path = project_root / ".env"
    existing: list[str] = []
    if env_path.exists():
        existing = env_path.read_text(encoding="utf-8").splitlines()

    token_line = f'GITHUB_TOKEN="{_escape_env_value(token.strip())}"'
    wrote_token = False
    lines: list[str] = []
    for line in existing:
        if line.strip().startswith("GITHUB_TOKEN="):
            if token.strip():
                lines.append(token_line)
            wrote_token = True
        else:
            lines.append(line)
    if not wrote_token and token.strip():
        lines.append(token_line)

    if lines:
        env_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    elif env_path.exists():
        env_path.unlink()

    if token.strip():
        os.environ["GITHUB_TOKEN"] = token.strip()
    else:
        os.environ.pop("GITHUB_TOKEN", None)


def _decode_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value.replace(r"\"", '"').replace(r"\\", "\\")


def _escape_env_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', r"\"")
