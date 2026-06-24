from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import re
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]


DEFAULT_QUERY_TEMPLATES = [
    "created:>{created_since} stars:>{min_stars}",
    "pushed:>{pushed_since} stars:>{min_stars}",
    "forks:>50 pushed:>{pushed_since} stars:>{min_stars}",
    "created:>{created_since} forks:>20 stars:>{min_stars}",
    "archived:false pushed:>{pushed_since} stars:>{min_stars}",
]
DEFAULT_TOPICS: list[str] = []
CONFIG_SCHEMA_VERSION = 2
SIMPLE_LANGUAGE_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


DEFAULT_CONFIG_TEXT = """# GitHub Radar local configuration.
# GitHub Token can be configured in the reader settings, gh, GH_TOKEN, or GITHUB_TOKEN.

config_schema_version = 2
db_path = "data/radar.db"
report_dir = "reports"
min_stars = 100
per_page = 50
created_within_days = 45
pushed_within_days = 14
allow_interest_queries = true

languages = []
excluded_terms = []
topics = []

query_templates = [
  "created:>{created_since} stars:>{min_stars}",
  "pushed:>{pushed_since} stars:>{min_stars}",
  "forks:>50 pushed:>{pushed_since} stars:>{min_stars}",
  "created:>{created_since} forks:>20 stars:>{min_stars}",
  "archived:false pushed:>{pushed_since} stars:>{min_stars}"
]
"""


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
    allow_interest_queries: bool = True
    languages: list[str] = field(default_factory=list)
    excluded_terms: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=lambda: DEFAULT_TOPICS.copy())
    query_templates: list[str] = field(default_factory=lambda: DEFAULT_QUERY_TEMPLATES.copy())
    github_token: str = ""
    config_schema_version: int = 0

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
                lang_terms = " ".join(
                    term for language in self.languages if (term := format_language_filter(language))
                )
                if lang_terms:
                    query = f"{query} {lang_terms}"
            queries.append(query)
        return queries


def load_settings(config_path: str | Path | None = None) -> Settings:
    project_root = Path.cwd()
    if config_path:
        path = Path(config_path)
        if not path.is_absolute():
            path = project_root / path
        project_root = path.parent
    else:
        path = project_root / "radar.toml"
    ensure_default_config(path)

    data: dict[str, Any] = {}
    if path.exists():
        if tomllib is None:
            raise RuntimeError("Python 3.10 needs a TOML parser. Use Python 3.11+ or install tomli.")
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        project_root = path.parent

    project_env = load_project_env(project_root / ".env")
    db_path = _resolve_path(project_root, data.get("db_path", "data/radar.db"))
    report_dir = _resolve_path(project_root, data.get("report_dir", "reports"))
    topics = [str(item).lower() for item in data.get("topics", [])]
    query_templates = [str(item) for item in data.get("query_templates", [])]
    if not query_templates:
        query_templates = query_templates_from_topics(topics or DEFAULT_TOPICS)
    if not topics:
        topics = topics_from_query_templates(query_templates)

    return Settings(
        project_root=project_root,
        db_path=db_path,
        report_dir=report_dir,
        min_stars=int(data.get("min_stars", 100)),
        per_page=int(data.get("per_page", 50)),
        created_within_days=int(data.get("created_within_days", 45)),
        pushed_within_days=int(data.get("pushed_within_days", 14)),
        exploration_ratio=float(data.get("exploration_ratio", 0.25)),
        allow_interest_queries=bool(data.get("allow_interest_queries", True)),
        languages=[str(item) for item in data.get("languages", [])],
        excluded_terms=[str(item).lower() for item in data.get("excluded_terms", [])],
        topics=topics,
        query_templates=query_templates,
        github_token=project_env.get("GITHUB_TOKEN", ""),
        config_schema_version=int(data.get("config_schema_version", 0)),
    )


def ensure_default_config(path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DEFAULT_CONFIG_TEXT, encoding="utf-8")


def _resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def load_project_env(path: Path) -> dict[str, str]:
    loaded: dict[str, str] = {}
    if not path.exists():
        return loaded
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        decoded_value = _decode_env_value(value.strip())
        loaded[key] = decoded_value
        if key not in os.environ:
            os.environ[key] = decoded_value
    return loaded


def save_github_token(project_root: Path, token: str) -> None:
    env_path = project_root / ".env"
    existing: list[str] = []
    if env_path.exists():
        existing = env_path.read_text(encoding="utf-8").splitlines()

    previous_token = ""
    token_line = f'GITHUB_TOKEN="{_escape_env_value(token.strip())}"'
    wrote_token = False
    lines: list[str] = []
    for line in existing:
        if line.strip().startswith("GITHUB_TOKEN="):
            _, old_value = line.split("=", 1)
            previous_token = _decode_env_value(old_value.strip())
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
    elif previous_token and os.getenv("GITHUB_TOKEN") == previous_token:
        os.environ.pop("GITHUB_TOKEN", None)


def save_collection_settings(
    settings: Settings,
    *,
    min_stars: int,
    per_page: int,
    created_within_days: int,
    pushed_within_days: int,
    exploration_ratio: float,
    allow_interest_queries: bool,
    languages: list[str],
    excluded_terms: list[str],
    topics: list[str],
    query_templates: list[str],
) -> None:
    config_path = settings.project_root / "radar.toml"
    lines = [
        "# GitHub Radar local configuration.",
        "# GitHub Token can be configured in the reader settings, gh, GH_TOKEN, or GITHUB_TOKEN.",
        "",
        f"config_schema_version = {CONFIG_SCHEMA_VERSION}",
        f'db_path = "{_toml_escape(_relative_or_absolute(settings.project_root, settings.db_path))}"',
        f'report_dir = "{_toml_escape(_relative_or_absolute(settings.project_root, settings.report_dir))}"',
        f"min_stars = {max(0, int(min_stars))}",
        f"per_page = {max(1, min(100, int(per_page)))}",
        f"created_within_days = {max(1, int(created_within_days))}",
        f"pushed_within_days = {max(1, int(pushed_within_days))}",
        f"allow_interest_queries = {_toml_bool(allow_interest_queries)}",
        "",
        f"languages = {_toml_string_list(languages)}",
        f"excluded_terms = {_toml_string_list(excluded_terms)}",
        f"topics = {_toml_string_list(topics)}",
        "",
        "query_templates = [",
    ]
    lines.extend(f'  "{_toml_escape(template)}",' for template in query_templates)
    lines.extend(["]", ""])
    config_path.write_text("\n".join(lines), encoding="utf-8")


def needs_legacy_topic_template_notice(settings: Settings) -> bool:
    return (
        settings.config_schema_version < CONFIG_SCHEMA_VERSION
        and any(template.strip().startswith("topic:") for template in settings.query_templates)
    )


def acknowledge_config_schema_version(settings: Settings) -> None:
    config_path = settings.project_root / "radar.toml"
    ensure_default_config(config_path)
    lines = config_path.read_text(encoding="utf-8").splitlines()
    marker = f"config_schema_version = {CONFIG_SCHEMA_VERSION}"
    for index, line in enumerate(lines):
        if line.strip().startswith("config_schema_version"):
            lines[index] = marker
            break
    else:
        insert_at = 0
        while insert_at < len(lines) and lines[insert_at].strip().startswith("#"):
            insert_at += 1
        while insert_at < len(lines) and not lines[insert_at].strip():
            insert_at += 1
        lines.insert(insert_at, marker)
    config_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def topics_from_query_templates(query_templates: list[str]) -> list[str]:
    topics: list[str] = []
    for template in query_templates:
        stripped = template.strip()
        if not stripped.startswith("topic:"):
            continue
        topic = stripped[len("topic:") :].split(maxsplit=1)[0].strip()
        if topic and topic not in topics:
            topics.append(topic)
    return topics


def query_templates_from_topics(topics: list[str]) -> list[str]:
    templates = [
        "created:>{created_since} stars:>{min_stars}",
        "pushed:>{pushed_since} stars:>{min_stars}",
        "forks:>50 pushed:>{pushed_since} stars:>{min_stars}",
        "created:>{created_since} forks:>20 stars:>{min_stars}",
        "archived:false pushed:>{pushed_since} stars:>{min_stars}",
    ]
    templates.extend(f"topic:{topic} pushed:>{{pushed_since}} stars:>{{min_stars}}" for topic in topics)
    return templates


def format_language_filter(language: str) -> str:
    value = " ".join(str(language).strip().split())
    if not value:
        return ""
    if SIMPLE_LANGUAGE_PATTERN.fullmatch(value):
        return f"language:{value}"
    escaped = value.replace("\\", "\\\\").replace('"', r"\"")
    return f'language:"{escaped}"'


def _decode_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value.replace(r"\"", '"').replace(r"\\", "\\")


def _escape_env_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', r"\"")


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', r"\"")


def _toml_string_list(values: list[str]) -> str:
    cleaned = [value.strip() for value in values if value.strip()]
    return "[" + ", ".join(f'"{_toml_escape(value)}"' for value in cleaned) + "]"


def _toml_bool(value: bool) -> str:
    return "true" if value else "false"


def _relative_or_absolute(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
