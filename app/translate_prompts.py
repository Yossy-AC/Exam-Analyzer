"""Multi-LLM英訳機能のプロンプト定義。"""

# ---------------------------------------------------------------------------
# 英訳生成: 4LLM共通
# ---------------------------------------------------------------------------

TRANSLATE_SYSTEM_PROMPT = """\
あなたは英日翻訳の専門家です。
以下の条件に従って、与えられた日本語文を英訳してください。

## 条件
- 文法的に正確で、自然な英語表現を使用
- 学習者が理解・再現可能なレベルの語彙・構文を優先
- 原文の意味を正確に伝えること

## 出力形式
英訳を1つだけ出力すること（解説・補足・注釈は一切不要）。
最も自然で正確な英訳を1つ選び、それだけを出力。"""

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
あなたは翻訳の専門家です。
4種のLLM（Claude, Gemini, ChatGPT, Grok）が同じ日本語文を英訳しました。
これらのサンプルを分析し、指定された形式で結果を作成してください。

## 基本方針
あなたの役割は「最善の合成」ではなく「最も標準的な英訳の抽出」です。
- 4つのサンプルの中で共通する表現・構文を重視する
- 1つのLLMだけが使った特異な表現は、明らかに優れている場合を除き採用しない
- 「多くの英語話者が自然に選ぶ表現」を最優先する
- 奇をてらわず、平明で確実な英文を目指す"""

INTEGRATE_FORMAT1_TEMPLATE = """\
4種のLLM（Claude, Gemini, ChatGPT, Grok）が同じ日本語文を英訳しました。
4つのサンプルを比較し、最も「ふつう」な英訳を1つ抽出してください。

## 原文
{japanese_text}

## 各LLMの英訳
### Claude
{claude_result}
### Gemini
{gemini_result}
### ChatGPT
{chatgpt_result}
### Grok
{grok_result}

## 出力形式

### 標準訳
4サンプル中で最も多くのLLMが共通して選んだ語彙・構文を採用した英訳を1つ提示。
学習者が理解・再現可能な平明さを維持し、文法的に確実に正しいこと。

### 根拠
各LLMの選択を比較し、なぜこの表現が「標準」と言えるかを簡潔に（2〜3行）。"""

INTEGRATE_FORMAT2_TEMPLATE = """\
4種のLLM（Claude, Gemini, ChatGPT, Grok）が同じ日本語文を英訳しました。
4つのサンプルで表現が分かれた箇所を分析し、「どこまでOKか」を示してください。

## 原文
{japanese_text}

## 各LLMの英訳
### Claude
{claude_result}
### Gemini
{gemini_result}
### ChatGPT
{chatgpt_result}
### Grok
{grok_result}

## 出力形式

### 標準訳
4サンプル中で最も多くのLLMが共通して選んだ語彙・構文を採用した英訳を1つ提示。

### 許容される表現バリエーション
4つのサンプルで表現が分かれた箇所について、許容可能な代替表現を2〜4例提示。
各例について:
- 英文
- 標準訳との違い（語彙/構文/ニュアンス）を1行で

### 避けるべき表現
4サンプル中で問題があったものがあれば記載（なければ省略）。"""

INTEGRATE_FORMAT3_TEMPLATE = """\
4種のLLM（Claude, Gemini, ChatGPT, Grok）が同じ日本語文を英訳しました。
4つのサンプルから最も完成度の高い英訳を1つ合成してください。

## 原文
{japanese_text}

## 各LLMの英訳
### Claude
{claude_result}
### Gemini
{gemini_result}
### ChatGPT
{chatgpt_result}
### Grok
{grok_result}

## 出力形式

### ベスト英訳
4サンプルから最も洗練された表現を選び、1つの英訳に合成。
標準訳と異なり、ここでは「最も洗練された表現」を目指してよい。

### 表現注釈
各LLMの表現を比較し、なぜこの語彙・構文を選んだかを注記。
形式: 箇所ごとに「採用表現 ← 出典LLM / 他LLMの代替表現 / 選択理由」を簡潔に。"""

# ---------------------------------------------------------------------------
# 英訳レビュー: 4LLM共通
# ---------------------------------------------------------------------------

REVIEW_SYSTEM_PROMPT = """\
あなたは英文添削の専門家です。
以下の日本語原文とそれに対するユーザーの英訳を評価してください。

## 評価観点
以下の各観点について、問題があれば具体的に指摘してください。問題がなければ「問題なし」と明記。

1. **文法正確性**: 時制・主述一致・冠詞・前置詞・関係詞・動詞構文等の誤り
2. **語彙適合性**: 語の選択、和製英語的表現、コロケーション違反
3. **構文・文構造**: 日本語直訳的な語順、不自然な接続、情報構造
4. **意味の正確性**: 原文の意味の伝達度、誤訳、意味の欠落・追加
5. **総合的な改善余地**: より自然・正確にする余地があるか

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
あなたは英文添削の専門家です。
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
4LLMが共通して評価した強み。

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


# ---------------------------------------------------------------------------
# バッチ英訳
# ---------------------------------------------------------------------------

BATCH_TRANSLATE_USER_TEMPLATE = """\
以下の日本語文リストを、それぞれ英訳してください。

## ルール
- 各文につき、最も自然で正確な英訳を1つだけ出力
- ※必須語句 がある文は、指定された語句を必ず使用すること
- ※禁止語句 がある文は、指定された語句を絶対に使用しないこと
- ※ヒント がある文は、その指示を考慮して英訳すること
- 文番号を維持して出力すること
- 解説・補足・注釈は不要

## 出力形式
【1】（英訳のみ）
【2】（英訳のみ）

## 日本語文リスト
{numbered_list}
"""

BATCH_INTEGRATE_SYSTEM_PROMPT = """\
あなたは英日翻訳の専門家です。
4種のLLMがそれぞれ日本語文リストを英訳しました。各文について、4LLMの訳を比較し、最も標準的・代表的な英訳を1つ抽出してください。
「合成」ではなく、最も多くのLLMが合意した表現の選択を基本方針としてください。"""

BATCH_INTEGRATE_USER_TEMPLATE = """\
## 日本語文リスト
{numbered_list}

## 各LLMの英訳

### Claude
{claude_result}

### Gemini
{gemini_result}

### ChatGPT
{chatgpt_result}

### Grok
{grok_result}

## 出力形式
各文について以下の形式で出力:

【1】
標準訳: （4LLMが最も共通して選んだ表現を採用した1訳。制約がある場合は厳守）
採用ポイント: （どのLLMの表現が共通していたか、簡潔に1行）
注意点: （文法・語彙・構文で注目すべき点。なければ省略可）

【2】
標準訳: ...
...
{constraints}"""


def build_batch_numbered_list(items: list) -> str:
    """BatchItemリストから【N】形式の番号付きリストを生成する。"""
    lines = []
    for item in items:
        line = f"【{item.number}】{item.japanese_text}"
        if item.force_words:
            line += f" ※必須語句: {', '.join(item.force_words)}"
        if item.ban_words:
            line += f" ※禁止語句: {', '.join(item.ban_words)}"
        if item.hint:
            line += f" ※ヒント: {item.hint}"
        lines.append(line)
    return "\n".join(lines)


def build_batch_constraints(items: list) -> str:
    """制約があるアイテムの一覧を生成する（統合プロンプト末尾用）。"""
    constraints = []
    for item in items:
        parts = []
        if item.force_words:
            parts.append(f'必須語句: "{", ".join(item.force_words)}"')
        if item.ban_words:
            parts.append(f'禁止語句: "{", ".join(item.ban_words)}"')
        if item.hint:
            parts.append(f"ヒント: {item.hint}")
        if parts:
            constraints.append(f"- 【{item.number}】{' / '.join(parts)}")
    if not constraints:
        return ""
    return "\n\n## 制約事項（厳守）\n" + "\n".join(constraints)


# ---------------------------------------------------------------------------
# 方式A（拡張サンプリング）用の追加説明
# ---------------------------------------------------------------------------

INTEGRATE_EXTENDED_NOTE = """
各LLMから複数のサンプルが提供されています。
同一LLM内のサンプル間の揺らぎは、そのLLM内での表現の確信度を示します。
- 同一LLM内で3サンプルが同じ表現 → そのLLMはその表現に高い確信を持っている
- 同一LLM内でサンプルがバラバラ → 表現の揺れが自然に生じるポイント
この情報を中央値抽出の判断材料として活用してください。"""

# 出力形式ラベル
OUTPUT_FORMAT_LABELS: dict[int, str] = {
    1: "標準訳",
    2: "許容範囲",
    3: "ベスト英訳+注釈",
}

# 出力形式に対応する統合テンプレート
INTEGRATE_TEMPLATES: dict[int, str] = {
    1: INTEGRATE_FORMAT1_TEMPLATE,
    2: INTEGRATE_FORMAT2_TEMPLATE,
    3: INTEGRATE_FORMAT3_TEMPLATE,
}


# ---------------------------------------------------------------------------
# バッチレビュー
# ---------------------------------------------------------------------------

BATCH_REVIEW_USER_TEMPLATE = """\
以下の日本語文と英訳のペアリストをそれぞれレビューしてください。

## ルール
- 各ペアについて、全ての英訳を個別に評価
- 評価観点: 文法正確性、語彙適合性、構文・文構造、意味の正確性、総合的な改善余地
- 文番号を維持して出力すること

## 出力形式
各ペアについて以下の形式で出力:

【1】
[英訳ごとに]
- 問題点（あれば、該当箇所+説明+修正案）
- 改善英訳
- 総合評価: A/B/C/D

【2】
...

## レビュー対象
{numbered_pairs}
"""

BATCH_REVIEW_INTEGRATE_SYSTEM_PROMPT = """\
あなたは英文添削の専門家です。
4種のLLM（Claude, Gemini, ChatGPT, Grok）が同じ英訳リストをレビューしました。
各ペアについて、4LLMのレビュー結果を統合し、信頼性の高い統合レビューレポートを作成してください。

## 統合ルール
- 複数LLMが同一箇所を指摘: 信頼度高く必ず報告。
- 1LLMのみ指摘: あなたが妥当性を判断し、正当なら採用、過剰なら除外。
- 修正案が割れる場合: 複数案を併記し推奨を明示。"""

BATCH_REVIEW_INTEGRATE_USER_TEMPLATE = """\
## レビュー対象
{numbered_pairs}

## 各LLMのレビュー

### Claude
{claude_result}

### Gemini
{gemini_result}

### ChatGPT
{chatgpt_result}

### Grok
{grok_result}

## 出力形式
各ペアについて以下の形式で出力:

【1】
### 総合評価
[A/B/C/D] + 一言コメント

### 問題点（重大度順）
（番号付きリスト。該当箇所・説明内容・指摘LLM名・修正案）
（英訳が複数ある場合は英訳ごとに分けて記述）

### 良い点
（4LLMが共通して評価した強み）

### 改善訳
#### 最小修正訳
（問題点のみ修正してユーザーのスタイル維持）
#### 推奨訳
（より自然な英語に再構成）

【2】
...
"""


def build_batch_review_numbered_pairs(items: list) -> str:
    """BatchReviewItemリストから【N】形式のペアリスト文字列を生成する。"""
    parts = []
    for item in items:
        lines = [f"【{item.number}】"]
        lines.append(f"日本語: {item.japanese_text}")
        if len(item.user_translations) == 1:
            lines.append(f"英訳: {item.user_translations[0]}")
        else:
            circled = "①②③④⑤⑥⑦⑧⑨⑩"
            for i, tr in enumerate(item.user_translations):
                label = circled[i] if i < len(circled) else f"({i+1})"
                lines.append(f"英訳{label}: {tr}")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)
