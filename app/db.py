import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

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
    has_wabun_eiyaku BOOLEAN DEFAULT 0,
    has_jiyu_eisakubun BOOLEAN DEFAULT 0,

    has_jp_translation BOOLEAN DEFAULT 0,
    has_jp_explanation BOOLEAN DEFAULT 0,
    has_en_explanation BOOLEAN DEFAULT 0,
    has_jp_summary BOOLEAN DEFAULT 0,
    has_en_summary BOOLEAN DEFAULT 0,

    has_visual_info BOOLEAN DEFAULT 0,
    visual_info_type TEXT DEFAULT '',

    low_confidence BOOLEAN DEFAULT 0,
    low_confidence_fields TEXT DEFAULT '',

    reviewed BOOLEAN DEFAULT 0,
    notes TEXT DEFAULT '',
    extracted_at TEXT DEFAULT (datetime('now')),

    text_body TEXT DEFAULT '',
    avg_sentence_length REAL,
    cefr_j_beyond_rate REAL,
    cefr_j_profile TEXT DEFAULT '',
    ngsl_uncovered_rate REAL,
    nawl_rate REAL,
    target1900_coverage REAL,
    target1900_profile TEXT DEFAULT '',
    leap_coverage REAL,
    leap_profile TEXT DEFAULT '',

    cefr_level TEXT DEFAULT '',
    cefr_confidence TEXT DEFAULT '',
    cefr_score REAL,

    embedding BLOB,

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


def _migrate_db(conn: sqlite3.Connection) -> None:
    """既存DBに不足カラムを追加し、UNIQUE制約を更新する。"""
    # universitiesテーブルへのカラム追加
    uni_existing = {row[1] for row in conn.execute("PRAGMA table_info(universities)").fetchall()}
    for col, typedef in [("university_class", "TEXT DEFAULT ''"), ("region", "TEXT DEFAULT ''")]:
        if col not in uni_existing:
            conn.execute(f"ALTER TABLE universities ADD COLUMN {col} {typedef}")

    cursor = conn.execute("PRAGMA table_info(passages)")
    existing = {row[1] for row in cursor.fetchall()}
    migrations = [
        ("has_visual_info", "BOOLEAN DEFAULT 0"),
        ("visual_info_type", "TEXT DEFAULT ''"),
        ("has_jp_translation", "BOOLEAN DEFAULT 0"),
        ("has_jp_explanation", "BOOLEAN DEFAULT 0"),
        ("has_en_explanation", "BOOLEAN DEFAULT 0"),
        ("has_jp_summary", "BOOLEAN DEFAULT 0"),
        ("has_en_summary", "BOOLEAN DEFAULT 0"),
        ("low_confidence", "BOOLEAN DEFAULT 0"),
        ("low_confidence_fields", "TEXT DEFAULT ''"),
        # Phase A: テキスト格納 + 語彙分析
        ("text_body", "TEXT DEFAULT ''"),
        ("avg_sentence_length", "REAL"),
        ("cefr_j_beyond_rate", "REAL"),
        ("cefr_j_profile", "TEXT DEFAULT ''"),
        ("ngsl_uncovered_rate", "REAL"),
        ("nawl_rate", "REAL"),
        ("target1900_coverage", "REAL"),
        ("target1900_profile", "TEXT DEFAULT ''"),
        ("leap_coverage", "REAL"),
        ("leap_profile", "TEXT DEFAULT ''"),
        # Phase B: CEFR推定
        ("cefr_level", "TEXT DEFAULT ''"),
        ("cefr_confidence", "TEXT DEFAULT ''"),
        ("cefr_score", "REAL"),
        # Phase C: Embedding（将来）
        ("embedding", "BLOB"),
    ]
    for col, typedef in migrations:
        if col not in existing:
            conn.execute(f"ALTER TABLE passages ADD COLUMN {col} {typedef}")

    # comp_type → has_wabun_eiyaku / has_jiyu_eisakubun マイグレーション
    if "comp_type" in existing and "has_wabun_eiyaku" not in existing:
        conn.execute("ALTER TABLE passages ADD COLUMN has_wabun_eiyaku BOOLEAN DEFAULT 0")
        conn.execute("ALTER TABLE passages ADD COLUMN has_jiyu_eisakubun BOOLEAN DEFAULT 0")
        conn.execute("UPDATE passages SET has_wabun_eiyaku = 1 WHERE comp_type = '和文英訳'")
        conn.execute("UPDATE passages SET has_jiyu_eisakubun = 1 WHERE comp_type = '自由英作文'")
        conn.commit()

    # analysis_jobsテーブルへのカラム追加
    jobs_existing = {row[1] for row in conn.execute("PRAGMA table_info(analysis_jobs)").fetchall()}
    if "reviewed" not in jobs_existing:
        conn.execute("ALTER TABLE analysis_jobs ADD COLUMN reviewed BOOLEAN DEFAULT 0")
    if "source_type" not in jobs_existing:
        conn.execute("ALTER TABLE analysis_jobs ADD COLUMN source_type TEXT DEFAULT 'md'")
    if "current_step" not in jobs_existing:
        conn.execute("ALTER TABLE analysis_jobs ADD COLUMN current_step TEXT DEFAULT ''")

    # CEFRインデックス（cefr_levelカラム追加後に作成）
    if "cefr_level" in existing:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_passages_cefr ON passages(cefr_level)")

    # 旧UNIQUE制約（faculty含む）からの移行
    idx_info = conn.execute("PRAGMA index_list(passages)").fetchall()
    for idx in idx_info:
        idx_name = idx[1]
        cols = conn.execute(f"PRAGMA index_info({idx_name})").fetchall()
        col_names = [c[2] for c in cols]
        if col_names == ["university", "year", "faculty", "question_number", "passage_index"]:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS passages_new AS SELECT * FROM passages;
                DROP TABLE passages;
                CREATE TABLE passages (
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
                    has_wabun_eiyaku BOOLEAN DEFAULT 0,
    has_jiyu_eisakubun BOOLEAN DEFAULT 0,
                    has_jp_translation BOOLEAN DEFAULT 0,
                    has_jp_explanation BOOLEAN DEFAULT 0,
                    has_en_explanation BOOLEAN DEFAULT 0,
                    has_jp_summary BOOLEAN DEFAULT 0,
                    has_en_summary BOOLEAN DEFAULT 0,
                    has_visual_info BOOLEAN DEFAULT 0,
                    visual_info_type TEXT DEFAULT '',
                    low_confidence BOOLEAN DEFAULT 0,
                    low_confidence_fields TEXT DEFAULT '',
                    reviewed BOOLEAN DEFAULT 0,
                    notes TEXT DEFAULT '',
                    extracted_at TEXT DEFAULT (datetime('now')),
                    text_body TEXT DEFAULT '',
                    avg_sentence_length REAL,
                    cefr_j_beyond_rate REAL,
                    cefr_j_profile TEXT DEFAULT '',
                    ngsl_uncovered_rate REAL,
                    nawl_rate REAL,
                    target1900_coverage REAL,
                    target1900_profile TEXT DEFAULT '',
                    leap_coverage REAL,
                    leap_profile TEXT DEFAULT '',
                    cefr_level TEXT DEFAULT '',
                    cefr_confidence TEXT DEFAULT '',
                    cefr_score REAL,
                    embedding BLOB,
                    UNIQUE(university, year, question_number, passage_index),
                    FOREIGN KEY (university) REFERENCES universities(name)
                );
                INSERT INTO passages SELECT * FROM passages_new;
                DROP TABLE passages_new;
                CREATE INDEX IF NOT EXISTS idx_passages_university ON passages(university);
                CREATE INDEX IF NOT EXISTS idx_passages_year ON passages(year);
                CREATE INDEX IF NOT EXISTS idx_passages_genre ON passages(genre_main);
                CREATE INDEX IF NOT EXISTS idx_passages_cefr ON passages(cefr_level);
            """)
            break


def sync_university_settings(conn: sqlite3.Connection) -> None:
    """config.pyのUNIVERSITY_SETTINGSをuniversitiesテーブルに反映する。"""
    from app.config import UNIVERSITY_SETTINGS
    for name, (uni_class, region) in UNIVERSITY_SETTINGS.items():
        conn.execute(
            "INSERT OR IGNORE INTO universities (name, is_national) VALUES (?, 1)",
            (name,),
        )
        conn.execute(
            "UPDATE universities SET university_class=?, region=? WHERE name=?",
            (uni_class, region, name),
        )
    conn.commit()


def build_filter_where(
    year_mode: str = "all",
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    university_class: list = None,
    region: list = None,
    year_col: str = "year",
    university_col: str = "university",
) -> tuple[str, list]:
    """フィルター条件のSQL WHERE句追加部分とパラメーターを返す。"""
    clauses: list[str] = []
    params: list = []
    current_year = datetime.now().year

    if year_mode == "recent3":
        clauses.append(f"{year_col} >= ?"); params.append(current_year - 2)
    elif year_mode == "recent5":
        clauses.append(f"{year_col} >= ?"); params.append(current_year - 4)
    elif year_mode == "recent10":
        clauses.append(f"{year_col} >= ?"); params.append(current_year - 9)
    elif year_mode == "custom":
        if year_from:
            clauses.append(f"{year_col} >= ?"); params.append(year_from)
        if year_to:
            clauses.append(f"{year_col} <= ?"); params.append(year_to)

    if university_class or region:
        # "未設定" は DB 上は '' で保存されているため変換する
        university_class = ["" if v == "未設定" else v for v in (university_class or [])]
        region = ["" if v == "未設定" else v for v in (region or [])]
        sub_parts: list[str] = []
        sub_params: list = []
        if university_class:
            ph = ",".join("?" * len(university_class))
            sub_parts.append(f"university_class IN ({ph})")
            sub_params.extend(university_class)
        if region:
            ph = ",".join("?" * len(region))
            sub_parts.append(f"region IN ({ph})")
            sub_params.extend(region)
        clauses.append(
            f"{university_col} IN (SELECT name FROM universities WHERE {' AND '.join(sub_parts)})"
        )
        params.extend(sub_params)

    extra = (" AND " + " AND ".join(clauses)) if clauses else ""
    return extra, params


def get_all_universities(conn: sqlite3.Connection) -> list[dict]:
    """全大学を university_class, region と共に返す。未設定のものを先頭に並べる。"""
    rows = conn.execute(
        """SELECT name, university_class, region FROM universities
        ORDER BY (CASE WHEN university_class = '' OR region = '' THEN 0 ELSE 1 END), name"""
    ).fetchall()
    return [
        {
            "name": r["name"],
            "university_class": r["university_class"] or "",
            "region": r["region"] or "",
        }
        for r in rows
    ]


def update_university(conn: sqlite3.Connection, name: str, university_class: str, region: str) -> bool:
    """大学の分類・地域を更新する。大学が存在しない場合は False を返す。"""
    cur = conn.execute(
        "UPDATE universities SET university_class=?, region=? WHERE name=?",
        (university_class, region, name),
    )
    conn.commit()
    return cur.rowcount > 0


def rename_university(conn: sqlite3.Connection, old_name: str, new_name: str) -> bool:
    """大学名を変更する。passagesテーブルも連動更新。"""
    existing = conn.execute("SELECT 1 FROM universities WHERE name=?", (old_name,)).fetchone()
    if not existing:
        return False
    duplicate = conn.execute("SELECT 1 FROM universities WHERE name=?", (new_name,)).fetchone()
    if duplicate:
        raise ValueError(f"大学名 '{new_name}' は既に存在します")
    conn.execute("UPDATE passages SET university=? WHERE university=?", (new_name, old_name))
    conn.execute("UPDATE universities SET name=? WHERE name=?", (new_name, old_name))
    conn.commit()
    return True


def delete_university(conn: sqlite3.Connection, name: str) -> tuple[bool, int]:
    """大学を削除する。関連passagesも削除。削除した件数を返す。"""
    existing = conn.execute("SELECT 1 FROM universities WHERE name=?", (name,)).fetchone()
    if not existing:
        return False, 0
    cur = conn.execute("DELETE FROM passages WHERE university=?", (name,))
    deleted_passages = cur.rowcount
    conn.execute("DELETE FROM universities WHERE name=?", (name,))
    conn.commit()
    return True, deleted_passages


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(SCHEMA_SQL)
        _migrate_db(conn)
        for name, is_kyutei, is_national, is_private in SEED_UNIVERSITIES:
            conn.execute(
                "INSERT OR IGNORE INTO universities (name, is_kyutei, is_national, is_private) VALUES (?, ?, ?, ?)",
                (name, is_kyutei, is_national, is_private),
            )
        conn.commit()
        sync_university_settings(conn)
    finally:
        conn.close()
