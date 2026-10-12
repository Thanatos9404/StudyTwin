"""SQLite persistence for sources, knowledge units, topics, questions and learner state."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY, kind TEXT, title TEXT, filename TEXT, path TEXT,
  remote_url TEXT, license TEXT, attribution TEXT, meta TEXT, created_at REAL
);
CREATE TABLE IF NOT EXISTS units (
  id TEXT PRIMARY KEY, source_id TEXT, kind TEXT, ord INTEGER, text TEXT, loc TEXT, label TEXT,
  section TEXT, image TEXT, page_image TEXT, topic_id TEXT, subtopic_id TEXT, concepts TEXT, tokens INTEGER
);
CREATE INDEX IF NOT EXISTS units_source ON units(source_id);
CREATE TABLE IF NOT EXISTS unit_vecs (unit_id TEXT PRIMARY KEY, model TEXT, vec BLOB);
CREATE TABLE IF NOT EXISTS topics (
  id TEXT PRIMARY KEY, name TEXT, parent_id TEXT, description TEXT, key_concepts TEXT,
  prerequisites TEXT, ord INTEGER
);
CREATE TABLE IF NOT EXISTS questions (
  id TEXT PRIMARY KEY, topic_id TEXT, subtopic_id TEXT, type TEXT, difficulty INTEGER, stem TEXT,
  options TEXT, answer TEXT, tolerance REAL, explanation TEXT, misconceptions TEXT, unit_ids TEXT,
  verified INTEGER, verification TEXT, generator TEXT, origin TEXT, norm_hash TEXT, created_at REAL
);
CREATE INDEX IF NOT EXISTS questions_topic ON questions(topic_id);
CREATE TABLE IF NOT EXISTS students (
  id TEXT PRIMARY KEY, name TEXT, created_at REAL, intake TEXT, profile TEXT
);
CREATE TABLE IF NOT EXISTS mastery (
  student_id TEXT, topic_id TEXT, p REAL, n INTEGER, correct REAL, last_ts REAL, half_life REAL,
  PRIMARY KEY (student_id, topic_id)
);
CREATE TABLE IF NOT EXISTS mastery_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT, topic_id TEXT, ts REAL,
  p_before REAL, p_after REAL, event TEXT, ref TEXT
);
CREATE TABLE IF NOT EXISTS assessments (
  id TEXT PRIMARY KEY, student_id TEXT, kind TEXT, scope TEXT, question_ids TEXT,
  created_at REAL, finished_at REAL, report TEXT
);
CREATE TABLE IF NOT EXISTS attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, assessment_id TEXT, student_id TEXT, question_id TEXT,
  response TEXT, score REAL, feedback TEXT, ts REAL
);
CREATE TABLE IF NOT EXISTS chat (
  id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT, role TEXT, content TEXT, meta TEXT, ts REAL
);
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY, kind TEXT, status TEXT, progress REAL, message TEXT, result TEXT,
  created_at REAL, updated_at REAL
);
"""

JSON_COLS = {
    "meta", "loc", "concepts", "key_concepts", "prerequisites", "options", "misconceptions", "unit_ids",
    "verification", "intake", "profile", "scope", "question_ids", "report", "feedback", "result",
}

_local = threading.local()
_init_done: set[str] = set()
_init_lock = threading.Lock()


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:10]}"


def _connect() -> sqlite3.Connection:
    settings.ensure_dirs()
    path = str(settings.db_path)
    conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    with _init_lock:
        if path not in _init_done:
            conn.executescript(SCHEMA)
            conn.commit()
            _init_done.add(path)
    return conn


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    """A per-thread connection (re-created if the workspace path changed, e.g. in tests)."""
    key = str(settings.db_path)
    conn = getattr(_local, "conn", None)
    if conn is None or getattr(_local, "key", None) != key:
        conn = _connect()
        _local.conn, _local.key = conn, key
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def reset_connections() -> None:
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
    _local.conn = None
    _init_done.clear()


def _decode(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    out = dict(row)
    for k, v in out.items():
        if k in JSON_COLS and isinstance(v, str):
            try:
                out[k] = json.loads(v)
            except json.JSONDecodeError:
                pass
    return out


def _encode(values: dict[str, Any]) -> dict[str, Any]:
    return {k: (json.dumps(v, ensure_ascii=False) if k in JSON_COLS and v is not None and not isinstance(v, str) else v) for k, v in values.items()}


def insert(table: str, values: dict[str, Any], replace: bool = False) -> None:
    values = _encode(values)
    cols = ",".join(values)
    qs = ",".join("?" for _ in values)
    verb = "INSERT OR REPLACE" if replace else "INSERT"
    with db() as c:
        c.execute(f"{verb} INTO {table} ({cols}) VALUES ({qs})", tuple(values.values()))


def insert_many(table: str, rows: list[dict[str, Any]], replace: bool = False) -> None:
    if not rows:
        return
    rows = [_encode(r) for r in rows]
    cols = list(rows[0])
    verb = "INSERT OR REPLACE" if replace else "INSERT"
    with db() as c:
        c.executemany(
            f"{verb} INTO {table} ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
            [tuple(r.get(k) for k in cols) for r in rows],
        )


def update(table: str, key: str, key_val: Any, values: dict[str, Any]) -> None:
    values = _encode(values)
    sets = ",".join(f"{k}=?" for k in values)
    with db() as c:
        c.execute(f"UPDATE {table} SET {sets} WHERE {key}=?", (*values.values(), key_val))


def one(sql: str, params: tuple = ()) -> dict[str, Any] | None:
    with db() as c:
        return _decode(c.execute(sql, params).fetchone())


def many(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    with db() as c:
        return [_decode(r) for r in c.execute(sql, params).fetchall()]  # type: ignore[misc]


def execute(sql: str, params: tuple = ()) -> None:
    with db() as c:
        c.execute(sql, params)


# ---- jobs -----------------------------------------------------------------------------------

def job_create(kind: str) -> str:
    jid = new_id("job_")
    now = time.time()
    insert("jobs", {"id": jid, "kind": kind, "status": "queued", "progress": 0.0, "message": "Queued",
                    "result": None, "created_at": now, "updated_at": now})
    return jid


def job_update(jid: str, *, status: str | None = None, progress: float | None = None,
               message: str | None = None, result: Any = None) -> None:
    vals: dict[str, Any] = {"updated_at": time.time()}
    if status is not None:
        vals["status"] = status
    if progress is not None:
        vals["progress"] = round(float(progress), 3)
    if message is not None:
        vals["message"] = message
    if result is not None:
        vals["result"] = result
    update("jobs", "id", jid, vals)
