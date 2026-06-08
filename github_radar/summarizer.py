from __future__ import annotations

import re
import unicodedata

from .models import Repository


DOMAIN_HINTS = [
    ({"agent", "agents", "ai-agent", "ai-agents", "llm", "chatgpt", "claude"}, "AI Agent / LLM 工具"),
    ({"developer-tools", "devtools", "cli", "terminal", "coding-agents"}, "开发者工具"),
    ({"database", "dbms", "analytics", "data", "big-data"}, "数据与分析工具"),
    ({"security", "audit", "firewall", "auth", "authentication"}, "安全与访问控制工具"),
    ({"dashboard", "business-intelligence", "bi", "visualization"}, "BI / 可视化工具"),
    ({"automation", "workflow", "integration", "integrations"}, "自动化 / 工作流工具"),
    ({"macos", "ios", "swift", "menubar"}, "Apple 平台应用"),
    ({"kubernetes", "cloud-native", "observability", "monitoring"}, "云原生 / 运维工具"),
    ({"machine-learning", "deep-learning", "ml", "neural-network"}, "机器学习框架或工具"),
]


def summarize_repository(repo: Repository) -> str:
    description = _clean_text(repo.description)
    topic_text = _topic_phrase(repo.topics)
    domain = _domain(repo)
    language = repo.language or "未知语言"

    if description:
        summary = description
        if not _looks_chinese(summary):
            summary = f"{repo.full_name} 是一个 {domain}，主要用于 {summary[0].lower() + summary[1:]}"
        elif not summary.endswith(("。", ".", "！", "!")):
            summary += "。"
    else:
        summary = f"{repo.full_name} 是一个以 {language} 为主的 {domain}"
        if topic_text:
            summary += f"，聚焦 {topic_text}"
        summary += "。"

    return _trim(summary, 180)


def _domain(repo: Repository) -> str:
    terms = {topic.lower() for topic in repo.topics}
    terms.update(_words(repo.name))
    terms.update(_words(repo.description))
    for keywords, label in DOMAIN_HINTS:
        if terms & keywords:
            return label
    if repo.language:
        return f"{repo.language} 项目"
    return "开源项目"


def _topic_phrase(topics: list[str]) -> str:
    clean = [topic for topic in topics[:5] if topic]
    if not clean:
        return ""
    return "、".join(clean)


def _clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    text = "".join(ch for ch in text if unicodedata.category(ch) not in {"So", "Cs"})
    text = re.sub(r"^[:\-–—\s]+", "", text)
    return text


def _words(text: str) -> set[str]:
    return {word.lower() for word in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text or "")}


def _looks_chinese(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _trim(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip(" ,，;；") + "…"
