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
  "genre_sub": "<上記リストから1つ選択>",
  "theme": "<テーマ要約・15字以内>"
}}

genre_main の選択肢:
科学・技術 / 医療・健康 / 心理・行動 / 教育・学習 / 環境・自然 / 社会・文化 / 経済・ビジネス / 歴史・哲学 / 言語・コミュニケーション / その他

genre_sub の選択肢（genre_main に対応するリストから1つ選択。該当なければ空文字）:
- 科学・技術: AI・ロボット / 宇宙・天文 / エネルギー / 情報技術 / バイオ・遺伝子 / 材料・化学 / 動物行動・生態 / 科学史・哲学 / その他科技
- 医療・健康: 病気・治療 / 食事・栄養 / メンタルヘルス / 医療制度 / 運動・身体 / 神経科学・脳 / 長寿・老化 / その他医療
- 心理・行動: 認知・思考 / 感情・幸福 / 行動・習慣 / 人間関係 / 意思決定 / その他心理
- 教育・学習: 学校・制度 / 言語学習 / 子育て・発達 / 創造性・才能 / その他教育
- 環境・自然: 地球温暖化 / 生物多様性 / 廃棄物・汚染 / エコ・持続可能性 / 自然現象 / その他環境
- 社会・文化: 観光 / メディア / 多様性 / 移民・難民 / 食文化 / スポーツ / 芸術 / ジェンダー / 家族・個人 / 犯罪・法律 / 地域・都市 / 高齢化・人口 / その他社会
- 経済・ビジネス: 消費・市場 / 国際経済 / 労働・雇用 / 農業・食料 / テクノロジー経済 / その他経済
- 歴史・哲学: 歴史 / 宗教・文化遺産 / 倫理・道徳 / 文明 / その他歴史
- 言語・コミュニケーション: 言語変化 / 翻訳・多言語 / SNS・デジタル / 対話・説得 / 言語理論・習得 / 手話・非言語 / 文学・文章論 / その他言語

text_type の判定基準:
- long_reading: 200語以上の連続英文 + 内容理解問題
- short_translation: 短文の英文和訳問題（英語→日本語の翻訳）のみ。和文英訳は含まない
- composition: 英文産出を主目的とする問題。和文英訳（日本語→英語の翻訳）、自由英作文、グラフ・データを見て英語で記述する問題を含む
- listening: リスニング問題。「放送を聞いて」「英語が読まれます」「聞き取り」等の指示がある音声聴解問題

注意:
- composition/listeningの場合、text_styleは最も近い文体を推定（不明なら「説明文」）
- composition/listeningで英文本文がない場合、word_countは0
- 日本語の本文が与えられた場合（和文英訳問題）はcomposition"""

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

判定基準（設問テキストだけでなく、指示文 Instructions の内容も含めて判定すること）:
- has_jp_translation: 「～を日本語に訳しなさい」「和訳せよ」「日本語で表しなさい」等。英文の部分訳に限定
- has_jp_explanation: 「～について日本語で説明しなさい」「述べよ」「日本語で答えなさい」等。設問への記述的な回答。内容説明・理由説明を日本語で求めるもの
- has_en_explanation: 「～についてEnglishで説明しなさい」「英語で述べよ」「Write in English」等。設問への英文記述回答
- has_jp_summary: 「要約せよ」「要旨をまとめよ」「summarize...in Japanese」「各段落を○字以内で要約」等。全体または段落の日本語要約
- has_en_summary: 「要約を英語で書きなさい」「英語で要旨をまとめよ」等。英語での要約
- comp_type: 和文英訳（日本語→英語の翻訳）/ 自由英作文（テーマを与えて自由に英語で書かせる、グラフ・データを見て英語で記述する問題も含む）/ none（いずれでもない）
- has_visual_info: 英作文・自由英作文の問題文中に、| で囲った表、グラフ、イラスト、写真、地図等の視覚素材が提示されているか。Markdown形式の表（| ... | ... |）も視覚情報に含める
- visual_info_type: 視覚情報がある場合はその種別を1つ選択（Markdown表は「表」）。ない場合は「なし」"""
