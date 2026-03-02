"""Claude APIに送るプロンプト定義。"""

SYSTEM_PROMPT_TEXT = """あなたは日本の大学入試英語問題を分析する専門家です。
以下のJSON形式のみ返してください。マークダウンのコードブロックや説明文は不要です。"""

USER_PROMPT_TEXT = """以下は{university} {year}年度の入試問題 Question {question_number} の英文本文です。

---
{text_section}
---

以下のJSONを返してください:
{{
  "text_type": "<long_reading | short_translation | composition>",
  "text_style": "<説明文 | 論説文 | ニュース・レポート | エッセイ・評論 | 物語文>",
  "word_count": <整数>,
  "source_title": "<出典タイトル、不明ならnull>",
  "source_author": "<著者名、不明ならnull>",
  "source_year": <出版年（整数）、不明ならnull>,
  "genre_main": "<以下のリストから1つ選択>",
  "genre_sub": "<自由記述・10字以内>",
  "theme": "<テーマ要約・15字以内>"
}}

genre_main の選択肢:
科学・技術 / 医療・健康 / 心理・行動 / 教育・学習 / 環境・自然 / 社会・文化 / 経済・ビジネス / 歴史・哲学 / 言語・コミュニケーション / その他

text_type の判定基準:
- long_reading: 200語以上の連続英文 + 内容理解問題
- short_translation: 短文1〜3文 + 和訳指示のみ
- composition: 英文産出を主目的とする問題（和文英訳・自由英作文）"""

SYSTEM_PROMPT_QUESTIONS = """あなたは日本の大学入試英語問題の設問を分析する専門家です。
以下のJSON形式のみ返してください。マークダウンのコードブロックや説明文は不要です。"""

USER_PROMPT_QUESTIONS = """以下は{university} {year}年度の入試問題 Question {question_number} の設問部分です。

---
{questions_section}
---

以下のJSONを返してください:
{{
  "has_jp_written": <true/false: 日本語で記述する和訳問題があるか>,
  "has_en_written": <true/false: 英語で記述する英訳問題があるか>,
  "has_summary": <true/false: 要約問題があるか>,
  "comp_type": "<none | 和文英訳 | 自由英作文>"
}}

判定基準:
- has_jp_written: 「和訳しなさい」「日本語で説明しなさい」「日本語で要約しなさい」等
- has_en_written: 「英訳せよ」「英語で述べよ」「英語で書きなさい」等
- has_summary: 「要約せよ」「要旨をまとめよ」等
- comp_type: 和文英訳（日本語→英語の翻訳）/ 自由英作文（テーマを与えて自由に英語で書かせる）/ none（いずれでもない）"""
