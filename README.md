# 入試問題分析システム

国公立大学の入試英語問題を自動分類・可視化するWebアプリケーション。

## 機能

- **自動分類**: OCR済みMDファイルをアップロードすると、Claude Sonnet APIで自動的にジャンル・テキスト種別・設問形式を分類
- **ダッシュボード**: 5タブ構成（アップロード / ジャンルトレンド / 大学別比較 / 問題構成表 / 全レコード一覧）
- **インライン編集**: 一覧画面からジャンルやテーマを直接編集可能
- **一括置換**: ジャンル名の一括変更に対応
- **エクスポート**: CSV / JSON / SQLiteファイルのダウンロード
- **認証**: パスワードベースの簡易認証（オプション）

## セットアップ

### 1. 依存インストール

```bash
cd exam-text-classifier
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
3. 「一覧」タブで分類結果を確認・編集
4. 「トレンド」「大学別」タブでグラフを確認
5. 必要に応じてCSV出力

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

各大学の特殊パターン（京都大のフロントマター異常、東京大のContinuedパターン、大阪大の(A)(B)分割、九州大の角括弧番号）に対応済み。

## 分類スキーム

### ジャンル（10カテゴリ）
科学・技術 / 医療・健康 / 心理・行動 / 教育・学習 / 環境・自然 / 社会・文化 / 経済・ビジネス / 歴史・哲学 / 言語・コミュニケーション / その他

### テキスト種別
long_reading / short_translation / composition

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
| バックエンド | FastAPI (Python) |
| フロントエンド | HTMX + Jinja2 + Chart.js |
| DB | SQLite |
| 分類API | Claude Sonnet (2回分割呼び出し) |
| デプロイ | Fly.io (Docker) |
