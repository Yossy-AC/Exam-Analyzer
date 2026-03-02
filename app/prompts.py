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
  "has_jp_written": <true/false: 日本語で記述する問題があるか（旧互換性フィールド）>,
  "has_en_written": <true/false: 英語で記述する問題があるか（旧互換性フィールド）>,
  "has_summary": <true/false: 要約問題があるか（旧互換性フィールド）>,
  "comp_type": "<none | 和文英訳 | 自由英作文>",
  "has_jp_translation": <true/false: 英文の一部を日本語に訳すタスク>,
  "has_jp_explanation": <true/false: 問いに対して日本語で説明・記述して答えるタスク>,
  "has_en_explanation": <true/false: 問いに対して英語で説明・記述して答えるタスク>,
  "has_jp_summary": <true/false: 英文を日本語で要約するタスク>,
  "has_en_summary": <true/false: 英文を英語で要約するタスク>,
  "has_visual_info": <true/false: 英作文問題に図表・グラフ・イラスト・Markdown表等の視覚情報が含まれるか>,
  "visual_info_type": "<グラフ | 表 | イラスト | 写真 | 地図 | なし>"
}}

判定基準:
- has_jp_translation: 「～を日本語に訳しなさい」「和訳せよ」等。英文の部分訳に限定
- has_jp_explanation: 「～について日本語で説明しなさい」「述べよ」等。設問への記述的な回答
- has_en_explanation: 「～についてEnglishで説明しなさい」「英語で述べよ」等。設問への英文記述回答
- has_jp_summary: 「本文の内容を日本語で要約しなさい」「要旨をまとめよ」等。全体または段落の要約
- has_en_summary: 「要約を英語で書きなさい」「英語で要旨をまとめよ」等。英語での要約
- comp_type: 和文英訳（日本語→英語の翻訳）/ 自由英作文（テーマを与えて自由に英語で書かせる）/ none（いずれでもない）
- has_visual_info: 英作文・自由英作文の問題文中に、| で囲った表、グラフ、イラスト、写真、地図等の視覚素材が提示されているか。Markdown形式の表（| ... | ... |）も視覚情報に含める
- visual_info_type: 視覚情報がある場合はその種別を1つ選択（Markdown表は「表」）。ない場合は「なし」"""
