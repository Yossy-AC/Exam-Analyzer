"""DB初期化のテスト。"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.config as config
from app.db import get_connection, init_db


@pytest.fixture(autouse=True)
def tmp_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    config.DB_PATH = db_path
    yield db_path


def test_init_db_creates_tables():
    init_db()
    conn = get_connection()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    table_names = [t["name"] for t in tables]
    assert "passages" in table_names
    assert "universities" in table_names
    assert "analysis_jobs" in table_names
    conn.close()


def test_seed_universities():
    init_db()
    conn = get_connection()
    rows = conn.execute("SELECT * FROM universities WHERE is_kyutei = 1").fetchall()
    assert len(rows) == 7  # 旧帝大7校
    conn.close()


def test_idempotent_init():
    init_db()
    init_db()  # 2回実行してもエラーにならない
    conn = get_connection()
    rows = conn.execute("SELECT count(*) as cnt FROM universities").fetchone()
    assert rows["cnt"] >= 7
    conn.close()
