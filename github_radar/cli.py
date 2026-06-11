from __future__ import annotations

import argparse
import sys

from . import db
from .github_api import GitHubApiError, fetch_repository, search_repositories
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
    queries = settings.expanded_queries()
    if args.dry_run:
        for query in queries:
            print(query)
        return 0

    repos = search_repositories(queries, per_page=settings.per_page)
    count = db.upsert_repositories(conn, repos)
    print(f"Collected {count} repositories into {settings.db_path}")
    return 0


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
            repo = fetch_repository(full_name)
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
    return 0


def run(args: argparse.Namespace, settings, conn) -> int:
    try:
        path = run_collection(settings, conn, limit=args.limit)
        print(path)
        return 0
    except GitHubApiError as exc:
        print(str(exc), file=sys.stderr)
        return 2


def run_collection(settings, conn, limit: int = 300):
    run_id = db.start_run(conn)
    try:
        repos = search_repositories(settings.expanded_queries(), per_page=settings.per_page)
        count = db.upsert_repositories(conn, repos)
        recent = db.load_recent_repositories(conn, limit=limit)
        scored = score_repositories(conn, recent, settings)
        path = write_markdown_report(scored, settings.report_dir)
        db.finish_run(conn, run_id, status="ok", repos_seen=count, report_path=str(path))
        return path
    except GitHubApiError as exc:
        db.finish_run(conn, run_id, status="error", repos_seen=0, message=str(exc))
        raise


if __name__ == "__main__":
    raise SystemExit(main())
