# 国公立大出題分析システム

## プロジェクト概要
国公立大学の入試英語問題（OCR済みMD形式）を Claude API で自動分類し、ダッシュボードで可視化・編集するWebアプリ。

## 技術スタック
- **バックエンド**: FastAPI (Python 3.12)
- **フロントエンド**: HTMX + Jinja2 + Chart.js
- **DB**: SQLite (単一ファイル `data/exam.db`)
- **分類API**: 大学クラスに応じてモデルを自動選択（統合プロンプトで1回呼び出し）
  - 旧帝大・難関大・準難関大 → Claude Opus (`claude-opus-4-6`)
  - その他 → Claude Sonnet (`claude-sonnet-4-6`)
- **CEFR推定**: Claude APIで長文のCEFRレベル（A2〜C2）を推定
- **Embedding**: Voyage AI (`voyage-4`, 1024次元) でテキスト類似度検索
- **語彙分析**: NLTK + 6語彙リスト（小中学語彙, CEFR-J, NGSL, NAWL, ターゲット1900, LEAP）
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
│   ├── prompts.py          # プロンプト定義（統合 + CEFR推定 + 旧互換）
│   ├── models.py           # Pydanticモデル（ClassificationResult等）
│   ├── vocab_analyzer.py   # 語彙分析（5リスト照合・平均文長・CEFR-J分布）
│   ├── embedding.py        # Voyage AI embedding（voyage-4, 1024次元）
│   ├── search.py           # 類似長文検索（コサイン類似度 / 特徴量フォールバック）
│   ├── wordlists/          # 語彙リストデータ（小中学語彙, CEFR-J, NGSL, NAWL, ターゲット1900, LEAP）
│   └── routers/            # エンドポイント群
│       ├── upload.py       # アップロード・解析・レビューリスト
│       ├── passages.py     # CRUD・インライン編集・手動追加・カラムフィルター
│       ├── dashboard.py    # 集計・グラフデータ（7エンドポイント）
│       ├── export.py       # CSV/JSON/DBエクスポート
│       ├── search.py       # 類似長文検索API・HTMXパーシャル
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

## 環境変数

中央管理: `Yossy/.env` に全サービスの環境変数を統合。`app/config.py` が `BASE_DIR.parent / ".env"` を参照。

使用する変数:
- `ANTHROPIC_API_KEY` — 必須: Claude API キー
- `VOYAGE_API_KEY` — 必須: Voyage AI API キー（embedding用）
- `ADMIN_PASSWORD_HASH` — 任意: bcryptハッシュ（空なら認証なし）
- `SECRET_KEY` — 任意: セッション署名キー
- `DB_PATH` — DB保存先（デフォルト: `./data/exam.db`）

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

## 語彙分析・CEFR推定・類似長文検索
- `vocab_analyzer.py`: long_readingのtext_bodyから語彙指標を自動計算（アップロード時）
  - CEFR-Jレベル別分布 + B2超過率、NGSL未カバー率、NAWL率、ターゲット1900/LEAPカバー率、平均文長
  - 単語帳プロファイル: 小中学語彙（`junior_high.txt`）をベースに加え、「小中学語彙+単語帳N番まで」の統合カバー率
- `classifier.py` の `estimate_cefr()`: Claude APIでCEFRレベル（A2〜C2）+ 信頼度を推定
  - 入力: text_body先頭3000字 + 語彙指標
  - cefr_score: A2=1, B1=2, B2=3, C1=3.5, C2=4（数値化）
- `embedding.py`: Voyage AI voyage-4モデル（1024次元）でtext_bodyをembedding化
  - アップロード時に自動生成、embedding IS NULLのパッセージは`backfill_embedding.py`で一括付与
  - Tier 1: 2,000 RPM / 8M TPM、無料枠200Mトークン
- `search.py`: 類似長文検索
  - embedding両方あり → コサイン類似度（ジャンル一致+0.02）
  - embedding片方なし → 特徴量ベース加重距離（cefr_score 50%, avg_sentence_length 20%, ngsl/nawl各15%）
- 一括更新スクリプト: `backfill_text.py`（text_body+語彙）、`backfill_cefr.py`（CEFR推定）、`backfill_embedding.py`（embedding付与）

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
- `app/auth.py` の `is_student(request)` で `BEHIND_PORTAL=true` かつ `X-Portal-Role` が `"student"` で始まるかを判定（`startswith("student")`）
- `student`・`student_exam`・`student_files` 全サブロールが student 扱い
- studentロールは管理画面(`/manage`)・全書き込みAPI（POST/PUT/DELETE/reclassify）・エクスポート（CSV/JSON/DB）を拒否
- スタンドアロン時（BEHIND_PORTAL未設定）はガード適用なし（自前bcrypt認証で全権限）

## 分析画面のタブ構成
- **デスクトップ（769px+）**: 7タブ（ダッシュボード / 長文統計 / 英作文統計 / 問題形式選択 / 類似検索 / データ一覧 / その他（大学間比較・大学別傾向・経年変化））
- **モバイル（768px以下）**: 4タブ統合（全体統計 / 問題形式 / 大学比較 / 大学詳細）
- Chart.js + chartjs-plugin-datalabels を全グラフで使用

## フィルターUI
- `<details>/<summary>` 折りたたみパネル（`.filter-panel`）
- デスクトップ: フローティング（`position:absolute`）、モバイル: インライン展開
- フィルタ状態判定: 全ON・全OFFは「制限なし」、一部チェック時のみ `is-filtered` クラス付与（黄色背景）
- 類似検索タブ: ソース選択用（大学ドロップダウン連動）と検索結果絞り込み用の2つの「大学属性」パネル

## コーディング規約
- テスト実行は変更後に必ず行う: `python -m pytest tests/ -v`
- 入試問題MDデータは `data/input_md/` に配置（gitには含めない）
- DBスキーマ変更時は `db.py` の `SCHEMA_SQL` を更新し、`init_db()` の冪等性を維持

## デザイン・UI（2026年3月更新）
- CSS: `--text-secondary`, `--danger-bg`, `--warning-bg`, `--warning-text`, `--orange` 変数追加（ダークモード対応）
- ユーティリティクラス追加: `.text-muted-sm`, `.text-danger`, `.text-warning`, `.bg-warning-subtle`, `.bg-danger-subtle`, `.similarity-high/mid/low`, `.metric-good/mid/bad/info`, `.modal-overlay`, `.modal-card`
- 全テンプレートのハードコード色(`#f8f9fa`等)をCSS変数・ユーティリティクラスに置換
- Chart.js: `cssVar()`ヘルパーでダークモード対応（`labelColor()`, `borderColor()`）
- upload.py: アップロードサイズ制限10MB追加
