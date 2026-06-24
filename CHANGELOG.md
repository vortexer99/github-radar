# Changelog

All notable changes to GitHub Radar are documented here.

## [1.2.0] - 2026-06-24

### Added

- Added feedback-driven GitHub collection planning that appends interest queries learned from positive feedback.
- Added a Settings preference preview tab and a switch to enable or disable interest-based GitHub collection queries.
- Added lightweight text logs under `logs/` for each GitHub collection run, including the planned queries and run outcome.
- Added a `config_schema_version` field and a legacy query-template notice for older configs that still contain default topic queries.

### Changed

- Replaced preset default topic queries with broad collection queries plus learned interest queries.
- Expanded the default broad exploration queries from 2 to 5 so collection keeps more non-personalized coverage.
- Clarified the UI and README distinction between GitHub collection and manual Repo search import.
- Updated the Windows scheduled-run docs to call `GitHubRadarReader.exe --run` directly and removed `run-radar.ps1` from the release package.
- Changed the CI artifact upload to publish the unpacked Windows package directory while keeping a zip asset for GitHub Releases.
- Reworked report sections around manual imports, personalized matches, and exploration results.
- Improved interest query planning with plural-variant merging, noisy keyword filtering, type diversity, and valid GitHub language filters.

## [1.1.0] - 2026-06-21

### Added

- Reworked the Settings dialog into a "采集" tab that edits all collection parameters in the UI (min stars, per-query count, created/pushed windows, exploration ratio, languages, downranked keywords, topics, and query templates), with a field-help dialog and write-back to `radar.toml`.
- Added a `topics` config key plus topic↔query-template conversion, so editing topics regenerates the default queries.
- Added a "检查更新" action on the About tab that compares the local version against the latest GitHub release.
- Added a "只看已标记" filter alongside the existing unmarked filter.
- Added a status-bar progress bar with live per-query messages when fetching from GitHub; collection now runs on a background thread so the window stays responsive.

### Changed

- Bumped the minimum Python version to 3.11.

## [1.0.5] - 2026-06-21

### Added

- Added retry/backoff for transient GitHub API failures such as network errors, rate limits, and GitHub 5xx responses.

### Changed

- Reworked README around the desktop exe user path, with source-mode and maintenance details separated from the main usage flow.

## [1.0.4] - 2026-06-20

### Added

- Added GitHub API credential fallback from Settings token to GitHub CLI login, environment variables, and anonymous API requests.
- Added reader and CLI status messages showing which GitHub authentication source was used.

## [1.0.3] - 2026-06-14

### Changed

- Manual repository imports now appear in a dedicated "手动导入" section in the reader and Markdown reports.
- Marking an item while filtering to unmarked repositories no longer immediately removes it from the current list.
- Updated the application icon with a brighter, higher-contrast design for better desktop and taskbar recognition.

## [1.0.2] - 2026-06-12

### Fixed

- Fixed Windows CI packaging so PySide6/Qt is bundled into `GitHubRadarReader.exe`.
- Added packaged exe size validation and a `--init-config` smoke test to prevent uploading broken reader builds.

## [1.0.1] - 2026-06-11

### Added

- Added a Windows GitHub Actions workflow for building the reader package.
- Added a README screenshot for the desktop reader.
- Added first-run creation of the default `radar.toml`.
- Added first-run prompt in `run-radar.ps1` so users can decide whether to fetch immediately after config creation.
- Added `GitHubRadarReader.exe --run --config radar.toml` for headless collection from the packaged reader.
- Added `run-radar.log` for packaged collection errors.

### Changed

- Changed the Windows reader build to PyInstaller one-file output.
- Updated `run-radar.ps1` to prefer the packaged reader exe and fall back to source mode.
- Updated scheduled-task helper to pass `-AssumeYes` for non-interactive runs.
- Updated `run-radar.ps1` to wait for the packaged exe and verify that a new report was generated.
- Updated distribution docs to recommend shipping `README.md`, `GitHubRadarReader.exe`, and `run-radar.ps1`.
- Removed bundled `radar.toml` from the exe build; runtime config is now created next to the app.
- Reader GitHub refresh now shows the actual API or runtime error instead of only exit code `2`.

## [1.0.0] - 2026-06-11

### Added

- Added the PySide desktop reader with a three-column layout.
- Added repository feedback actions: like, save, read, dislike, and downrank similar repos.
- Added custom repository tags with completion and pill-style editing.
- Added tag, language, feedback, section, keyword, and sort filters.
- Added batch repository import and GitHub repo search import.
- Added settings for GitHub Token and app information.
- Added local-time display for repository timestamps.
- Added the application icon and Windows packaging scripts.

### Changed

- Reworked README for the 1.0 release with bilingual Chinese and English documentation.
- Archived the old H5 static reader and made the PySide reader the primary UI.
