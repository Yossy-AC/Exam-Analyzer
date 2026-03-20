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
- **PDF変換**: Gemini API (`gemini-2.5-pro`) でPDF→Markdown変換
- **CEFR推定**: Claude APIで長文のCEFRレベル（A2〜C2）を推定
- **Embedding**: Voyage AI (`voyage-4`, 1024次元) でテキスト類似度検索
- **語彙分析**: NLTK + 7語彙リスト（小中学語彙, CEFR-J, NGSL, NAWL, ターゲット1900, LEAP, 最強単語リスト）
- **Multi-LLM英訳**: Claude, Gemini, ChatGPT, Grok の4LLM並列呼び出し + Claude統合
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
│   ├── gemini_convert.py   # Gemini API PDF→Markdown変換
│   ├── prompts.py          # プロンプト定義（統合 + CEFR推定 + 旧互換）
│   ├── llm_clients.py      # 4種LLM非同期クライアント + 並列呼び出し
│   ├── translate_prompts.py # Multi-LLM英訳プロンプト + 大学別チューニング
│   ├── translate_service.py # 英訳生成・reformat・レビューのビジネスロジック
│   ├── models.py           # Pydanticモデル（ClassificationResult等）
│   ├── vocab_analyzer.py   # 語彙分析（5リスト照合・平均文長・CEFR-J分布）
│   ├── embedding.py        # Voyage AI embedding（voyage-4, 1024次元）
│   ├── search.py           # 類似長文検索（コサイン類似度 / 特徴量フォールバック）
│   ├── wordlists/          # 語彙リストデータ（小中学語彙, CEFR-J, NGSL, NAWL, ターゲット1900, LEAP）
│   └── routers/            # エンドポイント群
│       ├── upload.py       # アップロード（MD/PDF統合）・解析・レビューリスト
│       ├── passages.py     # CRUD・インライン編集・手動追加・カラムフィルター
│       ├── dashboard.py    # 集計・グラフデータ（7エンドポイント）
│       ├── export.py       # CSV/JSON/DBエクスポート
│       ├── search.py       # 類似長文検索API・HTMXパーシャル
│       ├── universities.py # 大学分類・地域設定管理
│       └── translate.py   # Multi-LLM英訳API（生成・reformat・レビュー・履歴）
├── templates/              # Jinja2テンプレート
│   ├── base.html
│   ├── index.html          # 分析画面（7タブ、モバイルは4タブ統合）
│   ├── manage.html         # 管理画面（データ一覧・編集・削除）
│   ├── translate.html      # Multi-LLM英訳ツール（生成・レビュー・履歴）
│   ├── login.html
│   └── partials/           # HTMXフラグメント
├── static/style.css
├── data/                   # DB・アップロードファイル・一時PDF保存先
├── tools/                  # 一括更新スクリプト（backfill_*.py, compare_search.py）
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
- `GEMINI_API_KEY` — 必須: Gemini API キー（PDF変換用）
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
- チャンク分割対応: 同一Question IDの連続ブロックを自動マージ、アルファベット単体(`B`)→直前の`NA`から`NB`に補正、裸数字(`3`)→直前の`3B`にマージ
- ファイル名パース: `_問題` サフィックスなし（例: `2024一橋大学.pdf`）にもフォールバック対応
- 大学名正規化: `〇〇大学` → `〇〇大`（`_normalize_university_name()` / `_normalize_university()`）

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
  - CEFR-Jレベル別分布 + B2超過率、NGSL未カバー率、NAWL率、ターゲット1900/LEAP/最強単語リストカバー率、平均文長
  - 単語帳プロファイル: 小中学語彙（`junior_high.txt`）をベースに加え、「小中学語彙+単語帳N番まで」の統合カバー率
- `classifier.py` の `estimate_cefr()`: Claude APIでCEFRレベル（A2〜C2）+ 信頼度を推定
  - アップロード時に自動実行（`upload.py:_save_passage()`内、long_readingのみ）
  - 入力: text_body先頭3000字 + 語彙指標
  - cefr_score: A2=1, B1=2, B2=3, C1=3.5, C2=4（数値化）
- `embedding.py`: Voyage AI voyage-4モデル（1024次元）でtext_bodyをembedding化
  - アップロード時に自動生成、embedding IS NULLのパッセージは`tools/backfill_embedding.py`で一括付与
  - Tier 1: 2,000 RPM / 8M TPM、無料枠200Mトークン
- `search.py`: 類似長文検索
  - embedding両方あり → コサイン類似度（ジャンル一致+0.02）
  - embedding片方なし → 特徴量ベース加重距離（cefr_score 50%, avg_sentence_length 20%, ngsl/nawl各15%）
- 一括更新スクリプト: `tools/backfill_text.py`（text_body+語彙）、`tools/backfill_cefr.py`（CEFR推定）、`tools/backfill_embedding.py`（embedding付与）、`tools/backfill_saikyou.py`（最強単語リストカバー率）

## データ管理
- 全データ削除: `POST /api/passages/delete-all`
- 年度・大学別削除: `DELETE /api/passages?year=&university=`
- 手動データ追加: `POST /api/passages/manual`
- "その他"サブカテゴリ一括再分類: `POST /api/passages/reclassify-other`
- プロンプトやパーサー修正後は全削除→再アップロードが必要（`INSERT OR IGNORE`のため）

## data/フォルダ
- OneDriveへのシンボリックリンク（`Dev/setup.sh` で作成）
- 自宅・職場・ノートPC間のDB同期に使用。同時起動禁止。
- 入試問題MDデータは `data/input_md/` に配置（gitには含めない）
- セットアップ: `bash setup.sh <OneDriveのDO_NOT_CHANGE_NAMEパス>`（Dev/で1回実行）

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
- ダッシュボード・長文統計・英作文統計: 「共通テスト」はデフォルトOFF

## 著作権省略検出
- `parser.py:detect_copyright_omitted()`: Geminiマーカー(`<!-- COPYRIGHT_OMITTED`)+ 日本語正規表現フォールバック
- 著作権省略パッセージは `copyright_omitted=1` でDB保存、Claude分類・語彙分析・CEFR推定・embeddingをスキップ
- ダッシュボード集計・類似検索から自動除外（`COALESCE(copyright_omitted, 0) = 0`）
- 管理画面のデータ一覧・レビューリストには表示（グレー背景 + `©省略`バッジ）
- Geminiプロンプト（`data/gemini_prompt.md`）に`<!-- COPYRIGHT_OMITTED: [説明] -->`出力指示を追記済み

## 共通テスト対応
- `config.py`: `UNIVERSITY_CLASS_LIST`に`"共通テスト"`追加、`PREMIUM_UNIVERSITY_CLASSES`にも追加（Opus使用）
- 問題番号: `# 第1問A` → `split_questions()`で`"1A"` → `normalize_question_number()`で`"I-A"`
- ファイル名規約: `{year}第N回共通テスト_R_XXX_問題.pdf`（XXX = 本試験/追試験）、`{year}第N回共通テスト_R_試作問題.pdf`
- 大学名正規化: `第N回共通テスト_R_本試験` → `共通テスト（R本試験）`、`_R_試作問題` → `共通テスト（R試作）`
- 試行調査対応: `第N回試行調査_R` → `共通テスト（R試行調査N）`（共通テスト系として統合）
- 試作問題: `### 第A問` / `### 第B問` で分割するフォールバック（`_split_kyotsu_shisaku()`）
- upload.py: `共通テスト` を含む大学名に `university_class='共通テスト'` を自動設定
- 大学並び順: 共通テスト(0) > 旧帝大(1) > 難関大(2) > ...

## X-ray System（vocabulary-app連携）

spaCyベースのトークナイザーでlong_reading本文を解析し、語彙カテゴリ別に分類するAPI。

### 依存
- `spacy>=3.8.0` + `en_core_web_sm` モデル（`uv pip install`で直接インストール）

### モジュール
- `app/xray_tokenizer.py`: spaCyトークナイザー。トークン分類優先順位: punctuation→junior_high→wordbook_mastered→saikyou→ngsl→propn→number→glossed→unknown。派生語フォールバック（-ly/-ness等サフィックスストリップ）
- `app/routers/xray.py`: 3エンドポイント
  - `GET /api/xray/passages` — long_readingメタデータ一覧
  - `GET /api/xray/passage/{id}` — staff only、本文トークナイズ結果
  - `POST /api/xray/analyze` — 任意テキストトークナイズ（10,000字制限）

### DBカラム
- `saikyou_words` (TEXT DEFAULT ''): 各long_readingに出現する最強リスト語のJSON配列
- バックフィル: `tools/backfill_saikyou_words.py`

### アップロード連携
- `upload.py:_save_passage()` でsaikyou_words自動計算（`extract_saikyou_words()`使用）

## コーディング規約
- テスト実行は変更後に必ず行う: `python -m pytest tests/ -v`
- 入試問題MDデータは `data/input_md/` に配置（gitには含めない）
- DBスキーマ変更時は `db.py` の `SCHEMA_SQL` を更新し、`init_db()` の冪等性を維持

## UI改善（2026年3月Phase1-4）
- `TEXT_TYPE_LABELS`: `config.py`に一元化、テンプレートで日本語表示（長文読解/短文和訳/英作文/その他/リスニング）
- 要確認リスト: データ問題行に「編集」ボタン追加 → `jumpToRecord()`でデータ一覧タブへ直行
- テーブルヘッダー固定: `.table-scroll`に`max-height: calc(100vh - 220px); overflow-y: auto;`、`.table th`に`z-index: 2`
- チャートタブ読み込み表示: canvasを`opacity: 0.3`にして再描画時に復元
- 一括レビュー済み: `PATCH /api/passages/bulk-review` エンドポイント + `#bulk-bar`に「一括確認済み」ボタン
- 大学検索補完: `<datalist id="university-datalist">` + `<input list=...>`（大学比較・プロフィール・経年・類似検索）
- 類似検索クイックサーチ: テキスト入力で`_similarPassages`をフィルタ、カスケードは`<details>`内に格納
- manage.htmlフィルタURL保存: `applyRecordsFilter()`でURLパラメータ更新、リロード時に復元
- ダッシュボードKPI説明文: 各KPIカードにサブテキスト + 冒頭にシステム説明
- ジョブステップインジケータ: `.step-indicator`（G→M→C→✓）、`.step-active`（パルスアニメーション）、`.step-done`（緑チェック）
- モバイルフィルタ: bottom sheet化（`.filters-open`でfixed bottom配置 + slide-upアニメーション + overlay）
- トースト通知: `showToast(message, type)` をbase.htmlに定義、全`alert()`を置換
- 大学プロフィールディープリンク: `?tab=other&university=東京大`でプロフィール直接表示
- モーダルフォーカス管理: Escape閉じ + オーバーレイクリック閉じ + 自動フォーカス

## デザイン・UI（2026年3月更新）
- CSS: `--text-secondary`, `--danger-bg`, `--warning-bg`, `--warning-text`, `--orange` 変数追加（ダークモード対応）
- ユーティリティクラス追加: `.text-muted-sm`, `.text-danger`, `.text-warning`, `.bg-warning-subtle`, `.bg-danger-subtle`, `.similarity-high/mid/low`, `.metric-good/mid/bad/info`, `.modal-overlay`, `.modal-card`
- 全テンプレートのハードコード色(`#f8f9fa`等)をCSS変数・ユーティリティクラスに置換
- Chart.js: `cssVar()`ヘルパーでダークモード対応（`labelColor()`, `borderColor()`）
- upload.py: アップロードサイズ制限（MD: 10MB, PDF: 50MB）
- `.table-resizable th`: カラム幅リサイズ対応（アップロードタブ・大学設定テーブル）
- `.sortable` ヘッダー: クリックでテーブルソート（⇅▲▼ インジケータ付き）
- ダークモード可読性改善: `--muted: #c0c0c5`（旧 `#a1a1a6`）、`--text-secondary: #d0d0d5`（旧 `#c7c7cc`）
- ダークモードテーブルヘッダー: `--bg-header: #2c3a52`（青みのあるダーク色）、`.table th` に適用
- 長文統計タブレイアウト: 2×2グリッド（上行: ジャンル分布 + 文体分布、下行: 記述問題種別 + ジャンル詳細）
- ジャンル詳細（サブジャンル）: 総数上位4ジャンル（TOP_GENRES=4）、各最大5件（MAX_SUBS=5）を表示
- 共通テスト除外: 類似検索ソース選択（SQLの WHERE 句 + テンプレート）・類似検索結果（テンプレート + JS）・問題形式選択（テンプレート）すべてから除外
- style.css `:root` 変数をportal.css `--p-*` にブリッジ（`--primary`→`var(--p-accent)` 等10変数）。固有変数（`--muted`, `--danger-bg`等8変数）は保持
- university_settings.html: `alert()` 5箇所を `showToast()` に置換

## PDF一括アップロード機能
- 管理画面のアップロードタブでMD/PDFを統合ドロップゾーンで受付（フォルダD&D対応）
- エンドポイント: `POST /api/upload-all`（ファイル拡張子で自動判別）
- PDF処理パイプライン: Gemini変換 → MD解析 → Claude分類 → DB保存
- `app/gemini_convert.py`: pdf-converterから移植した3関数（`is_scanned_pdf`, `parse_filename`, `convert_pdf_to_markdown`）
- Gemini APIレート制限: Semaphore(1) + 10秒間隔
- RECITATION（著作権）フィルタ対策: ページ分割フォールバック（5ページずつチャンク送信）
- 安全フィルタ: 全カテゴリ`BLOCK_NONE`に設定
- 変換後MDは `data/input_md/` に保存、一時PDFは `data/temp_pdf/`（成功時削除）
- ジョブ進捗: `source_type`（md/pdf）と`current_step`（gemini_converting/parsing/classifying）で管理
- エラーメッセージにステップラベル付与: `[Gemini変換]`, `[MD解析]`, `[Claude分類]`
- プロンプト: `data/gemini_prompt.md`（基本ルール）+ `data/gemini_prompt_kyotsu.md`（共通テスト追加ルール、条件付き連結）
- Caddyfile: グローバル `max_size 200MB`、`/staff/exam*` も `max_size 200MB`
- アップロードUI: XHR手動送信 + プログレスバー（HTMX非使用）
- Shift-JIS→UTF-8ファイル名変換: latin-1→cp932デコードフォールバック
- ジョブ一覧: LIMIT 300（大量アップロード対応）、ソート可能（ファイル名・状態・抽出数・開始日時）
- アップロード時にCEFR推定も自動実行（long_readingのみ、`tools/backfill_cefr.py` 不要に）
- ファイル名パース: `_問題` サフィックスなしにもフォールバック対応（`parse_filename()`, `extract_university_from_filename()`）
- MD処理時もcurrent_step表示（parsing → classifying）
- 要確認リスト: 処理状況の下に表示（ジョブ問題→データ問題）、再投入成功時に旧警告を自動非表示
- ジョブステータス: passages_created=0 + エラーメッセージあり → `status='error'`（以前は`'completed'`）
- 処理状況フィルタ: HTMXターゲット外に配置（5秒リフレッシュでリセットされない）
- 要確認リスト: ソート・フィルタ・列幅変更対応（ジョブ問題・データ問題テーブル）
- Gemini 503/429対策: 5回リトライ + エクスポネンシャルバックオフ（15s→30s→60s→120s→240s）
- main.py: `_base_href` を `yossy-portal-lib` の `base_href` に置換、`/health` エンドポイント追加
- main.py + テンプレート: CSP nonceミドルウェア（`csp_middleware`）追加、全`<script>`タグに`nonce`属性付与

## Multi-LLM英訳機能（2026年3月）
和文英訳の指導支援。4種LLM（Claude, Gemini, ChatGPT, Grok）を並列呼び出しし、Claude統合で模範解答・レビューを生成。

### モード
- **英訳生成**: 日本語文→4LLM並列英訳→Claude統合（3形式: 3段階英訳/ベスト+注釈/4LLM並列+総評）
- **英訳レビュー**: ユーザー英訳を4LLMが評価→Claude統合レポート
- **履歴**: 過去の生成・レビュー結果を閲覧（translationsテーブル）

### APIエンドポイント（staff only）
- `POST /api/staff/translate` — 英訳生成
- `POST /api/staff/translate/reformat` — 形式変更（4LLM再呼び出しなし）
- `POST /api/staff/review` — 英訳レビュー
- `GET /api/staff/translate/history` — 履歴一覧
- `GET /api/staff/translate/history/{id}` — 履歴詳細
- `DELETE /api/staff/translate/history/{id}` — 履歴削除

### ファイル構成
- `app/llm_clients.py`: 4LLM非同期クライアント（Claude=anthropic, Gemini=google-genai, ChatGPT/Grok=openai）
- `app/translate_prompts.py`: プロンプト定義 + 大学別チューニング（京大/阪大/神大/京府大/大阪公立/カスタム）
- `app/translate_service.py`: ビジネスロジック（generate/reformat/review + DB保存）
- `app/routers/translate.py`: APIルーター + Pydanticモデル
- `templates/translate.html`: UI（3タブ: 英訳生成/レビュー/履歴、marked.js async CDN）

### オプション
- **大学別チューニング**: 大学固有の出題傾向をプロンプトに注入
- **減点シミュレーション**（レビューのみ）: 大学別配点で採点を模擬
- **生成結果との比較**（レビューのみ）: 事前の英訳生成結果とユーザー英訳を比較

### 環境変数（`Dev/.env`）
- `OPENAI_API_KEY` — ChatGPT API
- `XAI_API_KEY` — Grok API
- `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` — 既存

### DBスキーマ
- `translations` テーブル: id, mode, japanese_text, user_translation, context, output_format(INTEGER), university, options_json, raw_results_json, integrated_result, processing_time_ms, llm_times_json, created_at

### CSP注意事項
- CaddyのグローバルCSPとアプリのnonce付きCSPが共存するため、**インラインイベントハンドラ（onclick等）は使用不可**
- nonce付きCSPが存在すると `'unsafe-inline'` は無視される（CSP Level 2仕様）
- 全イベントは `addEventListener` で登録すること（translate.htmlで対応済み）
- marked.js は `async` 属性で読み込み、未ロード時はプレーンテキストフォールバック（`renderMarkdown()`）
