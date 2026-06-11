from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
import sys
from pathlib import Path

from .gui import RadarReader
from .settings import ensure_default_config

try:
    from PySide6.QtWidgets import QApplication
except ModuleNotFoundError as exc:  # pragma: no cover
    raise SystemExit("缺少 PySide6。请先运行：python -m pip install PySide6") from exc


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    config_path = Path(args.config) if args.config else _default_config_path()
    ensure_default_config(config_path)
    if args.init_config:
        return 0
    if args.run:
        from .cli import main as cli_main

        cli_args = ["run", "--config", str(config_path)]
        if args.log:
            return _run_with_log(cli_main, cli_args, Path(args.log))
        return cli_main(cli_args)

    app = QApplication([sys.argv[0]])
    window = RadarReader(config_path)
    window.show()
    return app.exec()


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GitHub Radar reader.")
    parser.add_argument("--config", default="", help="Path to radar.toml.")
    parser.add_argument("--init-config", action="store_true", help="Create radar.toml and exit.")
    parser.add_argument("--run", action="store_true", help="Run collection and report generation without opening the reader.")
    parser.add_argument("--log", default="", help="Write headless run output to a log file.")
    return parser.parse_args(argv)


def _run_with_log(cli_main, cli_args: list[str], log_path: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n=== GitHub Radar run {datetime.now().isoformat(timespec='seconds')} ===\n")
        log.flush()
        with redirect_stdout(log), redirect_stderr(log):
            exit_code = cli_main(cli_args)
        log.write(f"Exit code: {exit_code}\n")
    return exit_code


def _default_config_path() -> Path:
    exe_root = Path(sys.argv[0]).resolve().parent
    search_roots = [Path.cwd(), exe_root]

    for root in search_roots:
        for candidate_root in [root, *root.parents]:
            config = candidate_root / "radar.toml"
            if config.exists():
                return config
    return exe_root / "radar.toml"


if __name__ == "__main__":
    raise SystemExit(main())
