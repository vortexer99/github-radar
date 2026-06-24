from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

from . import db
from .github_api import GitHubApiError, fetch_repository, last_auth_source, search_repositories
from .query_planner import plan_collection_queries
from .report import write_markdown_report
from .scorer import score_all_repositories, score_repositories
from .settings import ensure_default_config, load_settings


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "init-config":
        return init_config(args)

    settings = load_settings(args.config)

    conn = db.connect(settings.db_path)
    db.init_db(conn)

    if args.command == "collect":
        return collect(args, settings, conn)
    if args.command == "report":
        return report(args, settings, conn)
    if args.command == "feedback":
        return feedback(args, settings, conn)
    if args.command == "import-repo":
        return import_repo(args, settings, conn)
    if args.command == "run":
        return run(args, settings, conn)

    parser.print_help()
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Personal GitHub hot project radar.")
    parser.add_argument("--config", default=None, help="Path to radar.toml.")
    sub = parser.add_subparsers(dest="command")

    collect_parser = sub.add_parser("collect", help="Collect repositories from GitHub.")
    collect_parser.add_argument("--config", default=None, help="Path to radar.toml.")
    collect_parser.add_argument("--dry-run", action="store_true", help="Print queries only.")

    report_parser = sub.add_parser("report", help="Generate a Markdown report from local data.")
    report_parser.add_argument("--config", default=None, help="Path to radar.toml.")
    report_parser.add_argument("--limit", type=int, default=300)

    run_parser = sub.add_parser("run", help="Collect data and generate a Markdown report.")
    run_parser.add_argument("--config", default=None, help="Path to radar.toml.")
    run_parser.add_argument("--limit", type=int, default=300)

    feedback_parser = sub.add_parser("feedback", help="Record preferences for future reports.")
    feedback_parser.add_argument("--config", default=None, help="Path to radar.toml.")
    feedback_parser.add_argument("--like", nargs="*", default=[], help="Repositories you liked.")
    feedback_parser.add_argument("--dislike", nargs="*", default=[], help="Repositories you disliked.")
    feedback_parser.add_argument("--save", nargs="*", default=[], help="Repositories worth revisiting.")
    feedback_parser.add_argument("--hide", nargs="*", default=[], help="Repositories to strongly downrank.")
    feedback_parser.add_argument("--more-topic", nargs="*", default=[], help="Topics or keywords to boost.")
    feedback_parser.add_argument("--less-topic", nargs="*", default=[], help="Topics or keywords to downrank.")
    feedback_parser.add_argument("--note", default="", help="Optional note for repo feedback.")

    import_parser = sub.add_parser("import-repo", help="Manually import specific repositories.")
    import_parser.add_argument("--config", default=None, help="Path to radar.toml.")
    import_parser.add_argument("repos", nargs="+", help="Repositories in owner/name format.")

    init_parser = sub.add_parser("init-config", help="Create a default radar.toml.")
    init_parser.add_argument("--config", default="radar.toml", help="Path to radar.toml.")

    return parser


def init_config(args: argparse.Namespace) -> int:
    from pathlib import Path

    path = Path(args.config)
    existed = path.exists()
    ensure_default_config(path)
    print(f"{'Existing' if existed else 'Created'} config: {path}")
    return 0


def collect(args: argparse.Namespace, settings, conn) -> int:
    queries = plan_collection_queries(settings, conn)
    if args.dry_run:
        for query in queries:
            print(query)
        return 0

    log = _start_collection_text_log(settings, mode="collect", queries=queries)

    def search_progress(done: int, total: int, query: str) -> None:
        if log is not None:
            log.append(f"search {done + 1}/{total}: {query}")

    try:
        repos = search_repositories(
            queries,
            per_page=settings.per_page,
            token=settings.github_token,
            progress_callback=search_progress,
        )
        count = db.upsert_repositories(conn, repos)
        auth = last_auth_source()
        if log is not None:
            log.finish("ok", repos_seen=count, auth=auth)
        print(f"Collected {count} repositories into {_display_path(settings.project_root, settings.db_path)}")
        print(f"GitHub auth: {auth}")
        if log is not None:
            print(f"Collection log: {log.display_path(log.path)}")
        return 0
    except GitHubApiError as exc:
        if log is not None:
            log.finish("error", repos_seen=0, auth=last_auth_source(), message=str(exc))
        raise
    except Exception as exc:
        if log is not None:
            log.finish(
                "error",
                repos_seen=0,
                auth=last_auth_source(),
                message=f"{type(exc).__name__}: {exc}",
            )
        raise


def report(args: argparse.Namespace, settings, conn) -> int:
    repos = db.load_recent_repositories(conn, limit=args.limit)
    scored = score_repositories(conn, repos, settings)
    path = write_markdown_report(scored, settings.report_dir)
    print(path)
    return 0


def feedback(args: argparse.Namespace, settings, conn) -> int:
    del settings
    total = 0
    total += db.add_feedback(conn, args.like, signal=1, note=args.note)
    total += db.add_feedback(conn, args.dislike, signal=-1, note=args.note)
    total += db.add_feedback(conn, args.save, signal=2, note=args.note, tags=["saved"])
    total += db.add_feedback(conn, args.hide, signal=-2, note=args.note, tags=["hidden"])
    boosted = db.add_profile_terms(conn, args.more_topic, delta=1.25)
    downranked = db.add_profile_terms(conn, args.less_topic, delta=-1.25)
    print(f"Recorded {total} repo feedback items, boosted {boosted} terms, downranked {downranked} terms.")
    return 0


def import_repo(args: argparse.Namespace, settings, conn) -> int:
    imported = []
    try:
        for full_name in args.repos:
            repo = fetch_repository(full_name, token=settings.github_token)
            db.upsert_repositories(conn, [repo])
            stored = db.load_repository(conn, repo.full_name)
            if stored:
                imported.append(stored)
    except GitHubApiError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    scored = score_all_repositories(conn, imported, settings)
    stats = db.repository_stats(conn)
    for item in scored:
        repo = item.repo
        print(f"{repo.full_name}")
        print(f"  score={item.total_score:.2f} heat={item.heat_score:.2f} growth={item.growth_score:.2f} interest={item.interest_score:.2f}")
        print(f"  stars={repo.stars:,} forks={repo.forks:,} language={repo.language or '未知'}")
        print(f"  first_seen={repo.first_seen_at or '未知'} last_seen={repo.last_seen_at or '未知'}")
    print(
        "Stats: "
        f"repos={stats['total_repositories']}, "
        f"marked={stats['marked_repositories']}, "
        f"top_languages={stats['top_languages']}"
    )
    print(f"GitHub auth: {last_auth_source()}")
    return 0


def run(args: argparse.Namespace, settings, conn) -> int:
    try:
        path = run_collection(settings, conn, limit=args.limit)
        print(path)
        print(f"GitHub auth: {last_auth_source()}")
        return 0
    except GitHubApiError as exc:
        print(str(exc), file=sys.stderr)
        return 2


def run_collection(settings, conn, limit: int = 300, progress_callback=None):
    queries = plan_collection_queries(settings, conn)
    total_steps = len(queries) + 2
    log = _start_collection_text_log(settings, mode="run", queries=queries)

    def emit(step: int, message: str) -> None:
        if progress_callback is not None:
            progress_callback(step, total_steps, message)

    def search_progress(done: int, total: int, query: str) -> None:
        if log is not None:
            log.append(f"search {done + 1}/{total}: {query}")
        emit(done, f"正在搜索（{done + 1}/{total}）：{query}")

    run_id = db.start_run(conn)
    try:
        repos = search_repositories(
            queries,
            per_page=settings.per_page,
            token=settings.github_token,
            progress_callback=search_progress,
        )
        emit(len(queries), f"已获取 {len(repos)} 个仓库，正在写入数据库…")
        count = db.upsert_repositories(conn, repos)
        emit(len(queries) + 1, "正在计算推荐分并生成报告…")
        recent = db.load_recent_repositories(conn, limit=limit)
        scored = score_repositories(conn, recent, settings)
        path = write_markdown_report(scored, settings.report_dir)
        emit(total_steps, "采集完成")
        if log is not None:
            log.finish("ok", repos_seen=count, report_path=str(path), auth=last_auth_source())
        db.finish_run(conn, run_id, status="ok", repos_seen=count, report_path=str(path))
        return path
    except GitHubApiError as exc:
        if log is not None:
            log.finish("error", repos_seen=0, auth=last_auth_source(), message=str(exc))
        db.finish_run(conn, run_id, status="error", repos_seen=0, message=str(exc))
        raise
    except Exception as exc:
        if log is not None:
            log.finish(
                "error",
                repos_seen=0,
                auth=last_auth_source(),
                message=f"{type(exc).__name__}: {exc}",
            )
        db.finish_run(conn, run_id, status="error", repos_seen=0, message=str(exc))
        raise


class CollectionTextLog:
    def __init__(self, path: Path, root: Path) -> None:
        self.path = path
        self.root = root

    def append(self, line: str) -> None:
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{timestamp}] {line}\n")

    def finish(
        self,
        status: str,
        *,
        repos_seen: int,
        auth: str,
        report_path: str = "",
        message: str = "",
    ) -> None:
        self.append(f"status: {status}")
        self.append(f"repos_seen: {repos_seen}")
        self.append(f"github_auth: {auth}")
        if report_path:
            self.append(f"report_path: {self.display_path(report_path)}")
        if message:
            self.append(f"message: {message}")

    def display_path(self, path: str | Path) -> str:
        return _display_path(self.root, path)


def _start_collection_text_log(settings, *, mode: str, queries: list[str]) -> CollectionTextLog | None:
    try:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        log_path = settings.project_root / "logs" / f"collection-{timestamp}.txt"
        log = CollectionTextLog(log_path, settings.project_root)
        log.append("GitHub Radar collection started")
        log.append(f"mode: {mode}")
        log.append("config_root: .")
        log.append(f"db_path: {_display_path(settings.project_root, settings.db_path)}")
        log.append(f"per_page: {settings.per_page}")
        log.append(f"min_stars: {settings.min_stars}")
        log.append(f"created_within_days: {settings.created_within_days}")
        log.append(f"pushed_within_days: {settings.pushed_within_days}")
        log.append(f"allow_interest_queries: {settings.allow_interest_queries}")
        log.append(f"languages: {', '.join(settings.languages) if settings.languages else '(all)'}")
        log.append(f"query_count: {len(queries)}")
        log.append("queries:")
        for index, query in enumerate(queries, start=1):
            log.append(f"  {index}. {query}")
        return log
    except OSError as exc:
        print(f"Warning: failed to create collection log: {exc}", file=sys.stderr)
        return None


def _display_path(root: Path, path: str | Path) -> str:
    path = Path(path)
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
