# 入試問題分析システム

## プロジェクト概要
国公立大学の入試英語問題（OCR済みMD形式）を Claude API で自動分類し、ダッシュボードで可視化・編集するWebアプリ。

## 技術スタック
- **バックエンド**: FastAPI (Python 3.12)
- **フロントエンド**: HTMX + Jinja2 + Chart.js
- **DB**: SQLite (単一ファイル `data/exam.db`)
- **分類API**: 大学クラスに応じてモデルを自動選択（統合プロンプトで1回呼び出し）
  - 旧帝大・難関大・準難関大 → Claude Opus (`claude-opus-4-6`)
  - その他 → Claude Sonnet (`claude-sonnet-4-6`)
- **デプロイ**: Fly.io (東京リージョン nrt)

## ディレクトリ構成
```
exam-analyzer/
├── app/                    # FastAPIアプリケーション
│   ├── main.py             # エントリポイント、認証ミドルウェア
│   ├── auth.py             # ロールチェック（is_student）
│   ├── config.py           # 環境変数、定数定義、モデル選択設定
│   ├── db.py               # SQLite接続、スキーマ、シードデータ
│   ├── parser.py           # MDファイルパーサー
│   ├── classifier.py       # Claude API呼び出し（統合プロンプト、モデル自動選択）
│   ├── prompts.py          # プロンプト定義（統合 + 旧互換）
│   ├── models.py           # Pydanticモデル（ClassificationResult等）
│   └── routers/            # エンドポイント群
│       ├── upload.py       # アップロード・解析・レビューリスト
│       ├── passages.py     # CRUD・インライン編集・手動追加・カラムフィルター
│       ├── dashboard.py    # 集計・グラフデータ（7エンドポイント）
│       ├── export.py       # CSV/JSON/DBエクスポート
│       └── universities.py # 大学分類・地域設定管理
├── templates/              # Jinja2テンプレート
│   ├── base.html
│   ├── index.html          # 分析画面（7タブ、モバイルは4タブ統合）
│   ├── manage.html         # 管理画面（データ一覧・編集・削除）
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

## text_type 分類（5種別）
- `long_reading`: 長文読解（200語以上 + 内容理解問題）
- `short_translation`: 短文和訳（英→日のみ）
- `composition`: 英作文（和文英訳・自由英作文・グラフ記述）
- `others`: 語句整序、文法・語彙問題など
- `listening`: リスニング（放送・聞き取り問題）

## フィールド判定ルール（text_type別）

| text_type | word_count | text_style | genre/sub/theme |
|---|---|---|---|
| long_reading | 判定 | 判定 | 判定 |
| short_translation | 判定 | 判定 | 判定 |
| composition(和英含む) | NULL | 判定(空白可) | 判定(空白可) |
| composition(自英のみ) | NULL | 空白 | 判定(空白可) |
| others | NULL | 空白 | 空白 |
| listening | NULL | 空白 | 空白 |

## 設問分析フィールド（5分類 + 視覚情報）
- `has_jp_translation`: 和訳問題
- `has_jp_explanation`: 日本語での説明・記述
- `has_en_explanation`: 英語での説明・記述
- `has_jp_summary`: 日本語での要約
- `has_en_summary`: 英語での要約
- `has_wabun_eiyaku`: 和文英訳
- `has_jiyu_eisakubun`: 自由英作文
- `has_visual_info` / `visual_info_type`: 英作文中の視覚情報（表・グラフ・イラスト等）

## 信頼度フラグ
- `low_confidence`: LLMが判定に自信のないフィールドがある場合true
- `low_confidence_fields`: 自信のないフィールド名のカンマ区切り文字列
- UI上で黄色背景 + フィールド名バッジで表示
- 語数(word_count)は警告対象から自動除外

## モデル選択（大学クラス別）
- `config.py` の `PREMIUM_UNIVERSITY_CLASSES` で制御
- 旧帝大・難関大・準難関大 → Opus（高精度）
- その他国立大・公立大・未設定 → Sonnet（コスト効率）
- `classifier.py` の `_select_model()` がDBの `university_class` を参照して決定

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

## ロールガード
- `app/auth.py` の `is_student(request)` で `BEHIND_PORTAL=true` かつ `X-Portal-Role: student` を判定
- studentロールは管理画面(`/manage`)・全書き込みAPI（POST/PUT/DELETE/reclassify）・DB出力を拒否
- スタンドアロン時（BEHIND_PORTAL未設定）はガード適用なし（自前bcrypt認証で全権限）

## 分析画面のタブ構成
- **デスクトップ（769px+）**: 7タブ（ダッシュボード / 長文統計 / 英作文統計 / 問題形式選択 / 大学間比較 / 大学別傾向 / 経年変化）
- **モバイル（768px以下）**: 4タブ統合（全体統計 / 問題形式 / 大学比較 / 大学詳細）
- Chart.js + chartjs-plugin-datalabels を全グラフで使用

## コーディング規約
- テスト実行は変更後に必ず行う: `python -m pytest tests/ -v`
- 入試問題MDデータは `data/input_md/` に配置（gitには含めない）
- DBスキーマ変更時は `db.py` の `SCHEMA_SQL` を更新し、`init_db()` の冪等性を維持
