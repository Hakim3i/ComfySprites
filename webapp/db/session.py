"""Database engine and session helpers."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import DB_PATH
from .models import Base, SCHEMA_VERSION

_engine: Engine | None = None
_Session: sessionmaker[Session] | None = None


def get_engine(db_path: Path | None = None) -> Engine:
    global _engine, _Session
    target = db_path or DB_PATH
    if _engine is not None and _engine.url.database == str(target):
        return _engine
    target.parent.mkdir(parents=True, exist_ok=True)
    _engine = create_engine(f"sqlite:///{target}", future=True, echo=False)

    @event.listens_for(_engine, "connect")
    def _on_connect(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    _Session = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


@contextmanager
def session_scope(db_path: Path | None = None) -> Iterator[Session]:
    if _Session is None:
        get_engine(db_path)
    assert _Session is not None
    s = _Session()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def _read_schema_version(engine: Engine) -> int | None:
    insp = inspect(engine)
    if "_schema_meta" not in insp.get_table_names():
        return None
    with engine.connect() as conn:
        row = conn.exec_driver_sql(
            "SELECT version FROM _schema_meta WHERE key = 'schema'"
        ).fetchone()
    return int(row[0]) if row else None


def _write_schema_version(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS _schema_meta ("
            "key TEXT PRIMARY KEY, version INTEGER NOT NULL)"
        )
        conn.exec_driver_sql(
            "INSERT OR REPLACE INTO _schema_meta (key, version) VALUES ('schema', ?)",
            (SCHEMA_VERSION,),
        )


def _schema_is_current(engine: Engine) -> bool:
    """True when every mapped table/column exists (v1: rebuild instead of migrate)."""
    insp = inspect(engine)
    table_names = insp.get_table_names()
    if not table_names:
        return True
    if _read_schema_version(engine) != SCHEMA_VERSION:
        return False
    for table_name, table in Base.metadata.tables.items():
        if table_name == "_schema_meta":
            continue
        if table_name not in table_names:
            return False
        db_cols = {c["name"] for c in insp.get_columns(table_name)}
        model_cols = {c.name for c in table.columns}
        if not model_cols.issubset(db_cols):
            return False
    return True


def _rebuild_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        Base.metadata.drop_all(bind=conn)
        conn.exec_driver_sql("DROP TABLE IF EXISTS _schema_meta")
    Base.metadata.create_all(engine)
    _write_schema_version(engine)


def init_schema(db_path: Path | None = None) -> Engine:
    engine = get_engine(db_path)
    if not _schema_is_current(engine):
        _rebuild_schema(engine)
    else:
        Base.metadata.create_all(engine)
        if _read_schema_version(engine) is None:
            _write_schema_version(engine)
    return engine
