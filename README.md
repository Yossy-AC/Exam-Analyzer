# 国公立大出題分析システム

国公立大学の入試英語問題を自動分類・可視化するWebアプリケーション。

## 機能

- **自動分類**: OCR済みMDファイルをアップロードすると、Claude APIで自動的にジャンル・テキスト種別・設問形式を分類
- **モデル自動選択**: 大学クラスに応じてOpus（旧帝大・難関大・準難関大）とSonnet（その他）を使い分け
- **信頼度フラグ**: LLMが判定に自信のないフィールドを黄色バッジで表示、レビューを促進
- **語彙分析**: CEFR-J / NGSL / NAWL / ターゲット1900 / LEAPの5語彙リストで難易度を定量化
- **CEFRレベル推定**: Claude APIで長文のCEFRレベル（A2〜C2）を自動推定
- **類似長文検索**: Voyage AI embedding（voyage-4）によるコサイン類似度で意味的に類似した長文を検索
- **分析画面**: 7タブ構成（ダッシュボード / 長文統計 / 英作文統計 / 問題形式選択 / 大学間比較 / 大学別傾向 / 経年変化）。モバイルは4タブに統合
- **管理画面**: データ一覧・インライン編集・削除・大学設定・アップロード
- **レビューリスト**: 未分類・低信頼度データをアップロードタブで確認可能
- **インライン編集**: 一覧画面からジャンルやテーマを直接編集可能
- **手動データ追加**: フォームから1件ずつデータを手動入力可能
- **カラムフィルター**: 一覧タブで列ごとに絞り込み可能（CEFRレベル含む）
- **大学設定管理**: 大学ごとの分類・地域をUIから設定
- **一括再分類**: "その他"サブカテゴリのデータをワンクリックで再分類
- **エクスポート**: CSV / JSON / SQLiteファイルのダウンロード
- **認証**: パスワードベースの簡易認証（オプション）。ポータル経由時はstudentロールのアクセス制限あり

## セットアップ

### 1. 依存インストール

```bash
pip install -r requirements.txt
```

### 2. 環境変数の設定

```bash
cp .env.example .env
# .env を編集して ANTHROPIC_API_KEY, VOYAGE_API_KEY を設定
```

### 3. 起動

```bash
uvicorn app.main:app --reload
```

ブラウザで http://localhost:8000 を開く。

### 4. 使い方

1. 「アップロード」タブでMDファイルをドラッグ&ドロップ
2. 自動解析が完了するとデータがDBに保存される
3. 各タブでグラフ・統計を確認
4. 「一覧」タブで分類結果を確認・編集
5. 必要に応じてCSV/JSON出力

## 対応MDファイル形式

```markdown
---
university: 東京大
year: 2025
faculty: []
---

# Question 1

## Instructions
...

## Text
...英文パッセージ...

## Questions
...設問...
```

各大学の特殊パターンに対応済み:
- 京都大: フロントマター異常時のファイル名フォールバック
- 東京大: Continuedパターンのマージ、複数Textセクションの連結
- 大阪大: (A)/(B)分割による別パッセージ抽出
- 九州大: 角括弧付き番号
- 空Text時の`## Data` → `## Instructions`フォールバック

## 分類スキーム

### テキスト種別（5種別）
| 種別 | 説明 |
|---|---|
| long_reading | 長文読解（200語以上 + 内容理解問題） |
| short_translation | 短文和訳（英→日のみ） |
| composition | 英作文（和文英訳・自由英作文・グラフ記述） |
| others | 語句整序、文法・語彙問題など |
| listening | リスニング（放送・聞き取り問題） |

### ジャンル（10カテゴリ）
科学・技術 / 医療・健康 / 心理・行動 / 教育・学習 / 環境・自然 / 社会・文化 / 経済・ビジネス / 歴史・哲学 / 言語・コミュニケーション / その他

### 設問分析
| フィールド | 説明 |
|---|---|
| has_jp_translation | 和訳問題 |
| has_jp_explanation | 日本語での説明・記述 |
| has_en_explanation | 英語での説明・記述 |
| has_jp_summary | 日本語での要約 |
| has_en_summary | 英語での要約 |
| has_wabun_eiyaku | 和文英訳 |
| has_jiyu_eisakubun | 自由英作文 |
| has_visual_info | 英作文中の視覚情報の有無 |
| visual_info_type | 視覚情報の種別（グラフ/表/イラスト/写真/地図） |

### 文体
説明文 / 論説文 / ニュース・レポート / エッセイ・評論 / 物語文

### モデル選択
| 大学クラス | モデル |
|---|---|
| 旧帝大・難関大・準難関大 | Claude Opus |
| その他 | Claude Sonnet |

## デプロイ (Fly.io)

```bash
fly launch
fly volumes create exam_data --region nrt --size 1
fly secrets set ANTHROPIC_API_KEY=sk-ant-xxxxx
fly secrets set SECRET_KEY=$(openssl rand -hex 32)
fly secrets set ADMIN_PASSWORD_HASH='$2b$12$...'
fly deploy
```

## テスト

```bash
python -m pytest tests/ -v
```

## 技術スタック

| 要素 | 技術 |
|---|---|
| バックエンド | FastAPI (Python 3.12) |
| フロントエンド | HTMX + Jinja2 + Chart.js |
| DB | SQLite |
| 分類API | Claude Opus / Sonnet（大学クラス別自動選択、統合プロンプト1回呼び出し） |
| CEFR推定 | Claude API（語彙指標をアンカーに使用） |
| Embedding | Voyage AI voyage-4（1024次元、コサイン類似度検索） |
| 語彙分析 | NLTK + CEFR-J / NGSL / NAWL / ターゲット1900 / LEAP |
| デプロイ | Fly.io (Docker, 東京リージョン) |
