import sqlite3
from pathlib import Path

from app.config import DB_PATH

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS universities (
    name TEXT PRIMARY KEY,
    is_kyutei BOOLEAN DEFAULT 0,
    is_national BOOLEAN DEFAULT 0,
    is_private BOOLEAN DEFAULT 0
);

CREATE TABLE IF NOT EXISTS passages (
    id TEXT PRIMARY KEY,
    university TEXT NOT NULL,
    year INTEGER NOT NULL,
    faculty TEXT DEFAULT '',
    question_number TEXT NOT NULL,
    passage_index INTEGER DEFAULT 1,

    text_type TEXT NOT NULL,
    text_style TEXT,
    word_count INTEGER,

    source_title TEXT,
    source_author TEXT,
    source_year INTEGER,

    genre_main TEXT NOT NULL,
    genre_sub TEXT DEFAULT '',
    theme TEXT DEFAULT '',

    has_jp_written BOOLEAN DEFAULT 0,
    has_en_written BOOLEAN DEFAULT 0,
    has_summary BOOLEAN DEFAULT 0,
    comp_type TEXT DEFAULT 'none',

    reviewed BOOLEAN DEFAULT 0,
    notes TEXT DEFAULT '',
    extracted_at TEXT DEFAULT (datetime('now')),

    UNIQUE(university, year, question_number, passage_index),
    FOREIGN KEY (university) REFERENCES universities(name)
);

CREATE INDEX IF NOT EXISTS idx_passages_university ON passages(university);
CREATE INDEX IF NOT EXISTS idx_passages_year ON passages(year);
CREATE INDEX IF NOT EXISTS idx_passages_genre ON passages(genre_main);

CREATE TABLE IF NOT EXISTS analysis_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    error_message TEXT,
    passages_created INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT
);
"""

SEED_UNIVERSITIES = [
    ("東京大", 1, 1, 0),
    ("京都大", 1, 1, 0),
    ("東北大", 1, 1, 0),
    ("大阪大", 1, 1, 0),
    ("名古屋大", 1, 1, 0),
    ("九州大", 1, 1, 0),
    ("北海道大", 1, 1, 0),
    ("一橋大", 0, 1, 0),
    ("東京工業大", 0, 1, 0),
    ("神戸大", 0, 1, 0),
    ("筑波大", 0, 1, 0),
    ("広島大", 0, 1, 0),
    ("千葉大", 0, 1, 0),
    ("金沢大", 0, 1, 0),
    ("岡山大", 0, 1, 0),
]


def get_connection() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(SCHEMA_SQL)
        for name, is_kyutei, is_national, is_private in SEED_UNIVERSITIES:
            conn.execute(
                "INSERT OR IGNORE INTO universities (name, is_kyutei, is_national, is_private) VALUES (?, ?, ?, ?)",
                (name, is_kyutei, is_national, is_private),
            )
        conn.commit()
    finally:
        conn.close()
