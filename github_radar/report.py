from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .models import ScoredRepository
from .summarizer import summarize_repository


SECTION_TITLES = {
    "personalized": "你可能感兴趣",
    "exploration": "探索推荐",
    "other": "其他热门项目",
}


def write_markdown_report(
    scored: list[ScoredRepository],
    report_dir: Path,
    *,
    title: str = "GitHub 热门项目雷达",
) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    path = report_dir / f"github-radar-{now:%Y-%m-%d-%H%M}.md"
    path.write_text(render_markdown(scored, title=title, generated_at=now), encoding="utf-8")
    return path


def render_markdown(
    scored: list[ScoredRepository],
    *,
    title: str,
    generated_at: datetime,
) -> str:
    sections: dict[str, list[ScoredRepository]] = defaultdict(list)
    for item in scored:
        sections[item.section].append(item)

    lines = [
        f"# {title}",
        "",
        f"生成时间：{generated_at:%Y-%m-%d %H:%M}",
        "",
        "反馈格式示例：",
        "",
        "```text",
        "python -m github_radar feedback --like owner/repo --dislike owner/other --more-topic ai cli --less-topic crypto",
        "```",
        "",
    ]

    for section in ["personalized", "exploration", "other"]:
        items = sections.get(section, [])
        if not items:
            continue
        lines.extend([f"## {SECTION_TITLES[section]}", ""])
        if section == "personalized" and all(item.interest_score == 0 for item in items):
            lines.extend(
                [
                    "> 目前还在冷启动阶段。这一栏先放综合分高的项目；你反馈几次后会真正个性化。",
                    "",
                ]
            )
        for index, item in enumerate(items, start=1):
            lines.extend(_render_item(index, item))
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _render_item(index: int, item: ScoredRepository) -> list[str]:
    repo = item.repo
    topics = ", ".join(repo.topics[:8]) if repo.topics else "无"
    language = repo.language or "未知"
    description = repo.description or "暂无描述"
    summary = summarize_repository(repo)
    reasons = "；".join(item.reasons) if item.reasons else "综合热度较高"
    risks = "；".join(_risk_notes(item)) or "未发现明显噪声信号"

    return [
        f"### {index}. [{repo.full_name}]({repo.html_url})",
        "",
        f"- 概述：{summary}",
        f"- 简介：{description}",
        f"- 分类：{language} / {topics}",
        f"- 热度：{repo.stars:,} stars，{repo.forks:,} forks，近 7 天约 +{item.star_delta:,} stars",
        f"- 入库：首次 {_format_time(repo.first_seen_at)}，最后采集 {_format_time(repo.last_seen_at)}",
        f"- 推荐理由：{reasons}",
        f"- 风险/噪声：{risks}",
        f"- 分数：综合 {item.total_score:.2f}，热度 {item.heat_score:.2f}，增长 {item.growth_score:.2f}，兴趣 {item.interest_score:.2f}",
    ]


def _risk_notes(item: ScoredRepository) -> list[str]:
    repo = item.repo
    notes: list[str] = []
    age_days = _age_days(repo.created_at)
    if age_days is not None and age_days < 90 and repo.stars >= 20000:
        notes.append("新仓库超高 star，建议核验传播来源")
    if not repo.topics:
        notes.append("缺少 topics，分类可信度较低")
    if len(repo.description.strip()) < 24:
        notes.append("简介较短，需打开仓库进一步判断")
    if repo.stars >= 1000 and repo.forks / max(repo.stars, 1) < 0.015:
        notes.append("fork/star 比较低，可能偏展示或短期围观")
    if item.star_delta == 0:
        notes.append("本地还没有历史快照，增长数据待后续校准")
    return notes[:3]


def _age_days(created_at: str) -> float | None:
    if not created_at:
        return None
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0.0, (datetime.now(timezone.utc) - created).total_seconds() / 86400)


def _format_time(value: str) -> str:
    if not value:
        return "未知"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M")
