from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .models import Feedback, Repository


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS repositories (
            full_name TEXT PRIMARY KEY,
            html_url TEXT NOT NULL,
            description TEXT NOT NULL,
            language TEXT NOT NULL,
            stars INTEGER NOT NULL,
            forks INTEGER NOT NULL,
            watchers INTEGER NOT NULL,
            open_issues INTEGER NOT NULL,
            topics_json TEXT NOT NULL,
            owner TEXT NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            pushed_at TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            last_query TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            stars INTEGER NOT NULL,
            forks INTEGER NOT NULL,
            watchers INTEGER NOT NULL,
            FOREIGN KEY (full_name) REFERENCES repositories(full_name)
        );

        CREATE INDEX IF NOT EXISTS idx_snapshots_repo_time
        ON snapshots(full_name, captured_at);

        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            signal INTEGER NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            tags_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            FOREIGN KEY (full_name) REFERENCES repositories(full_name)
        );

        CREATE TABLE IF NOT EXISTS repository_tags (
            full_name TEXT NOT NULL,
            tag TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (full_name, tag),
            FOREIGN KEY (full_name) REFERENCES repositories(full_name)
        );

        CREATE INDEX IF NOT EXISTS idx_repository_tags_tag
        ON repository_tags(tag);

        CREATE TABLE IF NOT EXISTS profile_terms (
            term TEXT PRIMARY KEY,
            weight REAL NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS run_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            repos_seen INTEGER NOT NULL DEFAULT 0,
            report_path TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            message TEXT NOT NULL DEFAULT ''
        );
        """
    )
    conn.commit()


def upsert_repositories(conn: sqlite3.Connection, repos: Iterable[Repository]) -> int:
    now = _now()
    rows = list(repos)
    for repo in rows:
        conn.execute(
            """
            INSERT INTO repositories (
                full_name, html_url, description, language, stars, forks, watchers,
                open_issues, topics_json, owner, name, created_at, pushed_at,
                first_seen_at, last_seen_at, last_query
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(full_name) DO UPDATE SET
                html_url = excluded.html_url,
                description = excluded.description,
                language = excluded.language,
                stars = excluded.stars,
                forks = excluded.forks,
                watchers = excluded.watchers,
                open_issues = excluded.open_issues,
                topics_json = excluded.topics_json,
                owner = excluded.owner,
                name = excluded.name,
                created_at = excluded.created_at,
                pushed_at = excluded.pushed_at,
                last_seen_at = excluded.last_seen_at,
                last_query = excluded.last_query
            """,
            (
                repo.full_name,
                repo.html_url,
                repo.description,
                repo.language,
                repo.stars,
                repo.forks,
                repo.watchers,
                repo.open_issues,
                json.dumps(repo.topics, ensure_ascii=True),
                repo.owner,
                repo.name,
                repo.created_at,
                repo.pushed_at,
                now,
                now,
                repo.query,
            ),
        )
        conn.execute(
            """
            INSERT INTO snapshots (full_name, captured_at, stars, forks, watchers)
            VALUES (?, ?, ?, ?, ?)
            """,
            (repo.full_name, now, repo.stars, repo.forks, repo.watchers),
        )
    conn.commit()
    return len(rows)


def load_recent_repositories(conn: sqlite3.Connection, *, limit: int = 500) -> list[Repository]:
    rows = conn.execute(
        """
        SELECT *
        FROM repositories
        ORDER BY last_seen_at DESC, stars DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [_repo_from_row(row) for row in rows]


def load_repository(conn: sqlite3.Connection, full_name: str) -> Repository | None:
    row = conn.execute(
        """
        SELECT *
        FROM repositories
        WHERE lower(full_name) = lower(?)
        LIMIT 1
        """,
        (full_name,),
    ).fetchone()
    return _repo_from_row(row) if row else None


def repository_stats(conn: sqlite3.Connection) -> dict[str, object]:
    total = int(conn.execute("SELECT count(*) FROM repositories").fetchone()[0])
    marked = int(
        conn.execute(
            """
            SELECT count(DISTINCT full_name)
            FROM feedback
            WHERE tags_json != '[]'
            """
        ).fetchone()[0]
    )
    languages = conn.execute(
        """
        SELECT coalesce(nullif(language, ''), '未知') AS language, count(*) AS count
        FROM repositories
        GROUP BY coalesce(nullif(language, ''), '未知')
        ORDER BY count DESC, language ASC
        LIMIT 5
        """
    ).fetchall()
    feedback = conn.execute(
        """
        SELECT tags_json, count(*) AS count
        FROM feedback
        GROUP BY tags_json
        """
    ).fetchall()
    feedback_counts: dict[str, int] = {}
    for row in feedback:
        for tag in json.loads(row["tags_json"] or "[]"):
            feedback_counts[tag] = feedback_counts.get(tag, 0) + int(row["count"])
    tag_rows = conn.execute(
        """
        SELECT tag, count(*) AS count
        FROM repository_tags
        GROUP BY tag
        ORDER BY tag ASC
        """
    ).fetchall()
    return {
        "total_repositories": total,
        "marked_repositories": marked,
        "tagged_repositories": int(
            conn.execute("SELECT count(DISTINCT full_name) FROM repository_tags").fetchone()[0]
        ),
        "top_languages": [(row["language"], int(row["count"])) for row in languages],
        "feedback_counts": feedback_counts,
        "tag_counts": {row["tag"]: int(row["count"]) for row in tag_rows},
    }


def add_feedback(
    conn: sqlite3.Connection,
    full_names: Iterable[str],
    *,
    signal: int,
    note: str = "",
    tags: Iterable[str] = (),
) -> int:
    now = _now()
    names = [name.strip() for name in full_names if name.strip()]
    tag_json = json.dumps([tag.strip().lower() for tag in tags if tag.strip()], ensure_ascii=True)
    for full_name in names:
        conn.execute(
            """
            INSERT INTO feedback (full_name, signal, note, tags_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (full_name, signal, note, tag_json, now),
        )
    conn.commit()
    return len(names)


def add_profile_terms(conn: sqlite3.Connection, terms: Iterable[str], *, delta: float) -> int:
    now = _now()
    clean_terms = sorted({term.strip().lower() for term in terms if term.strip()})
    for term in clean_terms:
        conn.execute(
            """
            INSERT INTO profile_terms (term, weight, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(term) DO UPDATE SET
                weight = weight + excluded.weight,
                updated_at = excluded.updated_at
            """,
            (term, delta, now),
        )
    conn.commit()
    return len(clean_terms)


def load_feedback(conn: sqlite3.Connection) -> list[Feedback]:
    rows = conn.execute(
        """
        SELECT full_name, signal, note, tags_json, created_at
        FROM feedback
        ORDER BY created_at DESC
        """
    ).fetchall()
    return [
        Feedback(
            full_name=row["full_name"],
            signal=int(row["signal"]),
            note=row["note"],
            tags=json.loads(row["tags_json"] or "[]"),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
        for row in rows
    ]


def add_repository_tags(
    conn: sqlite3.Connection,
    full_name: str,
    tags: Iterable[str],
) -> int:
    now = _now()
    clean_tags = _clean_tags(tags)
    for tag in clean_tags:
        conn.execute(
            """
            INSERT OR IGNORE INTO repository_tags (full_name, tag, created_at)
            VALUES (?, ?, ?)
            """,
            (full_name, tag, now),
        )
    conn.commit()
    return len(clean_tags)


def remove_repository_tag(conn: sqlite3.Connection, full_name: str, tag: str) -> bool:
    clean = _clean_tag(tag)
    if not clean:
        return False
    cursor = conn.execute(
        "DELETE FROM repository_tags WHERE full_name = ? AND tag = ?",
        (full_name, clean),
    )
    conn.commit()
    return cursor.rowcount > 0


def load_repository_tags(conn: sqlite3.Connection) -> dict[str, list[str]]:
    rows = conn.execute(
        """
        SELECT full_name, tag
        FROM repository_tags
        ORDER BY tag ASC
        """
    ).fetchall()
    tags_by_repo: dict[str, list[str]] = {}
    for row in rows:
        tags_by_repo.setdefault(row["full_name"], []).append(row["tag"])
    return tags_by_repo


def load_all_repository_tags(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT tag
        FROM repository_tags
        ORDER BY tag ASC
        """
    ).fetchall()
    return [row["tag"] for row in rows]


def load_profile_terms(conn: sqlite3.Connection) -> dict[str, float]:
    rows = conn.execute("SELECT term, weight FROM profile_terms").fetchall()
    return {row["term"]: float(row["weight"]) for row in rows}


def star_delta_since(conn: sqlite3.Connection, full_name: str, *, days: int = 7) -> int:
    latest = conn.execute(
        """
        SELECT stars
        FROM snapshots
        WHERE full_name = ?
        ORDER BY captured_at DESC
        LIMIT 1
        """,
        (full_name,),
    ).fetchone()
    if latest is None:
        return 0

    cutoff = (datetime.now(timezone.utc).timestamp() - days * 86400)
    cutoff_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat()
    earlier = conn.execute(
        """
        SELECT stars
        FROM snapshots
        WHERE full_name = ? AND captured_at <= ?
        ORDER BY captured_at DESC
        LIMIT 1
        """,
        (full_name, cutoff_iso),
    ).fetchone()
    if earlier is None:
        first = conn.execute(
            """
            SELECT stars
            FROM snapshots
            WHERE full_name = ?
            ORDER BY captured_at ASC
            LIMIT 1
            """,
            (full_name,),
        ).fetchone()
        earlier_stars = int(first["stars"]) if first else int(latest["stars"])
    else:
        earlier_stars = int(earlier["stars"])
    return max(0, int(latest["stars"]) - earlier_stars)


def start_run(conn: sqlite3.Connection) -> int:
    cursor = conn.execute(
        "INSERT INTO run_log (started_at, status) VALUES (?, ?)",
        (_now(), "running"),
    )
    conn.commit()
    return int(cursor.lastrowid)


def finish_run(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    status: str,
    repos_seen: int,
    report_path: str = "",
    message: str = "",
) -> None:
    conn.execute(
        """
        UPDATE run_log
        SET finished_at = ?, status = ?, repos_seen = ?, report_path = ?, message = ?
        WHERE id = ?
        """,
        (_now(), status, repos_seen, report_path, message, run_id),
    )
    conn.commit()


def _repo_from_row(row: sqlite3.Row) -> Repository:
    return Repository(
        full_name=row["full_name"],
        html_url=row["html_url"],
        description=row["description"],
        language=row["language"],
        stars=int(row["stars"]),
        forks=int(row["forks"]),
        watchers=int(row["watchers"]),
        open_issues=int(row["open_issues"]),
        topics=json.loads(row["topics_json"] or "[]"),
        owner=row["owner"],
        name=row["name"],
        created_at=row["created_at"],
        pushed_at=row["pushed_at"],
        first_seen_at=row["first_seen_at"],
        last_seen_at=row["last_seen_at"],
        query=row["last_query"],
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean_tags(tags: Iterable[str]) -> list[str]:
    cleaned = {_clean_tag(tag) for tag in tags}
    cleaned.discard("")
    return sorted(cleaned)


def _clean_tag(tag: str) -> str:
    return tag.strip().lower()
