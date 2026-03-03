# 入試問題分析システム

国公立大学の入試英語問題を自動分類・可視化するWebアプリケーション。

## 機能

- **自動分類**: OCR済みMDファイルをアップロードすると、Claude Sonnet APIで自動的にジャンル・テキスト種別・設問形式を分類
- **ダッシュボード**: 8タブ構成（アップロード / 大学別傾向 / 長文統計 / 英作文統計 / 経年変化 / 大学間比較 / 一覧 / 大学設定）
- **レビューリスト**: 未分類・問題データをアップロードタブで確認可能
- **インライン編集**: 一覧画面からジャンルやテーマを直接編集可能
- **手動データ追加**: フォームから1件ずつデータを手動入力可能
- **カラムフィルター**: 一覧タブで列ごとに絞り込み可能
- **大学設定管理**: 大学ごとの分類・地域をUIから設定
- **一括再分類**: "その他"サブカテゴリのデータをワンクリックで再分類
- **エクスポート**: CSV / JSON / SQLiteファイルのダウンロード
- **認証**: パスワードベースの簡易認証（オプション）

## セットアップ

### 1. 依存インストール

```bash
pip install -r requirements.txt
```

### 2. 環境変数の設定

```bash
cp .env.example .env
# .env を編集して ANTHROPIC_API_KEY を設定
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

### テキスト種別（4種別）
| 種別 | 説明 |
|---|---|
| long_reading | 長文読解（200語以上 + 内容理解問題） |
| short_translation | 短文和訳（英→日のみ） |
| composition | 英作文（和文英訳・自由英作文・グラフ記述） |
| listening | リスニング（放送・聞き取り問題） |

### ジャンル（10カテゴリ）
科学・技術 / 医療・健康 / 心理・行動 / 教育・学習 / 環境・自然 / 社会・文化 / 経済・ビジネス / 歴史・哲学 / 言語・コミュニケーション / その他

### 設問分析（5分類 + 視覚情報）
| フィールド | 説明 |
|---|---|
| has_jp_translation | 和訳問題 |
| has_jp_explanation | 日本語での説明・記述 |
| has_en_explanation | 英語での説明・記述 |
| has_jp_summary | 日本語での要約 |
| has_en_summary | 英語での要約 |
| has_visual_info | 英作文中の視覚情報の有無 |
| visual_info_type | 視覚情報の種別（グラフ/表/イラスト/写真/地図） |

### 文体
説明文 / 論説文 / ニュース・レポート / エッセイ・評論 / 物語文

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
| 分類API | Claude Sonnet (2回分割呼び出し) |
| デプロイ | Fly.io (Docker, 東京リージョン) |
