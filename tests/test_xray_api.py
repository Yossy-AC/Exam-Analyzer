"""X-ray APIエンドポイントのテスト。"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.config as config
import app.db as db_mod
from app.xray_tokenizer import MAX_TEXT_LENGTH


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def tmp_db(tmp_path):
    """テスト用の一時DBを作成し、config と db モジュール両方のDB_PATHを差し替える。"""
    db_path = str(tmp_path / "test.db")
    original_config = config.DB_PATH
    original_db = db_mod.DB_PATH
    config.DB_PATH = db_path
    db_mod.DB_PATH = db_path
    db_mod.init_db()
    yield db_path
    config.DB_PATH = original_config
    db_mod.DB_PATH = original_db


@pytest.fixture
def client():
    """FastAPI TestClient。"""
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def seed_passage(tmp_db):
    """テスト用のlong_readingパッセージをDBに挿入する。"""
    conn = db_mod.get_connection()
    # 外部キー制約のため先に大学を挿入
    conn.execute(
        "INSERT OR IGNORE INTO universities (name, is_national) VALUES (?, ?)",
        ("テスト大", 1),
    )
    conn.execute(
        """INSERT INTO passages
           (id, university, year, question_number, passage_index,
            text_type, text_body, word_count, cefr_level, genre_main, copyright_omitted)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "test-001", "テスト大", 2025, "I", 1,
            "long_reading",
            "The global economy has changed significantly. Technology plays a central role.",
            12, "B2", "economy", 0,
        ),
    )
    conn.commit()
    conn.close()
    return "test-001"


# ---------------------------------------------------------------------------
# GET /api/xray/passages
# ---------------------------------------------------------------------------

class TestListPassages:
    def test_returns_list(self, client, seed_passage):
        resp = client.get("/api/xray/passages")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_passage_fields(self, client, seed_passage):
        resp = client.get("/api/xray/passages")
        p = resp.json()[0]
        assert p["id"] == "test-001"
        assert p["university"] == "テスト大"
        assert p["year"] == 2025
        assert p["questionNumber"] == "I"
        assert p["wordCount"] == 12

    def test_empty_db(self, client):
        """パッセージが無い場合は空リスト。"""
        resp = client.get("/api/xray/passages")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_excludes_non_long_reading(self, client, tmp_db):
        """long_reading以外は返さない。"""
        conn = db_mod.get_connection()
        conn.execute(
            "INSERT OR IGNORE INTO universities (name, is_national) VALUES (?, ?)",
            ("テスト大", 1),
        )
        conn.execute(
            """INSERT INTO passages
               (id, university, year, question_number, passage_index,
                text_type, text_body, word_count, genre_main, copyright_omitted)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("comp-001", "テスト大", 2025, "II", 1,
             "composition", "Write about...", 5, "", 0),
        )
        conn.commit()
        conn.close()
        resp = client.get("/api/xray/passages")
        ids = [p["id"] for p in resp.json()]
        assert "comp-001" not in ids

    def test_excludes_copyright_omitted(self, client, tmp_db):
        """著作権省略パッセージは返さない。"""
        conn = db_mod.get_connection()
        conn.execute(
            "INSERT OR IGNORE INTO universities (name, is_national) VALUES (?, ?)",
            ("テスト大", 1),
        )
        conn.execute(
            """INSERT INTO passages
               (id, university, year, question_number, passage_index,
                text_type, text_body, word_count, genre_main, copyright_omitted)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("copy-001", "テスト大", 2025, "III", 1,
             "long_reading", "omitted", 1, "", 1),
        )
        conn.commit()
        conn.close()
        resp = client.get("/api/xray/passages")
        ids = [p["id"] for p in resp.json()]
        assert "copy-001" not in ids


# ---------------------------------------------------------------------------
# GET /api/xray/passage/{id}
# ---------------------------------------------------------------------------

class TestGetPassage:
    def test_normal(self, client, seed_passage):
        resp = client.get(f"/api/xray/passage/{seed_passage}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "test-001"
        assert "paragraphs" in data
        assert isinstance(data["paragraphs"], list)
        assert len(data["paragraphs"]) >= 1

    def test_with_progress_params(self, client, seed_passage):
        resp = client.get(
            f"/api/xray/passage/{seed_passage}",
            params={"target1900_progress": 500, "leap_progress": 300},
        )
        assert resp.status_code == 200
        assert "paragraphs" in resp.json()

    def test_missing_id_returns_404(self, client):
        resp = client.get("/api/xray/passage/nonexistent-999")
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_student_rejected(self, client, seed_passage):
        """studentロールは403で拒否される（BEHIND_PORTAL=true時）。"""
        with patch.dict("os.environ", {"BEHIND_PORTAL": "true"}):
            resp = client.get(
                f"/api/xray/passage/{seed_passage}",
                headers={"X-Portal-Role": "student:test"},
            )
            assert resp.status_code == 403
            assert "error" in resp.json()

    def test_staff_allowed(self, client, seed_passage):
        """staffロールはアクセス可能。"""
        with patch.dict("os.environ", {"BEHIND_PORTAL": "true"}):
            resp = client.get(
                f"/api/xray/passage/{seed_passage}",
                headers={"X-Portal-Role": "staff"},
            )
            assert resp.status_code == 200

    def test_empty_text_body_returns_404(self, client, tmp_db):
        """text_bodyが空のパッセージは404。"""
        conn = db_mod.get_connection()
        conn.execute(
            "INSERT OR IGNORE INTO universities (name, is_national) VALUES (?, ?)",
            ("テスト大", 1),
        )
        conn.execute(
            """INSERT INTO passages
               (id, university, year, question_number, passage_index,
                text_type, text_body, word_count, genre_main, copyright_omitted)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("empty-001", "テスト大", 2025, "IV", 1,
             "long_reading", "", 0, "", 0),
        )
        conn.commit()
        conn.close()
        resp = client.get("/api/xray/passage/empty-001")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/xray/analyze
# ---------------------------------------------------------------------------

class TestAnalyze:
    def test_normal(self, client):
        resp = client.post(
            "/api/xray/analyze",
            json={"text": "The cat sat on the mat."},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "paragraphs" in data
        assert isinstance(data["paragraphs"], list)
        assert len(data["paragraphs"]) >= 1

    def test_with_progress(self, client):
        resp = client.post(
            "/api/xray/analyze",
            json={
                "text": "Technology changes society.",
                "target1900_progress": 800,
                "leap_progress": 500,
            },
        )
        assert resp.status_code == 200
        assert "paragraphs" in resp.json()

    def test_empty_text_returns_400(self, client):
        resp = client.post("/api/xray/analyze", json={"text": ""})
        assert resp.status_code == 400
        assert "error" in resp.json()

    def test_whitespace_only_returns_400(self, client):
        resp = client.post("/api/xray/analyze", json={"text": "   "})
        assert resp.status_code == 400
        assert "error" in resp.json()

    def test_too_long_text_returns_400(self, client):
        long_text = "a" * (MAX_TEXT_LENGTH + 1)
        resp = client.post("/api/xray/analyze", json={"text": long_text})
        assert resp.status_code == 400
        assert "error" in resp.json()
        assert str(MAX_TEXT_LENGTH) in resp.json()["error"]

    def test_exactly_max_length_ok(self, client):
        """ちょうどMAX_TEXT_LENGTHの長さは受け付ける。"""
        text = "a " * (MAX_TEXT_LENGTH // 2)
        text = text[:MAX_TEXT_LENGTH]
        resp = client.post("/api/xray/analyze", json={"text": text})
        assert resp.status_code == 200
