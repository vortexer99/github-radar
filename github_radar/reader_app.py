from __future__ import annotations

import sys
from pathlib import Path

from .gui import RadarReader

try:
    from PySide6.QtWidgets import QApplication
except ModuleNotFoundError as exc:  # pragma: no cover
    raise SystemExit("缺少 PySide6。请先运行：python -m pip install PySide6") from exc


def main() -> int:
    app = QApplication(sys.argv)
    window = RadarReader(_default_config_path())
    window.show()
    return app.exec()


def _default_config_path() -> Path:
    search_roots = [Path.cwd(), Path(sys.argv[0]).resolve().parent]
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        search_roots.append(Path(bundle_root))

    for root in search_roots:
        for candidate_root in [root, *root.parents]:
            config = candidate_root / "radar.toml"
            if config.exists():
                return config
    return Path.cwd() / "radar.toml"


if __name__ == "__main__":
    raise SystemExit(main())
