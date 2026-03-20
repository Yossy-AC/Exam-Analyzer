"""Multi-LLM英訳機能のプロンプト定義。"""

# ---------------------------------------------------------------------------
# 英訳生成: 4LLM共通
# ---------------------------------------------------------------------------

TRANSLATE_SYSTEM_PROMPT = """\
あなたは大学入試の英語指導に精通した翻訳者です。
以下の条件に従って、与えられた日本語文を英訳してください。

## 条件
- 大学入試（和文英訳）の模範解答として適切な英文を作成
- 文法的に正確で、自然な英語表現を使用
- 受験生が理解・再現可能なレベルの語彙・構文を優先
- 原文の意味を正確に伝えること

## 出力形式
- 英訳のみを出力すること（解説・補足・注釈は不要）
- 複数の訳出案がある場合も、最善の1つだけを出力"""

TRANSLATE_USER_TEMPLATE = """\
以下の日本語文を英訳してください。

## 日本語文
{japanese_text}"""

TRANSLATE_USER_WITH_CONTEXT_TEMPLATE = """\
以下の日本語文を英訳してください。

## 出典
{context}

## 日本語文
{japanese_text}"""

# ---------------------------------------------------------------------------
# 英訳生成: 統合フェーズ（Claude）
# ---------------------------------------------------------------------------

INTEGRATE_SYSTEM_PROMPT = """\
あなたは大学入試の英語指導に精通した翻訳の専門家です。
4種のLLM（Claude, Gemini, ChatGPT, Grok）が同じ日本語文を英訳しました。
これらを分析し、指定された形式で統合結果を作成してください。
各LLMの良い表現を積極的に取り込み、採用した表現には出典LLMを括弧で注記してください。"""

INTEGRATE_FORMAT1_TEMPLATE = """\
4種のLLM（Claude, Gemini, ChatGPT, Grok）が同じ日本語文を英訳しました。
これらを分析し、3段階の英訳を作成してください。

## 原文
{japanese_text}

## 各LLMの英訳
- Claude: {claude_result}
- Gemini: {gemini_result}
- ChatGPT: {chatgpt_result}
- Grok: {grok_result}

## 出力形式
以下の3段階で英訳を作成し、各段階で4LLMの良い表現を積極的に取り込み、
採用した表現には出典LLMを括弧で注記してください。

### 1. 標準訳
原文に忠実な直訳寄りの英訳。入試で安全に得点できる表現を選択。
受験生が模範解答として暗記・再現できるレベル。

### 2. 再構成訳
文構造を英語的に再編成。情報の順序・接続表現・主語の選択を最適化。
上位層の学生に添削指導で「こう書くとより良い」と示すレベル。

### 3. native的訳
英語話者が自然に書く表現。イディオム・コロケーション・修辞的工夫を活用。
教員参考・最上位層への提示用。"""

INTEGRATE_FORMAT2_TEMPLATE = """\
4種のLLM（Claude, Gemini, ChatGPT, Grok）が同じ日本語文を英訳しました。
これらを分析し、最善の英訳を1つ合成してください。

## 原文
{japanese_text}

## 各LLMの英訳
- Claude: {claude_result}
- Gemini: {gemini_result}
- ChatGPT: {chatgpt_result}
- Grok: {grok_result}

## 出力形式

### ベスト英訳
4つの英訳から最も優れた表現を組み合わせて、1つの最善英訳を合成。
入試模範解答としての完成度を最優先。

### 表現注釈
ベスト英訳で採用した表現について、以下を注釈として付記:
- 採用元のLLM名
- 他LLMの代替表現（使える場合）
- 語彙・構文の選択理由（簡潔に）

形式例:
- "compelling argument"（採用: Gemini）→ Grokの "persuasive case" も可。compellingの方がアカデミックな文脈に適合。"""

INTEGRATE_FORMAT3_TEMPLATE = """\
4種のLLM（Claude, Gemini, ChatGPT, Grok）が同じ日本語文を英訳しました。
各英訳の特徴を分析し、総評を作成してください。

## 原文
{japanese_text}

## 各LLMの英訳
- Claude: {claude_result}
- Gemini: {gemini_result}
- ChatGPT: {chatgpt_result}
- Grok: {grok_result}

## 出力形式

### 各英訳の特徴分析
LLMごとに以下を簡潔に記述:
- 翻訳アプローチ（直訳寄り/意訳寄り）
- フォーマリティレベル
- 特筆すべき表現選択

### 入試適合度ランキング
1位〜4位を、理由とともに提示。

### 注目すべき表現差異
4つの英訳で特に差が出た箇所をピックアップ。
それぞれの表現の長所・短所を比較。"""

# ---------------------------------------------------------------------------
# 英訳レビュー: 4LLM共通
# ---------------------------------------------------------------------------

REVIEW_SYSTEM_PROMPT = """\
あなたは大学入試の英語指導に精通した英語教育の専門家です。
以下の日本語原文とそれに対するユーザーの英訳を評価してください。

## 評価観点
以下の各観点について、問題があれば具体的に指摘してください。問題がなければ「問題なし」と明記。

1. **文法正確性**: 時制・主述一致・冠詞・前置詞・関係詞・動詞構文等の誤り
2. **語彙適合性**: 語の選択、和製英語的表現、コロケーション違反
3. **構文・文構造**: 日本語直訳的な語順、不自然な接続、情報構造
4. **意味の正確性**: 原文の意味の伝達度、誤訳、意味の欠落・追加
5. **入試適合度**: 大学入試の解答として減点されそうなポイント

## 出力形式
各観点ごとに:
- 問題の有無
- 該当箇所の引用
- 問題の説明
- 具体的な修正案

最後に全体の改善版英訳を1つ提示。"""

REVIEW_USER_TEMPLATE = """\
以下の日本語原文とユーザーの英訳を評価してください。

## 日本語原文
{japanese_text}

## ユーザーの英訳
{user_translation}"""

REVIEW_USER_WITH_CONTEXT_TEMPLATE = """\
以下の日本語原文とユーザーの英訳を評価してください。

## 出典
{context}

## 日本語原文
{japanese_text}

## ユーザーの英訳
{user_translation}"""

# ---------------------------------------------------------------------------
# 英訳レビュー: 統合フェーズ（Claude）
# ---------------------------------------------------------------------------

REVIEW_INTEGRATE_SYSTEM_PROMPT = """\
あなたは大学入試の英語指導に精通した英語教育の専門家です。
4種のLLM（Claude, Gemini, ChatGPT, Grok）が同じ英訳をレビューしました。
各LLMのレビュー結果を統合し、信頼性の高い統合レビューレポートを作成してください。"""

REVIEW_INTEGRATE_TEMPLATE = """\
4種のLLM（Claude, Gemini, ChatGPT, Grok）が同じ英訳をレビューしました。
各LLMのレビュー結果を統合し、統合レビューレポートを作成してください。

## 原文
{japanese_text}

## ユーザーの英訳
{user_translation}

## 各LLMのレビュー
- Claude: {claude_result}
- Gemini: {gemini_result}
- ChatGPT: {chatgpt_result}
- Grok: {grok_result}

## 統合ルール
- **複数LLMが同一箇所を指摘**: 信頼度高。必ず報告。
- **1LLMのみ指摘**: あなた（Claude）が妥当性を判断。正当なら採用、過剰なら除外。
- **修正案が割れる場合**: 複数案を併記し、推奨を提示。理由を記載。
- **4LLMとも問題なしの箇所**: 「良い点」として積極的に報告。

## 出力形式（Markdown）

### 総合評価
[A: ほぼ完璧 / B: 軽微な問題あり / C: 要修正 / D: 大幅修正必要]
一文で総評。

### 問題点（重大度順）
番号付きリスト。各項目:
- 重大度（高/中/低）
- 該当箇所
- 指摘内容
- 指摘したLLM名（一致度=信頼性の指標）
- 修正案

### 良い点
4LLMが共通して評価した強み。受験生に伝えるべきOKポイント。

### 改善版
#### 最小修正版
問題点のみ修正し、ユーザーの英訳スタイルを維持。

#### 推奨版
より自然な英語に再構成。4LLMの改善提案の良いところを統合。"""

# ---------------------------------------------------------------------------
# オプション: 大学別チューニング
# ---------------------------------------------------------------------------

UNIVERSITY_CONTEXTS: dict[str, str] = {
    "kyoto": """【出題傾向: 京都大学】
京都大学の和文英訳は、抽象的・文学的な日本語が出題される傾向が強い。
- 原文の抽象概念を英語で再構成する力が重要視される
- 直訳では不自然になりがちな問題が多く、意訳力が求められる
- 「日本語の含意」を読み取り、英語で自然に表現する能力が問われる
- 比喩的表現や多義的な語句の処理が頻出
この傾向を踏まえた英訳・評価を行ってください。""",

    "osaka": """【出題傾向: 大阪大学】
大阪大学の和文英訳は、比較的素直な論理的文章が中心。
- 正確な文法と適切な語彙選択が重要
- 標準的な英語力を安定して発揮することが求められる
- 論理的なつなぎ（接続詞・指示語の処理）が重要
- 奇をてらわない堅実な英訳が高評価
この傾向を踏まえた英訳・評価を行ってください。""",

    "kobe": """【出題傾向: 神戸大学】
神戸大学の和文英訳は、文法的正確性と基本語彙の適切な運用が重要。
- 受験生が再現可能な表現を優先
- 奇をてらわない堅実な英訳が高評価
- 基本的な構文力（関係詞・動詞構文・仮定法等）の正確な運用が問われる
- 語彙は標準的な範囲で十分だが、コロケーションの正確さは重要
この傾向を踏まえた英訳・評価を行ってください。""",

    "kyoto_pref": """【出題傾向: 京都府立大学】
京都府立大学の和文英訳は、短めで基本的な構文力と語彙力を問う。
- シンプルで正確な英文が求められる
- 基本文法の確実な運用が最重要
- 難度は標準的だが、ケアレスミスが差をつけるポイント
この傾向を踏まえた英訳・評価を行ってください。""",

    "osaka_metro": """【出題傾向: 大阪公立大学】
大阪公立大学の和文英訳は、標準的な難度で論理的な文章の英訳が中心。
- 文法的正確性と読みやすさのバランスが重要
- 論説文・説明文の英訳が多い
- 情報を整理して英語の論理構造に再編する力が求められる
この傾向を踏まえた英訳・評価を行ってください。""",
}

UNIVERSITY_MAX_SCORES: dict[str, int] = {
    "kyoto": 25,
    "osaka": 20,
    "kobe": 15,
    "kyoto_pref": 15,
    "osaka_metro": 15,
}

# ---------------------------------------------------------------------------
# オプション: 減点シミュレーション（レビューモード専用）
# ---------------------------------------------------------------------------

SCORING_FRAGMENT = """
## 追加指示: 減点シミュレーション
レビュー結果に加えて、入試採点を模した減点シミュレーションを行ってください。

### 採点ルール
- 配点: {max_score}点満点
- 減点基準:
  - 文法エラー（重大: 時制の根本的誤り、主述不一致等）: -3点
  - 文法エラー（軽微: 冠詞の欠落、前置詞の誤用等）: -1点
  - 語彙不適合（意味が変わるレベル）: -2点
  - 語彙不適合（不自然だが通じる）: -1点
  - 意味の欠落・誤訳: -3〜5点（程度による）
  - 構文の不自然さ: -1〜2点（程度による）
- 同一カテゴリの減点が複数ある場合、個別にカウント

### 出力形式
以下のMarkdown形式で出力:

### 減点シミュレーション
**{{score}}/{max_score}点**

| # | 該当箇所 | 減点 | カテゴリ | 理由 |
|---|----------|------|----------|------|
| 1 | "..." | -2 | 語彙 | ... |
| 2 | "..." | -1 | 文法（軽微） | ... |
| 合計 | | -{{total}} | | |

※ 実際の採点基準は大学・年度により異なります。あくまで目安としてご利用ください。"""

# ---------------------------------------------------------------------------
# オプション: 生成結果との比較（レビューモード専用）
# ---------------------------------------------------------------------------

COMPARE_FRAGMENT = """
## 追加指示: LLM生成英訳との比較
同じ日本語文に対して、事前に4種LLMが生成した英訳があります。
ユーザーの英訳とこれらを比較し、以下を追加で分析してください。

### 4LLMの生成英訳
- Claude: {claude_translation}
- Gemini: {gemini_translation}
- ChatGPT: {chatgpt_translation}
- Grok: {grok_translation}

### 出力形式
以下のMarkdown形式で出力:

### LLM生成英訳との比較

#### ユーザー英訳がLLMより優れている点
- （具体的に記述。該当なしの場合は「特になし」）

#### LLM英訳から取り入れるべき表現
| LLM | 表現 | ユーザーの対応箇所 | 改善効果 |
|-----|------|-------------------|---------|
| ... | ... | ... | ... |

#### 総合的な位置づけ
ユーザー英訳の質を4LLMの英訳と比較した場合の相対的な評価。
（例: 「Geminiの英訳に近い質だが、語彙選択でClaude的が優位」等）"""


# ---------------------------------------------------------------------------
# ヘルパー関数
# ---------------------------------------------------------------------------

def build_translate_user_prompt(japanese_text: str, context: str | None = None) -> str:
    """英訳生成のuserプロンプトを構築する。"""
    if context:
        return TRANSLATE_USER_WITH_CONTEXT_TEMPLATE.format(
            japanese_text=japanese_text, context=context,
        )
    return TRANSLATE_USER_TEMPLATE.format(japanese_text=japanese_text)


def build_review_user_prompt(
    japanese_text: str, user_translation: str, context: str | None = None,
) -> str:
    """英訳レビューのuserプロンプトを構築する。"""
    if context:
        return REVIEW_USER_WITH_CONTEXT_TEMPLATE.format(
            japanese_text=japanese_text,
            user_translation=user_translation,
            context=context,
        )
    return REVIEW_USER_TEMPLATE.format(
        japanese_text=japanese_text, user_translation=user_translation,
    )


def inject_university(prompt: str, university: str | None, custom_text: str | None = None) -> str:
    """プロンプトに大学別チューニングを注入する。"""
    if not university:
        return prompt
    if university == "custom" and custom_text:
        return prompt + f"\n\n【出題傾向】{custom_text}"
    ctx = UNIVERSITY_CONTEXTS.get(university)
    if ctx:
        return prompt + "\n\n" + ctx
    return prompt


def get_max_score(university: str | None) -> int:
    """大学に応じた満点スコアを返す。"""
    return UNIVERSITY_MAX_SCORES.get(university or "", 15)


def build_scoring_fragment(university: str | None) -> str:
    """減点シミュレーションのプロンプト断片を構築する。"""
    return SCORING_FRAGMENT.format(max_score=get_max_score(university))


def build_compare_fragment(previous_translations: dict[str, str]) -> str:
    """生成結果比較のプロンプト断片を構築する。"""
    return COMPARE_FRAGMENT.format(
        claude_translation=previous_translations.get("claude", "[N/A]"),
        gemini_translation=previous_translations.get("gemini", "[N/A]"),
        chatgpt_translation=previous_translations.get("chatgpt", "[N/A]"),
        grok_translation=previous_translations.get("grok", "[N/A]"),
    )


# 出力形式ラベル
OUTPUT_FORMAT_LABELS: dict[int, str] = {
    1: "3段階英訳統合",
    2: "ベスト英訳+注釈",
    3: "4LLM並列+総評",
}

# 出力形式に対応する統合テンプレート
INTEGRATE_TEMPLATES: dict[int, str] = {
    1: INTEGRATE_FORMAT1_TEMPLATE,
    2: INTEGRATE_FORMAT2_TEMPLATE,
    3: INTEGRATE_FORMAT3_TEMPLATE,
}
