"""Claude APIに送るプロンプト定義。"""

# ---------- CEFR推定プロンプト ----------

CEFR_SYSTEM_PROMPT = """あなたは英語読解テキストのCEFRレベルを判定する専門家です。
日本の大学入試英語長文を対象に、A2〜C1の範囲でレベルを推定します。
以下のJSON形式のみ返してください。マークダウンのコードブロックや説明文は不要です。"""

CEFR_USER_PROMPT = """以下の英語長文のCEFRレベルを判定してください。

=== テキスト情報 ===
出典: {university} {year}年度
文体: {text_style}

=== 語彙・構文指標 ===
平均文長: {avg_sentence_length}語/文
CEFR-J B2超過語率: {cefr_j_beyond_rate}（リスト外の高度な語彙の割合）
NGSL未カバー率: {ngsl_uncovered_rate}（一般頻度語リスト外の割合）
NAWL率: {nawl_rate}（学術語彙の割合）
CEFR-J分布: {cefr_j_profile}

=== 英文本文（先頭3000字） ===
{text_body}

=== CEFRレベル判定基準（テキスト特徴量を最優先に判断すること）===
A2（基礎）    : beyond率<5%  ・平均文長<13語・NGSL未カバー<12%
               短文中心・日常的語彙・単純な文構造
               例: 共通テスト第1〜3問レベル

B1（中級）    : beyond率5〜8% ・平均文長13〜16語・NGSL未カバー12〜18%
               複文あり・平易な論説・中程度の語彙
               例: 共通テスト第4〜5問レベル

B2（上級）    : beyond率8〜12%・平均文長16〜20語・NGSL未カバー18〜25%
               高度な論説・抽象概念・複雑な文構造
               例: 中堅国公立大学レベル

C1（高度）    : beyond率12〜18%・平均文長18〜24語・NGSL未カバー25〜35%
               学術的表現・複雑な議論・難解な語彙
               例: 難関大学レベル

C2（最高度）  : beyond率>18%・平均文長>24語・NGSL未カバー>35%
               極めて高度な語彙・入り組んだ論理構造（日本の入試では極めて稀）

注意: 指標が境界域の場合はテキスト内容（語彙の難しさ・文構造の複雑さ・議論の抽象度）を重視すること。

=== 出力形式 ===
{{"cefr_score": <1.0〜5.0の数値（0.5刻み）>, "cefr_confidence": "<high|medium|low>"}}

スコア対応表:
1.0 = A2（基礎）     1.5 = A2/B1境界
2.0 = B1（中級）     2.5 = B1/B2境界
3.0 = B2（上級）     3.5 = B2/C1境界
4.0 = C1（高度）     4.5 = C1/C2境界
5.0 = C2（最高度）

confidence判定:
- high: 複数指標が一致しテキスト内容も明確
- medium: 指標が境界域か一部矛盾がある
- low: 指標が分散しテキストのみで判断"""


# ---------- 大問分類プロンプト ----------

SYSTEM_PROMPT = """あなたは日本の大学入試英語問題を分析する専門家です。
以下のJSON形式のみ返してください。マークダウンのコードブロックや説明文は不要です。"""

USER_PROMPT = """以下は{university} {year}年度の入試問題 Question {question_number} です。

=== 英文本文 ===
{text_section}

=== 設問 ===
{questions_section}

以下のJSONを返してください:
{{
  "text_type": "<long_reading | short_translation | composition | others | listening>",
  "text_style": "<説明文 | 論説文 | ニュース・レポート | エッセイ・評論 | 物語文>",
  "word_count": <英文の語数（整数）。composition/others/listeningの場合はnull>,
  "source_title": "<出典タイトル、不明ならnull>",
  "source_author": "<著者名、不明ならnull>",
  "source_year": <出版年（整数）、不明ならnull>,
  "genre_main": "<以下のリストから1つ選択>",
  "genre_sub": "<上記リストから1つ選択>",
  "theme": "<テーマ要約・15字以内>",
  "has_jp_translation": <true/false>,
  "has_jp_explanation": <true/false>,
  "has_en_explanation": <true/false>,
  "has_jp_summary": <true/false>,
  "has_en_summary": <true/false>,
  "has_wabun_eiyaku": <true/false>,
  "has_jiyu_eisakubun": <true/false>,
  "has_visual_info": <true/false>,
  "visual_info_type": "<グラフ | 表 | イラスト | 写真 | 地図 | なし>",
  "low_confidence_fields": ["<自信がないフィールド名のリスト>"]
}}

=== text_type の判定基準 ===
本文と設問の両方を見て総合的に判定すること。
- long_reading: 200語以上の連続英文 + 内容理解問題
- short_translation: 短文の英文和訳問題（英語→日本語の翻訳）のみ。和文英訳は含まない
- composition: 英文産出を主目的とする問題。和文英訳（与えられた日本語をほぼすべて自力で英訳する問題）、自由英作文、グラフ・データを見て英語で記述する問題、英語で空所を埋める記述問題を含む
- others: 語句整序（並べ替え）、語句変形・補充で英文を完成させる問題、独立した文法・語彙の選択問題（長文読解に付随しない単独の文法問題）など、上記に該当しない問題
- listening: リスニング問題。「放送を聞いて」「英語が読まれます」「聞き取り」等の指示がある音声聴解問題

=== genre_main の選択肢 ===
科学・技術 / 医療・健康 / 心理・行動 / 教育・学習 / 環境・自然 / 社会・文化 / 経済・ビジネス / 歴史・哲学 / 言語・コミュニケーション / その他

=== genre_sub の選択肢（genre_main に対応するリストから1つ選択。該当なければ空文字）===
- 科学・技術: AI・ロボット / 宇宙・天文 / エネルギー / 情報技術 / バイオ・遺伝子 / 材料・化学 / 動物行動・生態 / 科学史・哲学 / その他科技
- 医療・健康: 病気・治療 / 食事・栄養 / メンタルヘルス / 医療制度 / 運動・身体 / 神経科学・脳 / 長寿・老化 / その他医療
- 心理・行動: 認知・思考 / 感情・幸福 / 行動・習慣 / 人間関係 / 意思決定 / その他心理
- 教育・学習: 学校・制度 / 言語学習 / 子育て・発達 / 創造性・才能 / その他教育
- 環境・自然: 地球温暖化 / 生物多様性 / 廃棄物・汚染 / エコ・持続可能性 / 自然現象 / その他環境
- 社会・文化: 観光 / メディア / 多様性 / 移民・難民 / 食文化 / スポーツ / 芸術 / ジェンダー / 家族・個人 / 犯罪・法律 / 地域・都市 / 高齢化・人口 / その他社会
- 経済・ビジネス: 消費・市場 / 国際経済 / 労働・雇用 / 農業・食料 / テクノロジー経済 / その他経済
- 歴史・哲学: 歴史 / 宗教・文化遺産 / 倫理・道徳 / 文明 / その他歴史
- 言語・コミュニケーション: 言語変化 / 翻訳・多言語 / SNS・デジタル / 対話・説得 / 言語理論・習得 / 手話・非言語 / 文学・文章論 / その他言語

=== 設問フラグの判定基準（本文と設問の両方を見て判定すること）===
- has_jp_translation: 「～を日本語に訳しなさい」「和訳せよ」「日本語で表しなさい」等。英文の部分訳に限定
- has_jp_explanation: 「～について日本語で説明しなさい」「述べよ」「日本語で答えなさい」等。設問への記述的な回答。内容説明・理由説明を日本語で求めるもの
- has_en_explanation: 「～についてEnglishで説明しなさい」「英語で述べよ」「Write in English」等。設問への英文記述回答
- has_jp_summary: 「要約せよ」「要旨をまとめよ」「summarize...in Japanese」「各段落を○字以内で要約」等。全体または段落の日本語要約
- has_en_summary: 「要約を英語で書きなさい」「英語で要旨をまとめよ」等。英語での要約
- has_wabun_eiyaku: 和文英訳（与えられた日本語をほぼすべて自力で英訳する問題）を含むか
- has_jiyu_eisakubun: 自由英作文（テーマを与えて自由に英語で書かせる、グラフ・データを見て英語で記述する問題も含む）を含むか。両方含む場合は両方true
- has_visual_info: 英作文・自由英作文の問題文中に、| で囲った表、グラフ、イラスト、写真、地図等の視覚素材が提示されているか。Markdown形式の表（| ... | ... |）も視覚情報に含める
- visual_info_type: 視覚情報がある場合はその種別を1つ選択（Markdown表は「表」）。ない場合は「なし」

=== 重要な注意事項 ===
- text_type が others または listening の場合: text_style="", genre_main="", genre_sub="", theme="" とすること（判定不要）、word_countはnull
- text_type が long_reading, short_translation の場合: text_style, genre_main, genre_sub, theme, word_count を全て判定すること
- text_type が composition の場合: word_countはnull。genre_main, genre_sub, theme は判定する（短文で判定困難な場合は空文字可）。text_styleは以下のサブタイプで異なる:
  - 和文英訳（has_wabun_eiyaku=true）を含む場合: text_style を判定する（短文で判定困難な場合は空文字可）
  - 自由英作文のみ（has_jiyu_eisakubun=true かつ has_wabun_eiyaku=false）の場合: text_style="" とすること
- themeには問題の内容・題材を書くこと。問題形式（「自由英作文問題」「リスニング問題」「文法問題」等）をthemeに書いてはならない
- 日本語の本文が与えられた場合（和文英訳問題）はcomposition
- low_confidence_fields: 判定に自信がないフィールドがあれば、そのフィールド名を日本語ラベルで入れる（例: ["種別", "ジャンル", "和文英訳"]）。全て自信があれば空リスト[]
  - フィールド名→日本語ラベル対応: text_type=種別, text_style=文体, genre_main=ジャンル, genre_sub=サブジャンル, theme=テーマ, has_jp_translation=和訳, has_jp_explanation=説明(日), has_en_explanation=説明(英), has_jp_summary=要約(日), has_en_summary=要約(英), has_wabun_eiyaku=和英, has_jiyu_eisakubun=自英, has_visual_info=視覚"""


# --- 旧プロンプト（後方互換用・将来削除予定） ---

SYSTEM_PROMPT_TEXT = """あなたは日本の大学入試英語問題を分析する専門家です。
以下のJSON形式のみ返してください。マークダウンのコードブロックや説明文は不要です。"""

USER_PROMPT_TEXT = """以下は{university} {year}年度の入試問題 Question {question_number} の英文本文です。

---
{text_section}
---

以下のJSONを返してください:
{{
  "text_type": "<long_reading | short_translation | composition | others>",
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

text_type の判定基準:
- long_reading: 200語以上の連続英文 + 内容理解問題
- short_translation: 短文の英文和訳問題（英語→日本語の翻訳）のみ。和文英訳は含まない
- composition: 英文産出を主目的とする問題
- others: 語句整序、文法・語彙問題など上記に該当しない問題
- listening: リスニング問題

注意:
- genre_main, genre_sub, theme は text_type が long_reading の場合のみ判定する。それ以外では空文字"""

SYSTEM_PROMPT_QUESTIONS = """あなたは日本の大学入試英語問題の設問を分析する専門家です。
以下のJSON形式のみ返してください。マークダウンのコードブロックや説明文は不要です。"""

USER_PROMPT_QUESTIONS = """以下は{university} {year}年度の入試問題 Question {question_number} の設問部分です。

---
{questions_section}
---

以下のJSONを返してください:
{{
  "has_jp_written": false,
  "has_en_written": false,
  "has_summary": false,
  "has_wabun_eiyaku": false,
  "has_jiyu_eisakubun": false,
  "has_jp_translation": false,
  "has_jp_explanation": false,
  "has_en_explanation": false,
  "has_jp_summary": false,
  "has_en_summary": false,
  "has_visual_info": false,
  "visual_info_type": "なし"
}}"""
