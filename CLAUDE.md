# 入試問題分析システム

## プロジェクト概要
国公立大学の入試英語問題（OCR済みMD形式）を Claude API で自動分類し、ダッシュボードで可視化・編集するWebアプリ。

## 技術スタック
- **バックエンド**: FastAPI (Python 3.12)
- **フロントエンド**: HTMX + Jinja2 + Chart.js
- **DB**: SQLite (単一ファイル `data/exam.db`)
- **分類API**: Claude Sonnet (`claude-sonnet-4-20250514`)、2回分割呼び出し
- **デプロイ**: Fly.io (東京リージョン nrt)

## ディレクトリ構成
```
exam-text-classifier/
├── app/                    # FastAPIアプリケーション
│   ├── main.py             # エントリポイント、認証ミドルウェア
│   ├── config.py           # 環境変数、定数定義
│   ├── db.py               # SQLite接続、スキーマ、シードデータ
│   ├── parser.py           # MDファイルパーサー
│   ├── classifier.py       # Claude API呼び出し
│   ├── prompts.py          # プロンプト定義
│   └── routers/            # エンドポイント群
│       ├── upload.py       # アップロード・解析・レビューリスト
│       ├── passages.py     # CRUD・インライン編集・手動追加・カラムフィルター
│       ├── dashboard.py    # 集計・グラフデータ
│       ├── export.py       # CSV/JSON/DBエクスポート
│       └── universities.py # 大学分類・地域設定管理
├── templates/              # Jinja2テンプレート
│   ├── base.html
│   ├── index.html          # ダッシュボード（7タブ）
│   ├── login.html
│   └── partials/           # HTMXフラグメント
├── static/style.css
├── data/                   # DB・アップロードファイル保存先
├── tests/                  # pytest
├── Dockerfile
└── fly.toml
```

## 開発コマンド
```bash
# 依存インストール
pip install -r requirements.txt

# ローカル起動
uvicorn app.main:app --reload

# テスト実行
python -m pytest tests/ -v

# Fly.ioデプロイ
fly deploy
```

## 環境変数 (.env)
```
ANTHROPIC_API_KEY=sk-ant-xxxxx      # 必須: Claude API キー
ADMIN_PASSWORD_HASH=                 # 任意: bcryptハッシュ（空なら認証なし）
SECRET_KEY=change-me-in-production   # 任意: セッション署名キー
DB_PATH=./data/exam.db               # DB保存先
```

## MDパーサーの注意点
- 京都大: `university: (不明)`, `year: 令和7年度` → ファイル名フォールバック
- 東京大: `# Question 1 (Continued)` → 前の大問にマージ
- 東京大: 1つのQuestionに複数の`## Text`がある場合は連結（Q1の(A)(B)対応）
- 大阪大: `(A)/(B)` 分割 → 別パッセージとして抽出
- 九州大: `# Question [1]` → 角括弧付き番号に対応
- 大阪大（外国語）: `university: 大阪大（外国語）` → 大学名と学部に分離、IDに学部を含める
- `## Text`が空（`[ ]`等）の場合、`## Data` → `## Instructions`の順にフォールバック
- 設問分析には全`## Instructions` + `## Data` + `## Questions`を結合して送信（要約指示・英作文指示も検出可能に）

## text_type 分類（4種別）
- `long_reading`: 長文読解（200語以上 + 内容理解問題）
- `short_translation`: 短文和訳（英→日のみ）
- `composition`: 英作文（和文英訳・自由英作文・グラフ記述）
- `listening`: リスニング（放送・聞き取り問題）

## 設問分析フィールド（5分類 + 視覚情報）
- `has_jp_translation`: 和訳問題
- `has_jp_explanation`: 日本語での説明・記述
- `has_en_explanation`: 英語での説明・記述
- `has_jp_summary`: 日本語での要約
- `has_en_summary`: 英語での要約
- `has_visual_info` / `visual_info_type`: 英作文中の視覚情報（表・グラフ・イラスト等）

## データ管理
- 全データ削除: `POST /api/passages/delete-all`
- 年度・大学別削除: `DELETE /api/passages?year=&university=`
- 手動データ追加: `POST /api/passages/manual`
- "その他"サブカテゴリ一括再分類: `POST /api/passages/reclassify-other`
- プロンプトやパーサー修正後は全削除→再アップロードが必要（`INSERT OR IGNORE`のため）

## data/フォルダ
- OneDriveへのシンボリックリンク（`C:\Users\yoshi\OneDrive\DO_NOT_CHANGE_NAME`）
- 自宅・職場PC間のDB同期に使用。同時起動禁止。
- 入試問題MDデータは `data/input_md/` に配置（gitには含めない）

## ジャンル分類スキーム（10カテゴリ）
科学・技術 / 医療・健康 / 心理・行動 / 教育・学習 / 環境・自然 / 社会・文化 / 経済・ビジネス / 歴史・哲学 / 言語・コミュニケーション / その他

## コーディング規約
- テスト実行は変更後に必ず行う: `python -m pytest tests/ -v`
- 入試問題MDデータは `../input/` に配置（gitには含めない）
- DBスキーマ変更時は `db.py` の `SCHEMA_SQL` を更新し、`init_db()` の冪等性を維持
