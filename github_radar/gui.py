from __future__ import annotations

import subprocess
import sys
import webbrowser
import random
from datetime import datetime
from html import escape
from pathlib import Path
import re

from . import db
from . import __version__
from .github_api import GitHubApiError, fetch_repository, search_repositories
from .models import Repository, ScoredRepository
from .scorer import score_all_repositories
from .settings import load_settings, save_github_token
from .summarizer import summarize_repository

try:
    from PySide6.QtCore import QSize, QStringListModel, Qt, QUrl
    from PySide6.QtGui import QAction, QColor, QDesktopServices, QFont, QFontDatabase, QIcon, QPainter, QPen
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QCompleter,
        QDialog,
        QDialogButtonBox,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QInputDialog,
        QPlainTextEdit,
        QStyledItemDelegate,
        QStyle,
        QSplitter,
        QStatusBar,
        QTabWidget,
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


class RepoListDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        marker = index.data(Qt.UserRole) or ""
        selected = bool(option.state & QStyle.State_Selected)
        hover = bool(option.state & QStyle.State_MouseOver)
        background, foreground = FEEDBACK_COLORS.get(marker, ("#ffffff", "#1f2937"))
        border = "#e0e7f1"
        if marker:
            border = QColor(background).darker(112).name()
        if hover:
            border = "#9fc3f2"
        if selected:
            border = "#2563eb"

        rect = option.rect.adjusted(2, 2, -2, -2)
        painter.setPen(QPen(QColor(border), 1))
        painter.setBrush(QColor(background))
        painter.drawRoundedRect(rect, 7, 7)

        text_rect = rect.adjusted(12, 8, -12, -8)
        lines = (index.data(Qt.DisplayRole) or "").splitlines()
        title = lines[0] if lines else ""
        meta = lines[1] if len(lines) > 1 else ""

        title_font = QFont(option.font)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor("#0f172a" if selected else foreground))
        title_metrics = painter.fontMetrics()
        painter.drawText(
            text_rect,
            Qt.AlignLeft | Qt.AlignTop,
            title_metrics.elidedText(title, Qt.ElideRight, text_rect.width()),
        )

        meta_font = QFont(option.font)
        meta_font.setPointSize(max(8, meta_font.pointSize() - 1))
        painter.setFont(meta_font)
        painter.setPen(QColor("#475569" if not marker else foreground))
        meta_metrics = painter.fontMetrics()
        meta_rect = text_rect.adjusted(0, 25, 0, 0)
        painter.drawText(
            meta_rect,
            Qt.AlignLeft | Qt.AlignTop,
            meta_metrics.elidedText(meta, Qt.ElideRight, meta_rect.width()),
        )
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        return QSize(super().sizeHint(option, index).width(), 70)


class SettingsDialog(QDialog):
    def __init__(self, reader: "RadarReader") -> None:
        super().__init__(reader)
        self.reader = reader
        self.setWindowTitle("设置")
        self.resize(520, 360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        tabs = QTabWidget()
        tabs.addTab(self._github_tab(), "GitHub")
        tabs.addTab(self._about_tab(), "关于")
        layout.addWidget(tabs, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def github_token(self) -> str:
        return self.token_input.text().strip()

    def _github_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        self.token_input = QLineEdit()
        self.token_input.setEchoMode(QLineEdit.Password)
        self.token_input.setPlaceholderText("ghp_... 或 fine-grained token")
        self.token_input.setText(self.reader.settings.github_token)
        form.addRow("GitHub Token", self.token_input)
        layout.addLayout(form)

        hint = QLabel(
            "Token 会保存到项目根目录的 .env 文件，采集和导入仓库时自动使用。"
            "留空并保存可以清除当前项目 Token。"
        )
        hint.setWordWrap(True)
        hint.setObjectName("MutedText")
        layout.addWidget(hint)
        layout.addStretch(1)
        return tab

    def _about_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        icon_label = QLabel()
        icon_path = self.reader.settings.project_root / "assets" / "app-icon.png"
        if icon_path.exists():
            icon = QIcon(str(icon_path))
            icon_label.setPixmap(icon.pixmap(96, 96))
        icon_label.setAlignment(Qt.AlignHCenter)
        layout.addWidget(icon_label)

        stats = db.repository_stats(self.reader.conn)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        for label, value in [
            ("软件", "GitHub Radar 阅读器"),
            ("版本", __version__),
            ("GitHub", '<a href="https://github.com/vortexer99/github-radar">vortexer99/github-radar</a>'),
            ("项目目录", str(self.reader.settings.project_root)),
            ("数据库", str(self.reader.settings.db_path)),
            ("报告目录", str(self.reader.settings.report_dir)),
            ("仓库总数", str(stats["total_repositories"])),
            ("已标记仓库", str(stats["marked_repositories"])),
            ("已加标签仓库", str(stats.get("tagged_repositories", 0))),
            ("Python", sys.version.split()[0]),
        ]:
            value_label = QLabel(value)
            value_label.setOpenExternalLinks(True)
            value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            value_label.setWordWrap(True)
            form.addRow(label, value_label)
        layout.addLayout(form)
        layout.addStretch(1)
        return tab


class RefreshDataDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("刷新数据")
        self.resize(440, 190)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("刷新仓库数据")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        hint = QLabel("默认仅从本地数据库重新加载，速度更快且不会访问 GitHub。")
        hint.setObjectName("MutedText")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.fetch_from_github = QCheckBox("从 GitHub 获取最新数据后再刷新")
        self.fetch_from_github.setChecked(False)
        self.fetch_from_github.setToolTip("选中后会运行采集任务并更新本地数据库")
        layout.addWidget(self.fetch_from_github)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("刷新")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def should_fetch_from_github(self) -> bool:
        return self.fetch_from_github.isChecked()


class BatchImportDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("批量导入仓库")
        self.resize(560, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("每行输入一个 GitHub 仓库")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        self.repo_input = QPlainTextEdit()
        self.repo_input.setPlaceholderText(
            "owner/repo\nanother-owner/another-repo\nhttps://github.com/owner/repo"
        )
        layout.addWidget(self.repo_input, 1)

        self.tags_input = QLineEdit()
        self.tags_input.setPlaceholderText("可选：给本次导入的仓库统一添加标签，例如 ai, cli")
        layout.addWidget(self.tags_input)

        hint = QLabel("支持 owner/repo 或 GitHub 仓库 URL。空行会自动忽略。")
        hint.setObjectName("MutedText")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("导入")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def repo_names(self) -> list[str]:
        return _parse_repo_names(self.repo_input.toPlainText())

    def tags(self) -> list[str]:
        return _split_tags(self.tags_input.text())


class SearchResultWidget(QWidget):
    def __init__(self, repo: Repository) -> None:
        super().__init__()
        self.setObjectName("SearchResultRow")
        self.checkbox = QCheckBox()
        self.checkbox.setObjectName("SearchResultCheck")

        title = QLabel(repo.full_name)
        title.setObjectName("SearchResultTitle")
        title.setTextInteractionFlags(Qt.TextSelectableByMouse)

        topics = ", ".join(repo.topics[:5]) if repo.topics else "无 topics"
        meta = QLabel(f"{repo.stars:,} stars · {repo.language or '未知'} · {topics}")
        meta.setObjectName("SearchResultMeta")
        meta.setTextInteractionFlags(Qt.TextSelectableByMouse)

        description = QLabel(repo.description or "暂无描述")
        description.setObjectName("SearchResultDescription")
        description.setWordWrap(True)
        description.setTextInteractionFlags(Qt.TextSelectableByMouse)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        text_layout.addWidget(title)
        text_layout.addWidget(meta)
        text_layout.addWidget(description)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)
        layout.addWidget(self.checkbox, 0, Qt.AlignTop)
        layout.addLayout(text_layout, 1)

    def is_checked(self) -> bool:
        return self.checkbox.isChecked()

    def toggle_checked(self) -> None:
        self.checkbox.setChecked(not self.checkbox.isChecked())


class TopicImportDialog(QDialog):
    def __init__(self, reader: "RadarReader") -> None:
        super().__init__(reader)
        self.reader = reader
        self.results: list[Repository] = []
        self.setWindowTitle("搜索 Repo 导入")
        self.resize(760, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        search_row = QHBoxLayout()
        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("输入 topic 或关键词搜索 Repo，例如 ai、agent、developer-tools")
        self.query_input.returnPressed.connect(self.search)
        search_row.addWidget(self.query_input, 1)

        self.search_button = QPushButton("搜索")
        self.search_button.clicked.connect(self.search)
        search_row.addWidget(self.search_button)
        layout.addLayout(search_row)

        hint = QLabel("会优先按 GitHub topic 搜索 Repo；如果没有结果，再按关键词搜索。勾选结果后点击“导入选中”。")
        hint.setObjectName("MutedText")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.result_list = QListWidget()
        self.result_list.setObjectName("SearchResultList")
        self.result_list.setSpacing(4)
        self.result_list.itemClicked.connect(self._toggle_result_item)
        layout.addWidget(self.result_list, 1)

        button_row = QHBoxLayout()
        self.status_label = QLabel("输入 topic 或关键词后开始搜索 Repo")
        self.status_label.setObjectName("MutedText")
        button_row.addWidget(self.status_label, 1)

        select_all_button = QPushButton("全选")
        select_all_button.clicked.connect(lambda: self._set_all_checked(True))
        button_row.addWidget(select_all_button)

        clear_all_button = QPushButton("全不选")
        clear_all_button.clicked.connect(lambda: self._set_all_checked(False))
        button_row.addWidget(clear_all_button)

        self.import_button = QPushButton("导入选中")
        self.import_button.setObjectName("PrimaryButton")
        self.import_button.clicked.connect(self.accept)
        button_row.addWidget(self.import_button)

        cancel_button = QPushButton("取消")
        cancel_button.clicked.connect(self.reject)
        button_row.addWidget(cancel_button)
        layout.addLayout(button_row)

    def selected_repositories(self) -> list[Repository]:
        selected: list[Repository] = []
        for index, repo in enumerate(self.results):
            item = self.result_list.item(index)
            widget = self.result_list.itemWidget(item) if item else None
            if isinstance(widget, SearchResultWidget) and widget.is_checked():
                selected.append(repo)
        return selected

    def search_term(self) -> str:
        return self.query_input.text().strip()

    def search(self) -> None:
        term = self.search_term()
        if not term:
            self.status_label.setText("请输入 topic 或关键词")
            return

        self.search_button.setEnabled(False)
        self.search_button.setText("搜索中...")
        self.result_list.clear()
        self.status_label.setText(f"正在搜索 {term} ...")
        QApplication.processEvents()

        topic = _clean_search_topic(term)
        queries = [f"topic:{topic} stars:>10"] if topic else []
        if topic != term.lower():
            queries.append(f"{term} stars:>10")
        else:
            queries.append(f"{term} stars:>10")

        try:
            repos = search_repositories(queries, per_page=30, pause_seconds=0)
        except GitHubApiError as exc:
            QMessageBox.warning(self, "搜索失败", str(exc))
            repos = []
        finally:
            self.search_button.setEnabled(True)
            self.search_button.setText("搜索")

        self.results = repos[:30]
        for repo in self.results:
            item = QListWidgetItem()
            item.setToolTip(repo.description or repo.full_name)
            self.result_list.addItem(item)
            widget = SearchResultWidget(repo)
            item.setSizeHint(widget.sizeHint())
            self.result_list.setItemWidget(item, widget)
        self.status_label.setText(f"找到 {len(self.results)} 个结果")

    def _toggle_result_item(self, item: QListWidgetItem) -> None:
        widget = self.result_list.itemWidget(item)
        if isinstance(widget, SearchResultWidget):
            widget.toggle_checked()

    def _set_all_checked(self, checked: bool) -> None:
        for index in range(self.result_list.count()):
            item = self.result_list.item(index)
            widget = self.result_list.itemWidget(item)
            if isinstance(widget, SearchResultWidget):
                widget.checkbox.setChecked(checked)


class RadarReader(QMainWindow):
    def __init__(self, config_path: str | Path = "radar.toml") -> None:
        super().__init__()
        self.setObjectName("RadarReader")
        font_family = _preferred_font_family()
        if font_family:
            QApplication.setFont(QFont(font_family, 9))
        self.settings = load_settings(config_path)
        self._set_window_icon()
        self.conn = db.connect(self.settings.db_path)
        db.init_db(self.conn)
        self.scored: list[ScoredRepository] = []
        self.filtered: list[ScoredRepository] = []
        self.feedback_by_repo: dict[str, str] = {}
        self.tags_by_repo: dict[str, list[str]] = {}
        self.all_tags: list[str] = []
        self.current: ScoredRepository | None = None

        self.setWindowTitle("GitHub Radar 阅读器")
        self.resize(1600, 820)
        self.setMinimumSize(1200, 680)
        self._build_ui()
        self._apply_style()
        self.reload_data()

    def _set_window_icon(self) -> None:
        icon_path = self.settings.project_root / "assets" / "app-icon.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

    def _build_ui(self) -> None:
        toolbar = QToolBar("工具")
        toolbar.setObjectName("MainToolBar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(16, 16))
        self.addToolBar(toolbar)

        refresh_action = QAction("刷新数据", self)
        refresh_action.triggered.connect(self.prompt_refresh_data)
        toolbar.addAction(refresh_action)

        import_action = QAction("导入仓库", self)
        import_action.triggered.connect(self.import_repository)
        toolbar.addAction(import_action)

        topic_import_action = QAction("搜索 Repo", self)
        topic_import_action.triggered.connect(self.import_by_topic)
        toolbar.addAction(topic_import_action)

        random_action = QAction("随便看看", self)
        random_action.setShortcut("Ctrl+R")
        random_action.triggered.connect(self.random_item)
        toolbar.addAction(random_action)

        settings_action = QAction("设置", self)
        settings_action.triggered.connect(self.open_settings)
        toolbar.addAction(settings_action)

        self.status = QStatusBar()
        self.status.setObjectName("Status")
        self.setStatusBar(self.status)

        root = QSplitter(Qt.Horizontal)
        root.setChildrenCollapsible(False)
        self.setCentralWidget(root)

        left = QWidget()
        left.setFixedWidth(200)
        left.setObjectName("Sidebar")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(12, 16, 10, 16)
        left_layout.setSpacing(10)

        filter_title = QLabel("筛选")
        filter_title.setObjectName("PanelTitle")
        left_layout.addWidget(filter_title)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索名称、简介、语言...")
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

        self.tag_filter = QComboBox()
        self.tag_filter.currentIndexChanged.connect(lambda *_args: self.apply_filters())
        left_layout.addWidget(self.tag_filter)

        self.sort_filter = QComboBox()
        for key, label in SORT_OPTIONS.items():
            self.sort_filter.addItem(label, key)
        self.sort_filter.currentIndexChanged.connect(lambda *_args: self.apply_filters())
        left_layout.addWidget(self.sort_filter)

        self.only_unmarked = QCheckBox("只看未标记")
        self.only_unmarked.stateChanged.connect(self.toggle_unmarked_filter)
        left_layout.addWidget(self.only_unmarked)
        left_layout.addStretch(1)
        root.addWidget(left)

        middle = QWidget()
        middle.setObjectName("RepoPane")
        middle.setMinimumWidth(380)
        middle_layout = QVBoxLayout(middle)
        middle_layout.setContentsMargins(14, 16, 14, 16)
        middle_layout.setSpacing(10)

        repo_title = QLabel("项目")
        repo_title.setObjectName("PanelTitle")
        middle_layout.addWidget(repo_title)

        self.repo_list = QListWidget()
        self.repo_list.setObjectName("RepoList")
        self.repo_list.setSpacing(6)
        self.repo_list.setMouseTracking(True)
        self.repo_list.setItemDelegate(RepoListDelegate(self.repo_list))
        self.repo_list.currentRowChanged.connect(self.show_current)
        middle_layout.addWidget(self.repo_list, 1)
        root.addWidget(middle)

        right = QWidget()
        right.setObjectName("Content")
        right.setMinimumWidth(620)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(18, 16, 18, 14)
        right_layout.setSpacing(12)

        self.title = QLabel("选择一个项目")
        self.title.setObjectName("RepoTitle")
        self.title.setTextInteractionFlags(Qt.TextSelectableByMouse)
        right_layout.addWidget(self.title)

        self.detail = QTextBrowser()
        self.detail.setObjectName("Detail")
        self.detail.setOpenExternalLinks(True)
        right_layout.addWidget(self.detail, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.auto_next = QCheckBox("标记后自动下一条")
        self.auto_next.setChecked(True)
        buttons.addWidget(self.auto_next)

        self.next_button = QPushButton("下一条")
        self.next_button.setObjectName("SecondaryButton")
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
            button.setProperty("feedback", tag)
            button.clicked.connect(lambda checked=False, s=signal, t=tag: self.record_feedback(s, t))
            buttons.addWidget(button)

        self.open_button = QPushButton("打开 GitHub")
        self.open_button.setObjectName("PrimaryButton")
        self.open_button.clicked.connect(self.open_current)
        buttons.addWidget(self.open_button)
        right_layout.addLayout(buttons)

        tag_row = QHBoxLayout()
        tag_row.setSpacing(8)
        tag_label = QLabel("标签")
        tag_label.setObjectName("FieldLabel")
        tag_row.addWidget(tag_label)

        self.tag_pills = QWidget()
        self.tag_pills_layout = QHBoxLayout(self.tag_pills)
        self.tag_pills_layout.setContentsMargins(0, 0, 0, 0)
        self.tag_pills_layout.setSpacing(6)
        tag_row.addWidget(self.tag_pills)

        self.tag_input = QLineEdit()
        self.tag_input.setPlaceholderText("添加标签...")
        self.tag_input.returnPressed.connect(self.add_current_tags)
        self.tag_completer_model = QStringListModel()
        self.tag_completer = QCompleter(self.tag_completer_model, self)
        self.tag_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.tag_completer.setFilterMode(Qt.MatchContains)
        self.tag_completer.activated[str].connect(self._add_tag_from_text)
        self.tag_input.setCompleter(self.tag_completer)
        tag_row.addWidget(self.tag_input, 1)

        self.add_tag_button = QPushButton("+")
        self.add_tag_button.setObjectName("IconButton")
        self.add_tag_button.setToolTip("添加标签")
        self.add_tag_button.clicked.connect(self.add_current_tags)
        tag_row.addWidget(self.add_tag_button)
        right_layout.addLayout(tag_row)

        root.addWidget(right)
        root.setSizes([200, 450, 950])
        root.setStretchFactor(0, 0)
        root.setStretchFactor(1, 0)
        root.setStretchFactor(2, 1)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow#RadarReader {
                background: #f5f7fb;
                color: #172033;
                font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
                font-size: 13px;
            }
            QToolBar#MainToolBar {
                background: #ffffff;
                border: 0;
                border-bottom: 1px solid #dfe5ef;
                spacing: 6px;
                padding: 8px 10px;
            }
            QToolButton {
                background: transparent;
                border: 1px solid transparent;
                border-radius: 6px;
                color: #334155;
                padding: 6px 10px;
                font-weight: 500;
            }
            QToolButton:hover {
                background: #eef5ff;
                border-color: #c8daf7;
                color: #1557a6;
            }
            QWidget#Sidebar {
                background: #f8fafc;
                border-right: 1px solid #dfe5ef;
            }
            QWidget#RepoPane {
                background: #f8fafc;
                border-right: 1px solid #dfe5ef;
            }
            QWidget#Content {
                background: #ffffff;
            }
            QLabel#PanelTitle {
                color: #0f172a;
                font-size: 16px;
                font-weight: 700;
                padding-bottom: 2px;
            }
            QLabel#RepoTitle {
                color: #0f172a;
                font-size: 22px;
                font-weight: 700;
                padding: 2px 0 4px 0;
            }
            QLabel#FieldLabel {
                color: #475569;
                font-weight: 600;
            }
            QLabel#MutedText {
                color: #64748b;
                line-height: 1.4;
            }
            QLineEdit, QComboBox {
                background: #ffffff;
                border: 1px solid #cfd8e6;
                border-radius: 7px;
                min-height: 30px;
                padding: 4px 9px;
                color: #172033;
                selection-background-color: #cfe4ff;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #4f8edc;
                background: #fbfdff;
            }
            QComboBox::drop-down {
                border: 0;
                width: 24px;
            }
            QCheckBox {
                color: #334155;
                spacing: 6px;
            }
            QCheckBox::indicator {
                width: 15px;
                height: 15px;
                border-radius: 4px;
                border: 1px solid #b9c5d6;
                background: #ffffff;
            }
            QCheckBox::indicator:checked {
                background: #2563eb;
                border-color: #2563eb;
            }
            QListWidget#RepoList {
                background: #f8fafc;
                border: 0;
                outline: 0;
            }
            QListWidget#SearchResultList {
                background: #ffffff;
                border: 1px solid #e0e7f1;
                border-radius: 8px;
                outline: 0;
            }
            QListWidget#SearchResultList::item {
                border: 0;
                padding: 0;
            }
            QListWidget#SearchResultList::item:hover {
                background: #f3f8ff;
            }
            QListWidget#SearchResultList::item:selected {
                background: #eaf3ff;
                color: #0f172a;
            }
            QWidget#SearchResultRow {
                background: transparent;
                color: #0f172a;
            }
            QLabel#SearchResultTitle {
                color: #0f172a;
                font-weight: 700;
            }
            QLabel#SearchResultMeta {
                color: #334155;
                font-size: 12px;
            }
            QLabel#SearchResultDescription {
                color: #475569;
                font-size: 12px;
            }
            QCheckBox#SearchResultCheck::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid #94a3b8;
                background: #ffffff;
            }
            QCheckBox#SearchResultCheck::indicator:checked {
                background: #2563eb;
                border-color: #2563eb;
            }
            QTextBrowser#Detail {
                background: #ffffff;
                border: 1px solid #e0e7f1;
                border-radius: 8px;
                padding: 14px;
                color: #1f2937;
            }
            QPushButton {
                background: #ffffff;
                border: 1px solid #cfd8e6;
                border-radius: 7px;
                color: #1f2937;
                min-height: 28px;
                padding: 5px 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background: #f3f8ff;
                border-color: #9fc3f2;
            }
            QPushButton#PrimaryButton {
                background: #2563eb;
                border-color: #2563eb;
                color: #ffffff;
                font-weight: 700;
            }
            QPushButton#PrimaryButton:hover {
                background: #1d4ed8;
                border-color: #1d4ed8;
            }
            QPushButton#SecondaryButton {
                background: #f8fafc;
            }
            QPushButton#IconButton {
                min-width: 30px;
                max-width: 30px;
                padding: 4px 0;
                font-size: 16px;
                font-weight: 700;
            }
            QPushButton[feedback="liked"] {
                background: #ecfdf5;
                border-color: #b7ead1;
                color: #047857;
            }
            QPushButton[feedback="saved"] {
                background: #fff7ed;
                border-color: #fed7aa;
                color: #9a3412;
            }
            QPushButton[feedback="read"] {
                background: #f1f5f9;
                border-color: #d7e0ea;
                color: #475569;
            }
            QPushButton[feedback="disliked"] {
                background: #fff1f2;
                border-color: #fecdd3;
                color: #be123c;
            }
            QPushButton[feedback="hidden"] {
                background: #f5f3ff;
                border-color: #ddd6fe;
                color: #6d28d9;
            }
            QStatusBar#Status {
                background: #ffffff;
                border-top: 1px solid #dfe5ef;
                color: #64748b;
            }
            """
        )

    def reload_data(self) -> None:
        repos = db.load_recent_repositories(self.conn, limit=500)
        self.scored = score_all_repositories(self.conn, repos, self.settings)
        self.feedback_by_repo = self._load_latest_feedback()
        self.tags_by_repo = db.load_repository_tags(self.conn)
        self._populate_languages()
        self._populate_tags()
        self.apply_filters()
        self.status.showMessage(f"已载入 {len(self.scored)} 个项目", 5000)

    def prompt_refresh_data(self) -> None:
        dialog = RefreshDataDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        if dialog.should_fetch_from_github():
            self.collect_and_reload()
        else:
            self.reload_data()

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

    def import_repository(self) -> None:
        dialog = BatchImportDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return

        names = dialog.repo_names()
        if not names:
            self.status.showMessage("没有输入可导入的仓库", 3000)
            return

        self.status.showMessage(f"正在导入 {len(names)} 个仓库...")
        QApplication.processEvents()

        imported: list[Repository] = []
        failures: list[tuple[str, str]] = []
        for index, full_name in enumerate(names, start=1):
            self.status.showMessage(f"正在导入 {index}/{len(names)}：{full_name}")
            QApplication.processEvents()
            try:
                imported.append(fetch_repository(full_name))
            except GitHubApiError as exc:
                failures.append((full_name, str(exc)))

        if not imported:
            message = "\n".join(f"- {name}: {error}" for name, error in failures[:8])
            QMessageBox.warning(self, "导入失败", message or "没有仓库导入成功")
            return

        db.upsert_repositories(self.conn, imported)
        tags = dialog.tags()
        if tags:
            for repo in imported:
                db.add_repository_tags(self.conn, repo.full_name, tags)

        self.reload_data()
        self.apply_filters(preferred_name=imported[0].full_name)
        self._prepare_tag_input()

        summary = [f"已导入 {len(imported)} 个仓库。"]
        if tags:
            summary.append(f"已添加标签：{', '.join(sorted({tag.lower() for tag in tags}))}")
        if failures:
            summary.append("")
            summary.append(f"失败 {len(failures)} 个：")
            summary.extend(f"- {name}: {error}" for name, error in failures[:8])
            if len(failures) > 8:
                summary.append(f"... 还有 {len(failures) - 8} 个失败项")
        QMessageBox.information(
            self,
            "导入完成",
            "\n".join(summary),
        )

    def import_by_topic(self) -> None:
        dialog = TopicImportDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        repos = dialog.selected_repositories()
        if not repos:
            self.status.showMessage("没有选择要导入的仓库", 3000)
            return

        term = _clean_search_topic(dialog.search_term()) or dialog.search_term().strip().lower()
        self.status.showMessage(f"正在导入 {len(repos)} 个仓库...")
        QApplication.processEvents()

        db.upsert_repositories(self.conn, repos)
        if term:
            for repo in repos:
                db.add_repository_tags(self.conn, repo.full_name, [term])

        preferred_name = repos[0].full_name
        self.reload_data()
        self.apply_filters(preferred_name=preferred_name)
        QMessageBox.information(
            self,
            "导入完成",
            f"已导入 {len(repos)} 个仓库。"
            + (f"\n已自动添加标签：{term}" if term else ""),
        )

    def open_settings(self) -> None:
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.Accepted:
            token = dialog.github_token()
            save_github_token(self.settings.project_root, token)
            self.settings = load_settings(self.settings.project_root / "radar.toml")
            if token:
                self.status.showMessage("GitHub Token 已保存到项目 .env", 5000)
            else:
                self.status.showMessage("GitHub Token 已清除", 5000)

    def apply_filters(self, preferred_name: str | None = None, preferred_row: int | None = None) -> None:
        selected_name = preferred_name
        if selected_name is None:
            selected_name = self.current.repo.full_name if self.current else ""
        query = self.search.text().strip().lower()
        section = self.section_filter.currentData()
        language = self.language_filter.currentData() if self.language_filter.count() else "all"
        feedback = self.feedback_filter.currentData()
        tag_filter = self.tag_filter.currentData() if self.tag_filter.count() else "all"
        sort_key = self.sort_filter.currentData()

        self.filtered = []
        for item in self.scored:
            repo = item.repo
            repo_feedback = self.feedback_by_repo.get(repo.full_name)
            repo_tags = self.tags_by_repo.get(repo.full_name, [])
            if section != "all" and item.section != section:
                continue
            if language != "all" and (repo.language or "未知") != language:
                continue
            if feedback == "unmarked" and repo_feedback is not None:
                continue
            if feedback not in ("all", "unmarked") and repo_feedback != feedback:
                continue
            if tag_filter == "__untagged__" and repo_tags:
                continue
            if tag_filter not in ("all", "__untagged__") and tag_filter not in repo_tags:
                continue
            haystack = " ".join(
                [repo.full_name, repo.description, repo.language, " ".join(repo.topics), " ".join(repo_tags)]
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
        self._prepare_tag_input()
        self.detail.setHtml(self._detail_html(self.current))

    def record_feedback(self, signal: int, tag: str) -> None:
        if self.current is None:
            return
        repo = self.current.repo
        current_row = self.repo_list.currentRow()
        previous_tag = self.feedback_by_repo.get(repo.full_name)
        is_clearing = previous_tag == tag
        if is_clearing:
            db.add_feedback(self.conn, [repo.full_name], signal=0, tags=[])
            self.feedback_by_repo.pop(repo.full_name, None)
            self.status.showMessage(f"已取消“{FEEDBACK_LABELS[tag]}”标记：{repo.full_name}", 5000)
        else:
            db.add_feedback(self.conn, [repo.full_name], signal=signal, tags=[tag])
            self.feedback_by_repo[repo.full_name] = tag
            self.status.showMessage(f"已标记为“{FEEDBACK_LABELS[tag]}”：{repo.full_name}", 5000)
        if self.auto_next.isChecked():
            feedback_filter = self.feedback_filter.currentData()
            if is_clearing:
                current_stays_visible = feedback_filter in ("all", "unmarked")
            else:
                current_stays_visible = feedback_filter in ("all", tag)
            next_row = current_row + 1 if current_stays_visible else current_row
            self.apply_filters(preferred_row=next_row)
        else:
            feedback_filter = self.feedback_filter.currentData()
            if is_clearing and feedback_filter not in ("all", "unmarked"):
                self.apply_filters(preferred_row=current_row)
            elif not is_clearing and feedback_filter == "unmarked":
                self.apply_filters(preferred_row=current_row)
            else:
                self.apply_filters(preferred_name=repo.full_name)

    def add_current_tags(self) -> None:
        if self.current is None:
            return
        repo = self.current.repo
        tags = _split_tags(self.tag_input.text())
        if not tags:
            self.status.showMessage("请输入或选择要添加的标签", 3000)
            return
        self._add_tags_to_current(tags)

    def _add_tag_from_text(self, tag: str) -> None:
        if self.current is None:
            return
        tags = _split_tags(tag)
        if not tags:
            return
        self._add_tags_to_current(tags)

    def _add_tags_to_current(self, tags: list[str]) -> None:
        if self.current is None:
            return
        repo = self.current.repo
        db.add_repository_tags(self.conn, repo.full_name, tags)
        current_tags = set(self.tags_by_repo.get(repo.full_name, []))
        clean_tags = {tag.strip().lower() for tag in tags if tag.strip()}
        current_tags.update(clean_tags)
        self.tags_by_repo[repo.full_name] = sorted(current_tags)
        self._populate_tags()
        self.apply_filters(preferred_name=repo.full_name)
        self.tag_input.clear()
        self.status.showMessage(f"已给 {repo.full_name} 添加标签：{', '.join(sorted(clean_tags))}", 5000)

    def remove_current_tag(self, tag: str) -> None:
        if self.current is None:
            return
        repo = self.current.repo
        if not db.remove_repository_tag(self.conn, repo.full_name, tag):
            self.status.showMessage(f"{repo.full_name} 没有标签：{tag}", 3000)
            return
        remaining_tags = [
            existing for existing in self.tags_by_repo.get(repo.full_name, []) if existing != tag
        ]
        if remaining_tags:
            self.tags_by_repo[repo.full_name] = remaining_tags
        else:
            self.tags_by_repo.pop(repo.full_name, None)
        self._populate_tags()
        self.apply_filters(preferred_name=repo.full_name)
        self.status.showMessage(f"已从 {repo.full_name} 移除标签：{tag}", 5000)

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

    def _prompt_tags_for_import(self, full_name: str) -> None:
        all_tags = db.load_all_repository_tags(self.conn)
        label = f"给 {full_name} 添加标签（可选，多个用逗号分隔）："
        if all_tags:
            tag_text, ok = QInputDialog.getItem(
                self,
                "添加标签",
                label,
                all_tags,
                0,
                True,
            )
        else:
            tag_text, ok = QInputDialog.getText(self, "添加标签", label)
        if ok:
            tags = _split_tags(tag_text)
            if tags:
                db.add_repository_tags(self.conn, full_name, tags)

    def _find_scored(self, full_name: str) -> ScoredRepository | None:
        for item in self.scored:
            if item.repo.full_name.lower() == full_name.lower():
                return item
        return None

    def _import_summary(self, item: ScoredRepository | None, full_name: str) -> str:
        stats = db.repository_stats(self.conn)
        if item is None:
            return f"已导入 {full_name}\n\n当前数据库仓库数：{stats['total_repositories']}"

        repo = item.repo
        top_languages = "，".join(
            f"{language} {count}" for language, count in stats["top_languages"]
        ) or "无"
        feedback_counts = stats["feedback_counts"]
        feedback_text = "，".join(
            f"{FEEDBACK_LABELS.get(tag, tag)} {count}" for tag, count in sorted(feedback_counts.items())
        ) or "无"
        return (
            f"已导入：{repo.full_name}\n\n"
            f"综合分：{item.total_score:.2f}\n"
            f"热度：{item.heat_score:.2f}  增长：{item.growth_score:.2f}  "
            f"新鲜度：{item.recency_score:.2f}  兴趣：{item.interest_score:.2f}\n"
            f"Stars：{repo.stars:,}  Forks：{repo.forks:,}  语言：{repo.language or '未知'}\n"
            f"首次入库：{self._format_time(repo.first_seen_at)}\n"
            f"最后采集：{self._format_time(repo.last_seen_at)}\n\n"
            f"数据库统计：\n"
            f"仓库总数：{stats['total_repositories']}\n"
            f"已标记仓库：{stats['marked_repositories']}\n"
            f"热门语言：{top_languages}\n"
            f"反馈计数：{feedback_text}"
        )

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

    def _populate_tags(self) -> None:
        current_filter = self.tag_filter.currentData() if self.tag_filter.count() else "all"
        self.all_tags = db.load_all_repository_tags(self.conn)

        self.tag_filter.blockSignals(True)
        self.tag_filter.clear()
        self.tag_filter.addItem("全部标签", "all")
        self.tag_filter.addItem("未加标签", "__untagged__")
        for tag in self.all_tags:
            self.tag_filter.addItem(tag, tag)
        index = self.tag_filter.findData(current_filter)
        self.tag_filter.setCurrentIndex(index if index >= 0 else 0)
        self.tag_filter.blockSignals(False)

        if hasattr(self, "tag_completer_model"):
            self.tag_completer_model.setStringList(self.all_tags)

    def _prepare_tag_input(self) -> None:
        if self.current is None:
            self.tag_input.clear()
            self._render_tag_pills([])
            return
        repo_tags = self.tags_by_repo.get(self.current.repo.full_name, [])
        self.tag_input.clear()
        self._render_tag_pills(repo_tags)

    def _render_tag_pills(self, tags: list[str]) -> None:
        while self.tag_pills_layout.count():
            item = self.tag_pills_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for tag in tags:
            pill = QPushButton(f"{tag}  ×")
            pill.setToolTip("点击移除标签")
            pill.setCursor(Qt.PointingHandCursor)
            pill.setStyleSheet(
                """
                QPushButton {
                    background: #eef2f7;
                    color: #334155;
                    border: 1px solid #d8dee9;
                    border-radius: 10px;
                    padding: 3px 8px;
                }
                QPushButton:hover {
                    background: #e2e8f0;
                    color: #0f172a;
                }
                """
            )
            pill.clicked.connect(lambda checked=False, t=tag: self.remove_current_tag(t))
            self.tag_pills_layout.addWidget(pill)
        self.tag_pills_layout.addStretch(1)

    def _load_latest_feedback(self) -> dict[str, str]:
        latest: dict[str, str] = {}
        for item in reversed(db.load_feedback(self.conn)):
            latest.pop(item.full_name, None)
            for tag in item.tags:
                if tag in FEEDBACK_LABELS:
                    latest[item.full_name] = tag
                    break
        return latest

    def _list_item(self, item: ScoredRepository) -> QListWidgetItem:
        repo = item.repo
        marker = self.feedback_by_repo.get(repo.full_name)
        suffix = f"（{FEEDBACK_LABELS[marker]}）" if marker else ""
        tags = self.tags_by_repo.get(repo.full_name, [])
        tag_text = f" · 标签 {', '.join(tags)}" if tags else ""
        label = (
            f"{repo.full_name}{suffix}\n"
            f"{SECTION_LABELS.get(item.section, item.section)} · "
            f"{repo.language or '未知'} · {repo.stars:,} stars · "
            f"采集 {self._format_time(repo.last_seen_at)} · score {item.total_score:.2f}"
            f"{tag_text}"
        )
        widget_item = QListWidgetItem(label)
        widget_item.setSizeHint(QSize(320, 64))
        widget_item.setToolTip(repo.description or repo.full_name)
        widget_item.setData(Qt.UserRole, marker or "")
        return widget_item

    def _detail_html(self, item: ScoredRepository) -> str:
        repo = item.repo
        marker = self.feedback_by_repo.get(repo.full_name)
        feedback = FEEDBACK_LABELS[marker] if marker else "未标记"
        custom_tags = escape(", ".join(self.tags_by_repo.get(repo.full_name, [])) or "无")
        summary = escape(summarize_repository(repo))
        topics = escape(", ".join(repo.topics) if repo.topics else "无")
        reasons = "<br>".join(f"- {escape(reason)}" for reason in item.reasons) or "综合热度较高"
        description = escape(repo.description or "暂无描述")
        full_name = escape(repo.full_name)
        language = escape(repo.language or "未知")
        return f"""
        <style>
          body {{
            color: #1f2937;
            font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
            font-size: 14px;
            line-height: 1.55;
          }}
          a {{
            color: #2563eb;
            text-decoration: none;
            font-weight: 700;
          }}
          h2 {{
            color: #0f172a;
            font-size: 22px;
            margin: 0 0 14px 0;
          }}
          h3 {{
            color: #334155;
            font-size: 14px;
            font-weight: 700;
            margin: 18px 0 7px 0;
          }}
          p {{
            margin: 5px 0 10px 0;
          }}
          table {{
            border-collapse: collapse;
            margin-top: 8px;
            width: 100%;
          }}
          td {{
            border-bottom: 1px solid #e5eaf2;
            padding: 8px 10px;
            vertical-align: top;
          }}
          td:first-child {{
            background: #f8fafc;
            color: #475569;
            width: 116px;
          }}
        </style>
        <h2><a href="{escape(repo.html_url)}">{full_name}</a></h2>
        <h3>项目概述</h3>
        <p>{summary}</p>
        <h3>原始简介</h3>
        <p>{description}</p>
        <table>
          <tr><td><b>当前标记</b></td><td>{feedback}</td></tr>
          <tr><td><b>自定义标签</b></td><td>{custom_tags}</td></tr>
          <tr><td><b>分区</b></td><td>{SECTION_LABELS.get(item.section, item.section)}</td></tr>
          <tr><td><b>语言</b></td><td>{language}</td></tr>
          <tr><td><b>Topics</b></td><td>{topics}</td></tr>
          <tr><td><b>Stars</b></td><td>{repo.stars:,}</td></tr>
          <tr><td><b>Forks</b></td><td>{repo.forks:,}</td></tr>
          <tr><td><b>近 7 天增长</b></td><td>约 +{item.star_delta:,} stars</td></tr>
          <tr><td><b>首次入库</b></td><td>{escape(self._format_time(repo.first_seen_at))}</td></tr>
          <tr><td><b>最后采集</b></td><td>{escape(self._format_time(repo.last_seen_at))}</td></tr>
          <tr><td><b>创建时间</b></td><td>{escape(self._format_time(repo.created_at))}</td></tr>
          <tr><td><b>更新时间</b></td><td>{escape(self._format_time(repo.pushed_at))}</td></tr>
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
        return parsed.astimezone().strftime("%Y-%m-%d %H:%M")


def _split_tags(value: str) -> list[str]:
    return [tag.strip() for tag in re.split(r"[,，;；\s]+", value) if tag.strip()]


def _parse_repo_names(value: str) -> list[str]:
    seen: set[str] = set()
    names: list[str] = []
    for raw_line in value.splitlines():
        line = raw_line.strip().strip(",;")
        if not line:
            continue
        match = re.search(r"github\.com[/:]([^/\s]+)/([^/\s#?]+)", line, flags=re.I)
        if match:
            candidate = f"{match.group(1)}/{match.group(2)}"
        else:
            candidate = line
        candidate = candidate.strip().strip("/")
        candidate = re.sub(r"\.git$", "", candidate, flags=re.I)
        if not re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", candidate):
            continue
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(candidate)
    return names


def _clean_search_topic(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9_.-]+", "-", value.strip().lower())
    return cleaned.strip("-")


def _preferred_font_family() -> str:
    families = set(QFontDatabase.families())
    for family in [
        "Microsoft YaHei UI",
        "Microsoft YaHei",
        "Noto Sans CJK SC",
        "Source Han Sans SC",
        "SimHei",
        "Segoe UI",
    ]:
        if family in families:
            return family
    return ""


def main(argv: list[str] | None = None) -> int:
    app = QApplication(argv or sys.argv)
    window = RadarReader()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
