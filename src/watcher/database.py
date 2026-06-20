import hashlib
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import Circular

logger = logging.getLogger("watcher.database")


def get_db_path() -> Path:
    import os
    from dotenv import load_dotenv
    load_dotenv()
    return Path(os.getenv("DB_PATH", "./data/circulars/circulars.db"))


def init_db(db_path: Path | None = None) -> None:
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("""
        CREATE TABLE IF NOT EXISTS circulars (
            id           TEXT PRIMARY KEY,
            regulator    TEXT NOT NULL,
            title        TEXT NOT NULL,
            url          TEXT NOT NULL,
            date_issued  TEXT,
            effective_on TEXT,
            circular_no  TEXT,
            text_content TEXT,
            fetched_at   TEXT NOT NULL,
            ingested     INTEGER DEFAULT 0
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS watch_runs (
            run_id     TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            ended_at   TEXT,
            new_count  INTEGER DEFAULT 0,
            error      TEXT
        )
    """)
    con.commit()
    con.close()
    logger.info(f"Database initialized at {path}")


def make_circular_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def upsert_circular(circular: Circular, db_path: Path | None = None) -> bool:
    path = db_path or get_db_path()
    con = sqlite3.connect(path)
    existing = con.execute(
        "SELECT id FROM circulars WHERE id = ?", (circular.id,)
    ).fetchone()
    if existing:
        con.close()
        return False
    con.execute(
        """INSERT INTO circulars
           (id, regulator, title, url, date_issued, effective_on,
            circular_no, text_content, fetched_at, ingested)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
        (
            circular.id, circular.regulator, circular.title,
            circular.url, circular.date_issued, circular.effective_on,
            circular.circular_no, circular.text_content,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    con.commit()
    con.close()
    return True


def get_circulars(
    regulator: str | None = None,
    ingested: bool | None = None,
    limit: int = 20,
    db_path: Path | None = None,
) -> list[dict]:
    path = db_path or get_db_path()
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    query = "SELECT * FROM circulars WHERE 1=1"
    params: list[Any] = []
    if regulator:
        query += " AND regulator = ?"
        params.append(regulator.upper())
    if ingested is not None:
        query += " AND ingested = ?"
        params.append(1 if ingested else 0)
    query += " ORDER BY fetched_at DESC LIMIT ?"
    params.append(limit)
    rows = [dict(r) for r in con.execute(query, params).fetchall()]
    con.close()
    return rows


def mark_ingested(circular_id: str, db_path: Path | None = None) -> bool:
    path = db_path or get_db_path()
    con = sqlite3.connect(path)
    con.execute("UPDATE circulars SET ingested = 1 WHERE id = ?", (circular_id,))
    affected = con.total_changes
    con.commit()
    con.close()
    return affected > 0