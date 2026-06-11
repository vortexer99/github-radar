# GitHub Radar

<p align="center">
  <img src="assets/app-icon.png" alt="GitHub Radar icon" width="128" height="128">
</p>

GitHub Radar 是一个本地优先的 GitHub 热门项目雷达。它可以定期采集热门仓库，按热度、增长、新鲜度和你的反馈排序，并提供桌面阅读器来筛选、标记、加标签和导入项目。  
GitHub Radar is a local-first radar for trending GitHub repositories. It can periodically collect popular repos, rank them by heat, growth, freshness, and your feedback, and provides a desktop reader for filtering, marking, tagging, and importing projects.

这是 vortexer99 的个人项目，主要按个人使用需求演进。不承诺后续维护、功能支持或兼容性保证。有功能需求可以发 issue。  
This is a personal project by vortexer99 and evolves mainly around personal usage needs. No long-term maintenance, support, or compatibility guarantee is promised. Feature requests can be filed as issues.

当前版本 / Current version: `1.0.0`

## 功能 / Features

- GitHub 热门仓库采集，数据保存在本地 SQLite  
  Collect trending GitHub repositories and store data in local SQLite.
- Markdown 报告生成  
  Generate Markdown reports.
- PySide 桌面阅读器  
  PySide desktop reader.
- 三栏阅读布局：筛选、仓库列表、详情  
  Three-column reader layout: filters, repository list, and details.
- 喜欢、收藏、已阅、不感兴趣、少看这类反馈  
  Feedback actions: like, save, read, dislike, and downrank similar repos.
- 再次点击相同反馈会取消当前标记  
  Clicking the same feedback action again clears the current mark.
- 自定义仓库标签，支持类似 Notion 的多选标签体验  
  Custom repo tags with a Notion-like multi-select tagging experience.
- 按标签、语言、反馈状态、分区、关键词筛选  
  Filter by tag, language, feedback status, section, and keyword.
- 手动批量导入仓库，每行一个 `owner/repo`  
  Batch import repositories manually, one `owner/repo` per line.
- 用“搜索 Repo”按 topic/关键词搜索 GitHub 仓库并勾选导入  
  Use "搜索 Repo" / "Search Repo" to search GitHub by topic/keyword and import selected repositories.
- 设置页保存 GitHub Token，并显示软件信息  
  Settings page for saving a GitHub Token and viewing app information.
- “刷新数据”默认只重新加载本地数据库，也可以勾选后从 GitHub 获取最新数据  
  "Refresh data" reloads the local database by default, with an optional GitHub fetch.
- Windows exe 打包和应用图标  
  Windows exe packaging with an application icon.

## 快速开始 / Quick Start

如果只是日常使用，建议优先使用 exe 桌面阅读器；它是主要界面，支持筛选、标记、标签、导入、搜索和设置。详见 [桌面阅读器](#桌面阅读器--desktop-reader)。  
For daily use, the recommended entry point is the exe desktop reader. It is the primary UI for filtering, marking, tagging, importing, searching, and settings. See [Desktop Reader](#桌面阅读器--desktop-reader).

如果从源码运行采集和报告。  
If running collection and reports from source:

```powershell
cd path\to\github-radar
python -m pip install -e .
python -m github_radar run --config radar.toml
```

报告会生成到 `reports/`，数据库默认保存在 `data/radar.db`。  
Reports are written to `reports/`, and the default database path is `data/radar.db`.

## GitHub Token

建议配置 GitHub Token，提高 API 额度。  
A GitHub Token is recommended for higher API rate limits.

方式一：在桌面阅读器中配置。  
Option 1: configure it in the desktop reader.

```powershell
python -m github_radar.gui
```

打开“设置”，在 GitHub 页填写 Token。Token 会保存到项目根目录的 `.env` 文件，`.env` 已加入 `.gitignore`。  
Open "设置" / "Settings", then fill in the token on the GitHub tab. The token is saved to the project-level `.env` file, which is ignored by Git.

方式二：使用环境变量。  
Option 2: use an environment variable.

```powershell
$env:GITHUB_TOKEN = "<your-github-token>"
```

```powershell
$env:GITHUB_TOKEN = "<your-github-token>"
```

不要把真实 Token、`.env`、本机绝对路径或私人数据写入 README、配置示例或提交记录。  
Do not put real tokens, `.env` files, local absolute paths, or private data in README examples, configuration examples, or commits.

## 桌面阅读器 / Desktop Reader

启动 / Start:

```powershell
python -m github_radar.gui
```

也可以运行脚本。  
You can also run the helper script.

```powershell
.\scripts\run-reader.ps1
```

阅读器主要工作流：  
Main reader workflow:

1. 左栏筛选：搜索、分区、语言、反馈状态、标签、排序。  
   Use the left column for search, section, language, feedback status, tag, and sorting filters.
2. 中栏浏览仓库列表，已反馈项目会显示不同底色。  
   Browse repositories in the middle column; feedback-marked repos use different background colors.
3. 右栏阅读详情、打开 GitHub、记录反馈、管理自定义标签。  
   Read details, open GitHub, record feedback, and manage custom tags in the right column.
4. 点“刷新数据”时默认只从本地数据库加载；勾选“从 GitHub 获取最新数据后再刷新”才会采集远端数据。  
   Click "刷新数据" / "Refresh data" to reload locally by default; select "从 GitHub 获取最新数据后再刷新" to fetch from GitHub first.
5. 用“导入仓库”批量导入指定仓库。  
   Use "导入仓库" / "Import repositories" to batch import specific repos.
6. 用“搜索 Repo”按兴趣主题搜索并勾选导入。  
   Use "搜索 Repo" / "Search Repo" to search by interest topic and import selected repos.
7. 用“设置”配置 GitHub Token 和查看软件信息。  
   Use "设置" / "Settings" to configure the GitHub Token and view app information.

标签栏支持输入新标签，也支持从已用过的标签中补全选择；当前标签显示为胶囊，点击胶囊可移除。导入仓库时可以给本批仓库统一加标签，topic 搜索导入会自动把搜索词作为标签。  
The tag bar supports typing new tags and completing from existing tags. Current tags are shown as pills and can be removed by clicking them. Batch imports can apply shared tags, and topic search imports automatically tag repositories with the search term.

反馈按钮支持切换状态：对未标记仓库点击会设置标记；对已经有相同标记的仓库再次点击，会取消该标记。  
Feedback buttons are toggles: clicking a feedback action marks an unmarked repo, and clicking the same action again clears that mark.

## 命令行 / CLI

只查看会使用哪些 GitHub 查询。  
Preview GitHub queries without collecting data.

```powershell
python -m github_radar collect --dry-run
```

只采集，不生成报告。  
Collect data without generating a report.

```powershell
python -m github_radar collect
```

只基于本地数据重新生成报告。  
Regenerate a report from local data only.

```powershell
python -m github_radar report
```

采集并生成报告。  
Collect data and generate a report.

```powershell
python -m github_radar run --config radar.toml
```

记录偏好。  
Record preferences.

```powershell
python -m github_radar feedback --like owner/repo another/repo --dislike owner/nope
python -m github_radar feedback --more-topic ai cli rust --less-topic crypto blockchain
```

手动导入指定仓库。  
Manually import specific repositories.

```powershell
python -m github_radar import-repo owner/repo another/repo
```

## 自动运行 / Scheduled Runs

默认脚本会在周一和周四 06:00 运行。  
The default script creates a task that runs on Monday and Thursday at 06:00.

这个功能依赖 Windows 计划任务；脚本会调用 Task Scheduler 注册定时任务，并按计划运行 `scripts\run-radar.ps1`。如果不是 Windows，或者不想使用计划任务，请用系统自带的定时器，例如 cron、systemd timer 或其他任务调度工具，定时执行 `python -m github_radar run --config radar.toml`。  
This feature depends on Windows Task Scheduler. The script registers a scheduled task that runs `scripts\run-radar.ps1`. On non-Windows systems, or if you do not want to use Task Scheduler, use your system scheduler such as cron, systemd timers, or another task runner to execute `python -m github_radar run --config radar.toml`.

```powershell
cd path\to\github-radar
.\scripts\install-windows-task.ps1
```

如果想改时间。  
To use a different time:

```powershell
.\scripts\install-windows-task.ps1 -Time "18:30"
```

## 打包为 exe / Build exe

安装 PyInstaller 后运行。  
Install PyInstaller, then run:

```powershell
python -m pip install pyinstaller
.\scripts\build-reader-exe.ps1
```

生成文件：  
Output:

```text
dist\GitHubRadarReader\GitHubRadarReader.exe
```

打包会使用 `assets\app-icon.ico` 作为应用图标。exe 会优先读取启动目录或项目根目录下的 `radar.toml`，所以建议从项目根目录运行，或者把 `radar.toml` 和 `data\radar.db` 放在 exe 同级可访问的位置。  
Packaging uses `assets\app-icon.ico` as the application icon. The exe prefers `radar.toml` from the launch directory or project root, so running it from the project root is recommended. Alternatively, place `radar.toml` and `data\radar.db` somewhere accessible next to the exe.

## 配置 / Configuration

主要配置在 `radar.toml`。  
Main configuration lives in `radar.toml`.

- `db_path`：SQLite 数据库路径 / SQLite database path
- `report_dir`：报告输出目录 / Report output directory
- `min_stars`：采集查询的最低 stars / Minimum stars for collection queries
- `per_page`：每个 GitHub 查询拉取数量 / Number of results per GitHub query
- `created_within_days`：新建仓库查询窗口 / Creation-date query window
- `pushed_within_days`：近期更新仓库查询窗口 / Recent-push query window
- `exploration_ratio`：探索推荐比例 / Exploration recommendation ratio
- `languages`：限定语言 / Language filters
- `excluded_terms`：降权关键词 / Downranked keywords
- `query_templates`：GitHub 搜索模板 / GitHub search templates

## 发布 1.0 检查 / 1.0 Release Checklist

发布前建议确认。  
Before release, run:

```powershell
python -m compileall github_radar
python -m github_radar collect --dry-run
python -m github_radar report
python -m github_radar.gui
```

如果要发布 Windows 阅读器，再运行。  
For the Windows reader build, also run:

```powershell
.\scripts\build-reader-exe.ps1
```

## 已归档功能 / Archived Features

H5 静态阅读器已经归档，不再维护。相关文件保留在 `archive\h5\`，仅用于历史参考；当前主力阅读器是 PySide 桌面版，因为它可以直接读写 SQLite 反馈、标签和设置。  
The old H5 static reader is archived and no longer maintained. Its files remain in `archive\h5\` for historical reference only. The current primary reader is the PySide desktop app because it can directly read and write SQLite feedback, tags, and settings.
