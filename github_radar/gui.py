from __future__ import annotations

import subprocess
import sys
import webbrowser
import random
from datetime import datetime
from html import escape
from pathlib import Path

from . import db
from .models import ScoredRepository
from .scorer import score_all_repositories
from .settings import load_settings
from .summarizer import summarize_repository

try:
    from PySide6.QtCore import Qt, QUrl
    from PySide6.QtGui import QAction, QBrush, QColor, QDesktopServices
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QSplitter,
        QStatusBar,
        QTextBrowser,
        QToolBar,
        QVBoxLayout,
        QWidget,
    )
except ModuleNotFoundError as exc:  # pragma: no cover
    raise SystemExit("缺少 PySide6。请先运行：python -m pip install PySide6") from exc


SECTION_LABELS = {
    "all": "全部",
    "personalized": "你可能感兴趣",
    "exploration": "探索推荐",
    "other": "其他热门",
}

FEEDBACK_LABELS = {
    "liked": "喜欢",
    "saved": "收藏",
    "read": "已阅",
    "disliked": "不感兴趣",
    "hidden": "少看这类",
}

FEEDBACK_FILTERS = {
    "all": "全部标记",
    "unmarked": "未标记",
    **FEEDBACK_LABELS,
}

FEEDBACK_COLORS = {
    "liked": ("#e9f6ef", "#176049"),
    "saved": ("#fff4d8", "#7a4e00"),
    "read": ("#eef2f7", "#4b5563"),
    "disliked": ("#fdecec", "#8f2f3f"),
    "hidden": ("#f4eefd", "#5b3b8c"),
}

SORT_OPTIONS = {
    "score_desc": "推荐分最高",
    "last_seen_desc": "最后采集：新到旧",
    "last_seen_asc": "最后采集：旧到新",
    "first_seen_desc": "首次入库：新到旧",
    "first_seen_asc": "首次入库：旧到新",
    "pushed_desc": "GitHub 更新：新到旧",
    "stars_desc": "Stars 最多",
}


class RadarReader(QMainWindow):
    def __init__(self, config_path: str | Path = "radar.toml") -> None:
        super().__init__()
        self.settings = load_settings(config_path)
        self.conn = db.connect(self.settings.db_path)
        db.init_db(self.conn)
        self.scored: list[ScoredRepository] = []
        self.filtered: list[ScoredRepository] = []
        self.feedback_by_repo: dict[str, str] = {}
        self.current: ScoredRepository | None = None

        self.setWindowTitle("GitHub Radar 阅读器")
        self.resize(1180, 760)
        self._build_ui()
        self.reload_data()

    def _build_ui(self) -> None:
        toolbar = QToolBar("工具")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        refresh_action = QAction("刷新数据", self)
        refresh_action.triggered.connect(self.reload_data)
        toolbar.addAction(refresh_action)

        collect_action = QAction("采集并刷新", self)
        collect_action.triggered.connect(self.collect_and_reload)
        toolbar.addAction(collect_action)

        next_action = QAction("下一条", self)
        next_action.setShortcut("Ctrl+N")
        next_action.triggered.connect(self.next_item)
        toolbar.addAction(next_action)

        random_action = QAction("随便看看", self)
        random_action.setShortcut("Ctrl+R")
        random_action.triggered.connect(self.random_item)
        toolbar.addAction(random_action)

        self.status = QStatusBar()
        self.setStatusBar(self.status)

        root = QSplitter(Qt.Horizontal)
        root.setChildrenCollapsible(False)
        self.setCentralWidget(root)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(8)

        left_layout.addWidget(QLabel("筛选"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索名称、简介、语言、topics")
        self.search.textChanged.connect(lambda *_args: self.apply_filters())
        left_layout.addWidget(self.search)

        self.section_filter = QComboBox()
        for key, label in SECTION_LABELS.items():
            self.section_filter.addItem(label, key)
        self.section_filter.currentIndexChanged.connect(lambda *_args: self.apply_filters())
        left_layout.addWidget(self.section_filter)

        self.language_filter = QComboBox()
        self.language_filter.currentIndexChanged.connect(lambda *_args: self.apply_filters())
        left_layout.addWidget(self.language_filter)

        self.feedback_filter = QComboBox()
        for key, label in FEEDBACK_FILTERS.items():
            self.feedback_filter.addItem(label, key)
        self.feedback_filter.currentIndexChanged.connect(self.feedback_filter_changed)
        left_layout.addWidget(self.feedback_filter)

        self.sort_filter = QComboBox()
        for key, label in SORT_OPTIONS.items():
            self.sort_filter.addItem(label, key)
        self.sort_filter.currentIndexChanged.connect(lambda *_args: self.apply_filters())
        left_layout.addWidget(self.sort_filter)

        self.only_unmarked = QCheckBox("只看未标记")
        self.only_unmarked.stateChanged.connect(self.toggle_unmarked_filter)
        left_layout.addWidget(self.only_unmarked)

        self.repo_list = QListWidget()
        self.repo_list.currentRowChanged.connect(self.show_current)
        left_layout.addWidget(self.repo_list, 1)
        root.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 10, 12, 10)

        self.title = QLabel("选择一个项目")
        self.title.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.title.setStyleSheet("font-size: 20px; font-weight: 600;")
        right_layout.addWidget(self.title)

        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(True)
        right_layout.addWidget(self.detail, 1)

        buttons = QHBoxLayout()
        self.auto_next = QCheckBox("标记后自动下一条")
        self.auto_next.setChecked(True)
        buttons.addWidget(self.auto_next)

        self.next_button = QPushButton("下一条")
        self.next_button.clicked.connect(self.next_item)
        buttons.addWidget(self.next_button)

        for label, signal, tag in [
            ("喜欢", 1, "liked"),
            ("收藏", 2, "saved"),
            ("已阅", 0, "read"),
            ("不感兴趣", -1, "disliked"),
            ("少看这类", -2, "hidden"),
        ]:
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, s=signal, t=tag: self.record_feedback(s, t))
            buttons.addWidget(button)

        self.open_button = QPushButton("打开 GitHub")
        self.open_button.clicked.connect(self.open_current)
        buttons.addWidget(self.open_button)
        right_layout.addLayout(buttons)

        root.addWidget(right)
        root.setSizes([370, 810])

    def reload_data(self) -> None:
        repos = db.load_recent_repositories(self.conn, limit=500)
        self.scored = score_all_repositories(self.conn, repos, self.settings)
        self.feedback_by_repo = self._load_latest_feedback()
        self._populate_languages()
        self.apply_filters()
        self.status.showMessage(f"已载入 {len(self.scored)} 个项目", 5000)

    def collect_and_reload(self) -> None:
        self.status.showMessage("正在采集 GitHub 数据...")
        QApplication.processEvents()
        command = [
            sys.executable,
            "-m",
            "github_radar",
            "run",
            "--config",
            str(self.settings.project_root / "radar.toml"),
            "--limit",
            "300",
        ]
        try:
            subprocess.run(command, cwd=self.settings.project_root, check=True)
        except subprocess.CalledProcessError as exc:
            QMessageBox.warning(self, "采集失败", f"命令退出码：{exc.returncode}")
            return
        self.reload_data()

    def apply_filters(self, preferred_name: str | None = None, preferred_row: int | None = None) -> None:
        selected_name = preferred_name
        if selected_name is None:
            selected_name = self.current.repo.full_name if self.current else ""
        query = self.search.text().strip().lower()
        section = self.section_filter.currentData()
        language = self.language_filter.currentData() if self.language_filter.count() else "all"
        feedback = self.feedback_filter.currentData()
        sort_key = self.sort_filter.currentData()

        self.filtered = []
        for item in self.scored:
            repo = item.repo
            repo_feedback = self.feedback_by_repo.get(repo.full_name)
            if section != "all" and item.section != section:
                continue
            if language != "all" and (repo.language or "未知") != language:
                continue
            if feedback == "unmarked" and repo_feedback is not None:
                continue
            if feedback not in ("all", "unmarked") and repo_feedback != feedback:
                continue
            haystack = " ".join(
                [repo.full_name, repo.description, repo.language, " ".join(repo.topics)]
            ).lower()
            if query and query not in haystack:
                continue
            self.filtered.append(item)
        self._sort_filtered(sort_key)

        self.repo_list.blockSignals(True)
        self.repo_list.clear()
        selected_row = 0
        for index, item in enumerate(self.filtered):
            self.repo_list.addItem(self._list_item(item))
            if item.repo.full_name == selected_name:
                selected_row = index
        if preferred_row is not None:
            selected_row = max(0, min(preferred_row, len(self.filtered) - 1))
        self.repo_list.blockSignals(False)

        if self.filtered:
            self.repo_list.setCurrentRow(min(selected_row, len(self.filtered) - 1))
            self.show_current(self.repo_list.currentRow())
        else:
            self.current = None
            self.title.setText("没有匹配项目")
            self.detail.setHtml("<p>换一个筛选条件试试。</p>")

    def show_current(self, row: int) -> None:
        if row < 0 or row >= len(self.filtered):
            return
        self.current = self.filtered[row]
        repo = self.current.repo
        marker = self.feedback_by_repo.get(repo.full_name)
        suffix = f"（{FEEDBACK_LABELS[marker]}）" if marker else ""
        self.title.setText(f"{repo.full_name}{suffix}")
        self.detail.setHtml(self._detail_html(self.current))

    def record_feedback(self, signal: int, tag: str) -> None:
        if self.current is None:
            return
        repo = self.current.repo
        current_row = self.repo_list.currentRow()
        db.add_feedback(self.conn, [repo.full_name], signal=signal, tags=[tag])
        self.feedback_by_repo[repo.full_name] = tag
        self.status.showMessage(f"已标记为“{FEEDBACK_LABELS[tag]}”：{repo.full_name}", 5000)
        if self.auto_next.isChecked():
            self.apply_filters(preferred_row=current_row)
        else:
            self.apply_filters(preferred_name=repo.full_name)

    def next_item(self) -> None:
        if not self.filtered:
            return
        row = self.repo_list.currentRow()
        next_row = min(row + 1, len(self.filtered) - 1)
        if row == next_row:
            self.status.showMessage("已经是当前筛选结果的最后一条", 3000)
            return
        self.repo_list.setCurrentRow(next_row)

    def random_item(self) -> None:
        if not self.filtered:
            self.status.showMessage("当前筛选结果为空，没法随机选择", 3000)
            return
        if len(self.filtered) == 1:
            self.repo_list.setCurrentRow(0)
            self.status.showMessage("当前筛选结果只有一条", 3000)
            return
        current_row = self.repo_list.currentRow()
        choices = [index for index in range(len(self.filtered)) if index != current_row]
        row = random.choice(choices)
        self.repo_list.setCurrentRow(row)
        self.status.showMessage(f"随机选中：{self.filtered[row].repo.full_name}", 3000)

    def toggle_unmarked_filter(self, *_args) -> None:
        target = "unmarked" if self.only_unmarked.isChecked() else "all"
        index = self.feedback_filter.findData(target)
        if index >= 0 and self.feedback_filter.currentIndex() != index:
            self.feedback_filter.setCurrentIndex(index)
        else:
            self.apply_filters()

    def feedback_filter_changed(self, *_args) -> None:
        should_check = self.feedback_filter.currentData() == "unmarked"
        if self.only_unmarked.isChecked() != should_check:
            self.only_unmarked.blockSignals(True)
            self.only_unmarked.setChecked(should_check)
            self.only_unmarked.blockSignals(False)
        self.apply_filters()

    def open_current(self) -> None:
        if self.current is None:
            return
        url = self.current.repo.html_url
        if not QDesktopServices.openUrl(QUrl(url)):
            webbrowser.open(url)

    def _populate_languages(self) -> None:
        current = self.language_filter.currentData() if self.language_filter.count() else "all"
        languages = sorted({item.repo.language or "未知" for item in self.scored})
        self.language_filter.blockSignals(True)
        self.language_filter.clear()
        self.language_filter.addItem("所有语言", "all")
        for language in languages:
            self.language_filter.addItem(language, language)
        index = self.language_filter.findData(current)
        self.language_filter.setCurrentIndex(index if index >= 0 else 0)
        self.language_filter.blockSignals(False)

    def _load_latest_feedback(self) -> dict[str, str]:
        latest: dict[str, str] = {}
        for item in reversed(db.load_feedback(self.conn)):
            for tag in item.tags:
                if tag in FEEDBACK_LABELS:
                    latest[item.full_name] = tag
                    break
        return latest

    def _list_item(self, item: ScoredRepository) -> QListWidgetItem:
        repo = item.repo
        marker = self.feedback_by_repo.get(repo.full_name)
        suffix = f"（{FEEDBACK_LABELS[marker]}）" if marker else ""
        label = (
            f"{repo.full_name}{suffix}\n"
            f"{SECTION_LABELS.get(item.section, item.section)} · "
            f"{repo.language or '未知'} · {repo.stars:,} stars · "
            f"采集 {self._format_time(repo.last_seen_at)} · score {item.total_score:.2f}"
        )
        widget_item = QListWidgetItem(label)
        widget_item.setToolTip(repo.description or repo.full_name)
        if marker in FEEDBACK_COLORS:
            background, foreground = FEEDBACK_COLORS[marker]
            widget_item.setBackground(QBrush(QColor(background)))
            widget_item.setForeground(QBrush(QColor(foreground)))
        return widget_item

    def _detail_html(self, item: ScoredRepository) -> str:
        repo = item.repo
        marker = self.feedback_by_repo.get(repo.full_name)
        feedback = FEEDBACK_LABELS[marker] if marker else "未标记"
        summary = escape(summarize_repository(repo))
        topics = escape(", ".join(repo.topics) if repo.topics else "无")
        reasons = "<br>".join(f"- {escape(reason)}" for reason in item.reasons) or "综合热度较高"
        description = escape(repo.description or "暂无描述")
        full_name = escape(repo.full_name)
        language = escape(repo.language or "未知")
        return f"""
        <h2><a href="{escape(repo.html_url)}">{full_name}</a></h2>
        <h3>项目概述</h3>
        <p>{summary}</p>
        <h3>原始简介</h3>
        <p>{description}</p>
        <table>
          <tr><td><b>当前标记</b></td><td>{feedback}</td></tr>
          <tr><td><b>分区</b></td><td>{SECTION_LABELS.get(item.section, item.section)}</td></tr>
          <tr><td><b>语言</b></td><td>{language}</td></tr>
          <tr><td><b>Topics</b></td><td>{topics}</td></tr>
          <tr><td><b>Stars</b></td><td>{repo.stars:,}</td></tr>
          <tr><td><b>Forks</b></td><td>{repo.forks:,}</td></tr>
          <tr><td><b>近 7 天增长</b></td><td>约 +{item.star_delta:,} stars</td></tr>
          <tr><td><b>首次入库</b></td><td>{escape(self._format_time(repo.first_seen_at))}</td></tr>
          <tr><td><b>最后采集</b></td><td>{escape(self._format_time(repo.last_seen_at))}</td></tr>
          <tr><td><b>创建时间</b></td><td>{repo.created_at}</td></tr>
          <tr><td><b>更新时间</b></td><td>{repo.pushed_at}</td></tr>
        </table>
        <h3>推荐理由</h3>
        <p>{reasons}</p>
        <h3>评分</h3>
        <p>
          综合 {item.total_score:.2f}，
          热度 {item.heat_score:.2f}，
          增长 {item.growth_score:.2f}，
          新鲜度 {item.recency_score:.2f}，
          兴趣 {item.interest_score:.2f}
        </p>
        """

    def _sort_filtered(self, sort_key: str) -> None:
        if sort_key == "last_seen_desc":
            self.filtered.sort(key=lambda item: self._time_sort_key(item.repo.last_seen_at), reverse=True)
        elif sort_key == "last_seen_asc":
            self.filtered.sort(key=lambda item: self._time_sort_key(item.repo.last_seen_at))
        elif sort_key == "first_seen_desc":
            self.filtered.sort(key=lambda item: self._time_sort_key(item.repo.first_seen_at), reverse=True)
        elif sort_key == "first_seen_asc":
            self.filtered.sort(key=lambda item: self._time_sort_key(item.repo.first_seen_at))
        elif sort_key == "pushed_desc":
            self.filtered.sort(key=lambda item: self._time_sort_key(item.repo.pushed_at), reverse=True)
        elif sort_key == "stars_desc":
            self.filtered.sort(key=lambda item: item.repo.stars, reverse=True)
        else:
            self.filtered.sort(key=lambda item: item.total_score, reverse=True)

    @staticmethod
    def _time_sort_key(value: str) -> float:
        if not value:
            return 0.0
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0

    @staticmethod
    def _format_time(value: str) -> str:
        if not value:
            return "未知"
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
        return parsed.strftime("%Y-%m-%d %H:%M")


def main(argv: list[str] | None = None) -> int:
    app = QApplication(argv or sys.argv)
    window = RadarReader()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
