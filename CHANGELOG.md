# Changelog

All notable changes to GitHub Radar are documented here.

## [1.0.2] - 2026-06-12

### Changed

- Manual repository imports now appear in a dedicated "手动导入" section in the reader and Markdown reports.
- Marking an item while filtering to unmarked repositories no longer immediately removes it from the current list.
- Updated the application icon with a brighter, higher-contrast design for better desktop and taskbar recognition.

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
