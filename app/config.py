import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "data" / "exam.db"))
INPUT_MD_DIR = str(BASE_DIR / "data" / "input_md")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-6"
CLAUDE_MAX_TOKENS = 300
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

TEXT_TYPE_LIST = ["long_reading", "short_translation", "composition"]

TEXT_STYLE_LIST = [
    "説明文",
    "論説文",
    "ニュース・レポート",
    "エッセイ・評論",
    "物語文",
]

COMP_TYPE_LIST = ["none", "和文英訳", "自由英作文"]

VISUAL_INFO_TYPE_LIST = ["なし", "グラフ", "表", "イラスト", "写真", "地図"]
