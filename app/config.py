import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / ".env")
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "data" / "exam.db"))
INPUT_MD_DIR = str(BASE_DIR / "data" / "input_md")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "")
CLAUDE_MODEL_DEFAULT = "claude-sonnet-4-6"
CLAUDE_MODEL_PREMIUM = "claude-opus-4-6"
PREMIUM_UNIVERSITY_CLASSES = {"旧帝大", "難関大", "準難関大", "共通テスト"}
CLAUDE_MAX_TOKENS = 600
CLAUDE_TEMPERATURE = 0
CONCURRENT_LIMIT = 5

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "")
SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30 days

GENRE_MAIN_LIST = [
    "科学・技術",
    "医療・健康",
    "心理・行動",
    "教育・学習",
    "環境・自然",
    "社会・文化",
    "経済・ビジネス",
    "歴史・哲学",
    "言語・コミュニケーション",
    "その他",
]

TEXT_TYPE_LIST = ["long_reading", "short_translation", "composition", "others", "listening"]
TEXT_TYPE_LABELS = {
    "long_reading": "長文読解",
    "short_translation": "短文和訳",
    "composition": "英作文",
    "others": "その他",
    "listening": "リスニング",
}

TEXT_STYLE_LIST = [
    "説明文",
    "論説文",
    "ニュース・レポート",
    "エッセイ・評論",
    "物語文",
]


VISUAL_INFO_TYPE_LIST = ["なし", "グラフ", "表", "イラスト", "写真", "地図"]

UNIVERSITY_CLASS_LIST = ["旧帝大", "難関大", "準難関大", "その他国立大", "その他公立大", "共通テスト", "未設定"]

REGION_LIST = ["東北以北", "関東", "中部", "近畿", "中四国", "九州以南", "未設定"]

# 大学名 → (分類, 地域) のマッピング。新大学追加時はここに追記する。
UNIVERSITY_SETTINGS: dict[str, tuple[str, str]] = {
    "東京大": ("旧帝大", "関東"),
    "京都大": ("旧帝大", "近畿"),
    "東北大": ("旧帝大", "東北以北"),
    "大阪大": ("旧帝大", "近畿"),
    "名古屋大": ("旧帝大", "中部"),
    "九州大": ("旧帝大", "九州以南"),
    "北海道大": ("旧帝大", "東北以北"),
    # 以下、ユーザーが追記
    "共通テスト": ("共通テスト", ""),
}

# Gemini PDF変換
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL_NAME = "gemini-2.5-pro"
GEMINI_MAX_RETRIES = 5
GEMINI_RETRY_WAIT_SEC = 15
GEMINI_REQUEST_INTERVAL_SEC = 10
GEMINI_PROMPT_FILE = BASE_DIR / "data" / "gemini_prompt.md"
TEMP_PDF_DIR = str(BASE_DIR / "data" / "temp_pdf")
