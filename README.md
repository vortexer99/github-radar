# GitHub Radar

一个会逐步学习你偏好的 GitHub 热门项目雷达。第一版使用 Python 标准库、GitHub API、SQLite 和 Markdown 报告。

这是 vortexer99 的个人项目，主要按个人使用需求演进。不承诺后续维护、功能支持或兼容性保证。

## 快速开始

```powershell
cd D:\Documents\Utilcode\github\github-radar
python -m github_radar run --config radar.toml
```

建议设置 GitHub token，提高 API 额度：

```powershell
$env:GITHUB_TOKEN = "你的 token"
```

报告会生成到 `reports/`，数据库会保存在 `data/radar.db`。

## 反馈偏好

看完报告后，用仓库名反馈：

```powershell
python -m github_radar feedback --like owner/repo another/repo --dislike owner/nope
```

也可以直接告诉系统多看或少看某些主题：

```powershell
python -m github_radar feedback --more-topic ai cli rust --less-topic crypto blockchain
```

下一次报告会把内容分成：

- 你可能感兴趣
- 探索推荐
- 其他热门项目

## 可视化阅读器

安装 PySide6 后启动桌面阅读器：

```powershell
python -m pip install PySide6
python -m github_radar.gui
```

也可以运行脚本：

```powershell
.\scripts\run-reader.ps1
```

阅读器左侧提供搜索、分区筛选、语言筛选、反馈标记筛选和排序。右侧显示项目详情，详情顶部会给出一句话“项目概述”，帮助快速判断仓库是做什么的；详情表格会显示“首次入库”和“最后采集”时间。排序支持推荐分、最后采集时间、首次入库时间、GitHub 更新时间和 Stars。底部的“喜欢”“收藏”“已阅”“不感兴趣”“少看这类”会直接写入本地反馈数据库，项目列表会立刻显示类似“（喜欢）”的标记，并用不同底色区分标记类型。可以勾选“只看未标记”连续处理新项目；默认开启“标记后自动下一条”，也可以点“下一条”或按 `Ctrl+N` 手动跳转。后续报告和界面排序都会使用这些偏好；“已阅”表示看过但不影响兴趣权重。

## 已归档功能

H5 静态阅读器已经归档，不再维护。相关文件保留在 `archive\h5\`，仅用于历史参考；当前主力阅读器是 PySide 桌面版，因为它可以直接读写 SQLite 反馈数据库，不需要手动导入导出 JSON。

## 每周两次自动运行

默认脚本会在周一和周四 09:00 运行：

```powershell
cd D:\Documents\Utilcode\github\github-radar
.\scripts\install-windows-task.ps1
```

如果想改时间：

```powershell
.\scripts\install-windows-task.ps1 -Time "18:30"
```

## 常用命令

只查看会使用哪些 GitHub 查询：

```powershell
python -m github_radar collect --dry-run
```

只采集，不生成报告：

```powershell
python -m github_radar collect
```

只基于本地数据重新生成报告：

```powershell
python -m github_radar report
```

## 后续可扩展

- 加 README 摘要和 embedding 相似度
- 加 HTML 报告或邮件推送
- 加真实 star 增长趋势图
- 继续打磨 PySide 桌面阅读器
