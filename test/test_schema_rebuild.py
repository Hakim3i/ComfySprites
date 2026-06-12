"""Stale SQLite files are rebuilt when mapped columns drift."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from webapp.db.models import SCHEMA_VERSION
from webapp.db.session import init_schema


@pytest.fixture
def stale_styles_db(tmp_path: Path) -> Path:
    """Legacy styles table used ``name`` instead of ``display_name``."""
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE styles ("
        "id INTEGER PRIMARY KEY, slug TEXT UNIQUE, name TEXT, filename TEXT DEFAULT '')"
    )
    conn.execute(
        "INSERT INTO styles (slug, name, filename) VALUES ('old', 'Old Style', 'old.safetensors')"
    )
    conn.commit()
    conn.close()
    return db_path


def test_init_schema_rebuilds_legacy_styles_table(stale_styles_db: Path):
    import webapp.db.session as db_session

    db_session._engine = None
    db_session._Session = None

    engine = init_schema(stale_styles_db)
    insp_cols = {
        row[1]
        for row in engine.connect().exec_driver_sql("PRAGMA table_info(styles)").fetchall()
    }
    assert "display_name" in insp_cols
    assert "name" not in insp_cols

    version = engine.connect().exec_driver_sql(
        "SELECT version FROM _schema_meta WHERE key = 'schema'"
    ).scalar()
    assert version == SCHEMA_VERSION
