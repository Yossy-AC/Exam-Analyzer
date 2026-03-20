# Multi-LLM英訳ツール

## 概要
4種LLM（Claude, Gemini, ChatGPT, Grok）を並列呼び出しし、Claude統合で模範解答・レビューレポートを生成する英訳支援ツール。exam-analyzerサービス内の独立機能。

設計書: `multi-llm-translation-spec-v2.md`

## アクセス
- ブラウザ: `/staff/exam/translate`（ポータル経由）
- ポータルトップ: スタッフ向けツール「Multi-LLM 英訳」カード

## ファイル構成

```
app/
├── llm_clients.py          # 4LLM非同期クライアント + call_all_llms()並列呼び出し
├── translate_prompts.py    # 全プロンプト定義 + 大学別チューニング + ヘルパー
├── translate_service.py    # ビジネスロジック（generate/reformat/review + DB保存）
└── routers/
    └── translate.py        # API 6エンドポイント + Pydanticモデル

templates/
└── translate.html          # UI（3タブ: 英訳生成/レビュー/履歴）

tests/
└── test_translate.py       # 17テスト（プロンプトビルダー + 部分失敗）
```

## モード

### 英訳生成
日本語文 → 4LLM並列英訳（各2案: 直訳寄り + 意訳寄り） → Claude統合

各LLMが2訳を出力し、統合Claudeが8訳を素材として統合。さらにClaude独自の改善提案も可能。

3つの出力形式（`output_format` INTEGER）:
1. **3段階英訳統合**: 標準訳 / 再構成訳 / native的訳
2. **ベスト英訳+注釈**: 最善の1訳 + 表現選択理由
3. **4LLM並列+総評**: 各LLMの特徴分析 + 英文品質ランキング + 独自改善提案

形式切替は `/reformat` で統合のみ再実行（4LLM再呼び出しなし）。

### 英訳レビュー
日本語文 + ユーザー英訳 → 4LLMレビュー → Claude統合レポート

オプション:
- **減点シミュレーション**: 大学別配点で採点を模擬（レビューのみ）
- **生成結果との比較**: 事前の英訳生成結果とユーザー英訳を比較（レビューのみ、同一セッションで生成実行済みの場合のみ有効）

### 履歴
全結果をDBに自動保存。閲覧・再利用（入力欄にセット）・削除が可能。

## APIエンドポイント（staff only）

| メソッド | パス | 用途 |
|---------|------|------|
| POST | `/api/staff/translate` | 英訳生成（4LLM並列+統合） |
| POST | `/api/staff/translate/reformat` | 形式変更（統合のみ再実行、DB保存しない） |
| POST | `/api/staff/review` | 英訳レビュー（4LLMレビュー+統合） |
| POST | `/api/staff/translate/ask` | 結果に対する質問（会話履歴対応） |
| GET | `/api/staff/translate/history` | 履歴一覧（`?limit=50&offset=0`） |
| GET | `/api/staff/translate/history/{id}` | 履歴詳細 |
| DELETE | `/api/staff/translate/history/{id}` | 履歴削除 |

## LLMクライアント（`llm_clients.py`）

| LLM | SDK | モデル | system渡し方 |
|-----|-----|--------|-------------|
| Claude | `anthropic.AsyncAnthropic` | `claude-sonnet-4-6` | `system` パラメータ |
| Gemini | `google.genai.Client` | `gemini-2.5-flash` | `system_instruction` (GenerateContentConfig) |
| ChatGPT | `openai.AsyncOpenAI` | `gpt-4o` | `messages[0].role="system"` |
| Grok | `openai.AsyncOpenAI` (base_url=xai) | `grok-3` | `messages[0].role="system"` |

- 並列呼び出し: `call_all_llms(system, user, timeout=120)` → `asyncio.gather` + 個別タイムアウト
- 1LLM失敗時: 他は続行、失敗分は `[ERROR] ...` 文字列
- 統合フェーズ: `call_claude()` で統合プロンプト実行（モデル: `TRANSLATE_INTEGRATION_MODEL`）
- モデル名は全て `config.py` の定数で管理（変更容易）

## プロンプト構成（`translate_prompts.py`）

### system/user分離
- **system**: ロール定義 + 出力制約（「英訳のみ出力、解説不要」等）
- **user**: 日本語テキスト + 出典 + 大学オプション

### 定数一覧
| 定数 | 用途 |
|------|------|
| `TRANSLATE_SYSTEM_PROMPT` | 4LLM共通system（英訳指示） |
| `TRANSLATE_USER_TEMPLATE` | 英訳user（出典なし） |
| `TRANSLATE_USER_WITH_CONTEXT_TEMPLATE` | 英訳user（出典あり） |
| `INTEGRATE_SYSTEM_PROMPT` | 統合system |
| `INTEGRATE_FORMAT1_TEMPLATE` | 3段階英訳統合user |
| `INTEGRATE_FORMAT2_TEMPLATE` | ベスト+注釈user |
| `INTEGRATE_FORMAT3_TEMPLATE` | 4LLM並列+総評user |
| `REVIEW_SYSTEM_PROMPT` | 4LLMレビューsystem |
| `REVIEW_USER_TEMPLATE` | レビューuser |
| `REVIEW_INTEGRATE_SYSTEM_PROMPT` | レビュー統合system |
| `REVIEW_INTEGRATE_TEMPLATE` | レビュー統合user |
| `UNIVERSITY_CONTEXTS` | 大学別チューニング辞書 |
| `SCORING_FRAGMENT` | 減点シミュレーション追加指示 |
| `COMPARE_FRAGMENT` | 生成結果比較追加指示 |

### ヘルパー関数
- `build_translate_user_prompt(text, context)` — 英訳userプロンプト構築
- `build_review_user_prompt(text, translation, context)` — レビューuserプロンプト構築
- `inject_university(prompt, university, custom_text)` — 大学別チューニング注入
- `get_max_score(university)` — 大学別満点スコア取得
- `build_scoring_fragment(university)` — 減点シミュレーション断片構築
- `build_compare_fragment(previous_translations)` — 生成比較断片構築

## 大学別チューニング

| キー | 大学 | 満点 | 特徴 |
|------|------|------|------|
| `kyoto` | 京都大学 | 25 | 抽象的・文学的、意訳力重視 |
| `osaka` | 大阪大学 | 20 | 素直な論理的文章、正確性重視 |
| `kobe` | 神戸大学 | 15 | 基本語彙・構文の正確な運用 |
| `kyoto_pref` | 京都府立大学 | 15 | 短め、シンプル・正確 |
| `osaka_metro` | 大阪公立大学 | 15 | 標準難度、論理構造の再編 |
| `custom` | カスタム | 15 | ユーザーが自由入力 |

## DBスキーマ（`translations`テーブル）

```sql
CREATE TABLE IF NOT EXISTS translations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mode TEXT NOT NULL,              -- 'translate' | 'review'
    japanese_text TEXT NOT NULL,
    user_translation TEXT,           -- レビューモード時のみ
    context TEXT,
    output_format INTEGER,           -- 1=3段階 / 2=ベスト / 3=並列
    university TEXT,
    options_json TEXT,               -- オプション全体をJSON保存
    raw_results_json TEXT NOT NULL,  -- 4LLM生出力 {claude:..., gemini:...}
    integrated_result TEXT NOT NULL, -- Claude統合結果（Markdown）
    processing_time_ms INTEGER,
    llm_times_json TEXT,             -- {claude: ms, gemini: ms, ...}
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);
```

## フロントエンド（`translate.html`）

### 技術スタック
- Jinja2テンプレート（`base.html` 継承）
- vanilla JS（React/HTMX不使用）
- marked.js（CDN、async読み込み、未ロード時プレーンテキストフォールバック）

### State管理
```javascript
let _rawTranslations = null;      // 4LLM生出力（reformat・レビュー比較用）
let _integratedMarkdown = null;   // 統合結果Markdown（コピー用）
let _currentFormat = 1;           // 現在の出力形式
let _reviewMarkdown = null;       // レビュー統合結果Markdown
let _askConversation = [];        // 英訳生成の質問会話履歴
let _revAskConversation = [];     // レビューの質問会話履歴
```

### 質問機能
英訳生成・レビューの両結果に対してClaudeに質問可能。原文・4LLM出力・統合結果をコンテキストとして送信し、会話履歴を保持して複数ターンの対話が可能。新規生成/レビュー実行時にリセット。Enterで送信、Shift+Enterで改行。

### CSP制約（重要）
- **インラインイベントハンドラ（`onclick`等）は使用不可**
- CaddyグローバルCSPとアプリnonce付きCSPが共存し、nonce付きCSPが存在すると`'unsafe-inline'`は無視される（CSP Level 2仕様）
- 全イベントは `addEventListener` で登録
- 動的生成HTML（履歴テーブル等）は `data-action` 属性 + イベント委譲で処理

### API通信
- `apiPost(path, body)` / `apiGet(path)` ヘルパー関数
- 認証切れ検出: `res.redirected` または `content-type` が非JSONの場合エラー
- エラー時: ローディングオーバーレイにエラーメッセージ表示（どのステップで失敗したか明示）

### ローディング表示
- 経過時間リアルタイム表示
- 3ステップ表示: 4LLM並列呼び出し → Claude統合処理 → 完了
- エラー時: 失敗ステップを赤色表示 + エラーメッセージ + 閉じるボタン

## 環境変数（`Dev/.env`）

| 変数 | 用途 | 備考 |
|------|------|------|
| `ANTHROPIC_API_KEY` | Claude API | 既存 |
| `GEMINI_API_KEY` | Gemini API | 既存 |
| `OPENAI_API_KEY` | ChatGPT API | 新規追加 |
| `XAI_API_KEY` | Grok API | 新規追加 |

## config.py 定数

```python
TRANSLATE_CLAUDE_MODEL = "claude-sonnet-4-6"
TRANSLATE_GEMINI_MODEL = "gemini-2.5-flash"
TRANSLATE_OPENAI_MODEL = "gpt-4o"
TRANSLATE_GROK_MODEL = "grok-3"
TRANSLATE_INTEGRATION_MODEL = "claude-sonnet-4-6"
TRANSLATE_MAX_TOKENS = 4096
TRANSLATE_TIMEOUT = 120  # 秒
```

## テスト

```bash
# 英訳機能のテストのみ
python -m pytest tests/test_translate.py -v

# 全テスト
python -m pytest tests/ -v
```

テスト内容:
- プロンプトビルダー: 大学別・採点・比較の各組み合わせ
- `call_all_llms` 部分失敗: 1LLMタイムアウト/例外時に他3つが正常返却

## 入試文脈の扱い（設計方針）

LLMの入試採点予測は信頼性が低い。LLMが得意なのは「英語としての正確性・自然さ・表現の巧拙」の評価であり、「特定大学の採点者がどう評価するか」の予測ではない。

| プロンプト層 | 入試文脈 | 理由 |
|-------------|---------|------|
| 個別LLM英訳 | 「学習者が再現可能な語彙・構文」は残す | 難易度コントロール（出力制御） |
| 統合プロンプト | **全て除去** | 英文の正確性・自然さ・表現力で評価 |
| 減点シミュレーション | **例外として許可** | 機能目的が入試採点模擬 |
| 大学別チューニング | そのまま残す | ユーザーが意図的にONにするオプション |

統合プロンプトでの禁止ワード: 「入試で減点」「入試適合度」「得点」「受験生に伝える」等

## 将来拡張（未実装）
- 3案モード: 各LLMの出力を3訳に増やす（2案で似通る場合の対策）
- SSE対応: 4LLM個別の進捗をリアルタイム表示
- 特定LLMのON/OFF切替UI
- プロンプトカスタマイズUI
- exam.dbとの紐付け（特定の入試問題に対する英訳結果の保存）
- 生徒解答との比較モード（essay-service連携）
