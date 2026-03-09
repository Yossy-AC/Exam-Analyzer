"""MDファイルパーサー: 入試問題MDを大問単位に分割し、Text/Questionsセクションを抽出する。"""

from __future__ import annotations

import re
from typing import Optional

import yaml

from app.models import ParsedQuestion


def extract_university_from_filename(filename: str) -> str:
    """ファイル名から大学名を抽出（括弧付き名称を含む）。

    Examples:
        '2025東京大_問題.md' -> '東京大'
        '2025大阪大（外国語以外）_問題.md' -> '大阪大（外国語以外）'
        '2025東京都立大（理系）_問題.md' -> '東京都立大（理系）'
        '2025第５回共通テスト_R_本試験_問題.md' -> '共通テスト（R本試験）'
        '2025第５回共通テスト_R_試作問題.md' -> '共通テスト（R試作）'
    """
    match = re.match(r"\d{4}(.+?)_問題", filename)
    if not match:
        # _問題 なし（例: 2024一橋大学.md）
        match = re.match(r"\d{4}(.+?)\.md$", filename)
    if not match:
        match = re.match(r"\d{4}(.+)$", filename)
    raw = match.group(1) if match else filename.replace(".md", "")
    return _normalize_kyotsu_test(raw)


def _normalize_kyotsu_test(raw: str) -> str:
    """共通テスト系・試行調査の大学名を正規化する。

    '第５回共通テスト_R_本試験' → '共通テスト（R本試験）'
    '2025第５回共通テスト_R_試作問題' → '共通テスト（R試作）'
    '第１回試行調査_R' → '共通テスト（R試行調査1）'
    """
    # 試行調査 → 共通テスト系として扱う
    m_shikou = re.search(r"第([０-９\d]+)回試行調査(?:_(.+))?", raw)
    if m_shikou:
        # 全角→半角数字変換
        num = m_shikou.group(1).translate(str.maketrans("０１２３４５６７８９", "0123456789"))
        suffix = m_shikou.group(2) or ""
        suffix = suffix.replace("_", "")
        label = f"{suffix}試行調査{num}" if suffix else f"試行調査{num}"
        return f"共通テスト（{label}）"

    if "共通テスト" not in raw:
        return raw
    m = re.search(r"共通テスト(?:_(.+))?", raw)
    if not m or not m.group(1):
        return "共通テスト"
    suffix = m.group(1)  # e.g., "R_本試験", "R_試作問題"
    suffix = re.sub(r"問題$", "", suffix)  # Remove trailing 問題
    suffix = suffix.replace("_", "")  # "R_本試験" → "R本試験"
    return f"共通テスト（{suffix}）"


def normalize_year(raw_year) -> Optional[int]:
    """年度を西暦整数に変換する。"""
    if isinstance(raw_year, int):
        return raw_year
    if isinstance(raw_year, str):
        # 西暦パターン: '2025' or '2025年度'
        m = re.search(r"(20\d{2})", raw_year)
        if m:
            return int(m.group(1))
        # 令和パターン: '令和7年度'
        m = re.search(r"令和(\d+)", raw_year)
        if m:
            return int(m.group(1)) + 2018
        # 平成パターン (念のため)
        m = re.search(r"平成(\d+)", raw_year)
        if m:
            return int(m.group(1)) + 1988
    return None


def normalize_fullwidth_roman(s: str) -> str:
    """全角ローマ数字（Ⅰ-Ⅹ）を半角ASCII表現に変換する。"""
    fw_to_ascii = {
        "Ⅰ": "I", "Ⅱ": "II", "Ⅲ": "III", "Ⅳ": "IV", "Ⅴ": "V",
        "Ⅵ": "VI", "Ⅶ": "VII", "Ⅷ": "VIII", "Ⅸ": "IX", "Ⅹ": "X",
    }
    for fw, ascii_val in fw_to_ascii.items():
        s = s.replace(fw, ascii_val)
    return s


_ARABIC_TO_ROMAN = {
    "1": "I", "2": "II", "3": "III", "4": "IV", "5": "V",
    "6": "VI", "7": "VII", "8": "VIII", "9": "IX", "10": "X",
}


def normalize_question_number(raw: str) -> str:
    """Question番号を統一形式に変換する。

    'Question 1' -> 'I', 'Question II' -> 'II', 'Question IV' -> 'IV'
    アルファベット (A, B, C...) はそのまま保持する。
    """
    raw = normalize_fullwidth_roman(raw.strip())
    # ローマ数字ならそのまま
    if re.match(r"^[IVX]+$", raw):
        return raw
    # アラビア数字ならローマ数字に変換
    # アラビア数字+アルファベット (共通テスト: "1A" -> "I-A")
    m = re.match(r"^(\d+)([A-Z])$", raw)
    if m and m.group(1) in _ARABIC_TO_ROMAN:
        return _ARABIC_TO_ROMAN[m.group(1)] + "-" + m.group(2)
    # ハイフン付きサブ番号の場合、先頭部分のみ変換 (例: "3-1" -> "III-1")
    m = re.match(r"^(\d+)(-\d+)$", raw)
    if m and m.group(1) in _ARABIC_TO_ROMAN:
        return _ARABIC_TO_ROMAN[m.group(1)] + m.group(2)
    return _ARABIC_TO_ROMAN.get(raw, raw)


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """フロントマター（YAML）を抽出し、残りの本文を返す。"""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        return {}, content
    try:
        fm = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        fm = {}
    body = content[match.end():]
    return fm, body


def split_questions(body: str) -> list[tuple[str, str]]:
    """本文を `# Question ...` 等で大問ブロックに分割する。

    対応パターン:
        # Question I / # Question 1 / # Question [1] / # Question (I)
        # Question A / # Question B (アルファベット識別子)
        # Question Ⅰ (全角ローマ数字)
        # Question III-1 (ハイフン付きサブ番号)
        # Question III (注記...) / # Question 1 (Continued)
        # Problem I / # Section 1
        # 問題I / # 問題1 / # 問題Ⅰ
        # 第1問 / # 第2問 / # 第1問A (共通テスト)

    Returns:
        List of (question_identifier, block_content)
        question_identifier は '1', 'I', 'A', 'III-1' などの番号部分
    """
    # 全角ローマ数字を半角に変換してからマッチ
    normalized_body = normalize_fullwidth_roman(body)

    # 識別子パターン: ローマ数字、アラビア数字、アルファベット（ハイフン付きサブ番号含む）
    IDENT = r"[IVX]+(?:-\d+)?|\d+[A-Z]?(?:-\d+)?|[A-Z]"
    pattern = re.compile(
        r"^# (?:"
        r"(?:Question|Problem|Section)\s+[\[\(]?(" + IDENT + r")[\]\)]?(?:\s+\(.*?\))?"
        r"|問題\s*(" + IDENT + r")"
        r"|第(\d+)問\s*([A-Z])?"
        r")\s*$",
        re.MULTILINE
    )
    matches = list(pattern.finditer(normalized_body))
    if not matches:
        return []

    blocks: list[tuple[str, str, bool]] = []
    for i, m in enumerate(matches):
        # group(1): Question/Problem/Section, group(2): 問題, group(3): 第N問, group(4): A/B suffix
        q_id = m.group(1) or m.group(2)
        if q_id is None:
            q_id = m.group(3)
            if m.group(4):
                q_id += m.group(4)  # "1" + "A" -> "1A"
        # (Continued), (cont.), (Part B) 等 → 前の同一q_idブロックにマージ
        paren_text = m.group(0)
        is_continued = ("(Continued)" in paren_text
                        or "(cont.)" in paren_text
                        or re.search(r"\(Part [A-Z]\)", paren_text) is not None)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        # body（元テキスト）から切り出す（normalized_bodyと同じ長さ保証）
        block_content = body[start:end].strip()
        blocks.append((q_id, block_content, is_continued))

    # チャンク分割起因のq_id補正
    # 1. アルファベット単体("B"等) → 直前のq_idが"NA"形式なら"NB"に補正
    # 2. "N" → 直前が"NA"/"NB"形式なら最後のサブIDにマージ
    for i in range(len(blocks)):
        q_id = blocks[i][0]
        if i == 0:
            continue
        prev_id = blocks[i - 1][0]
        # パターン1: "B" → "6B" （直前が "6A" のとき）
        if re.match(r"^[A-Z]$", q_id):
            m_prev = re.match(r"^(\d+)[A-Z]$", prev_id)
            if m_prev:
                blocks[i] = (m_prev.group(1) + q_id, blocks[i][1], blocks[i][2])
        # パターン2: "3" → 直前が "3B"/"3A" のとき、"3B"にマージ
        elif re.match(r"^\d+$", q_id):
            m_prev = re.match(r"^(\d+)[A-Z]$", prev_id)
            if m_prev and m_prev.group(1) == q_id:
                blocks[i] = (prev_id, blocks[i][1], True)  # マージフラグをTrueに

    # 同一q_idの連続ブロックをマージ（(Continued) やチャンク分割による重複を統合）
    merged: list[tuple[str, str]] = []
    for q_id, content, is_continued in blocks:
        if merged and merged[-1][0] == q_id:
            prev_id, prev_content = merged[-1]
            merged[-1] = (prev_id, prev_content + "\n\n" + content)
        else:
            merged.append((q_id, content))

    # 同一q_idの重複を検出し、サフィックスで一意化
    # 例: 大阪公立大の学部別 Question 3 → "3", "3" → "3-1", "3-2"
    from collections import Counter
    id_counts = Counter(q_id for q_id, _ in merged)
    duplicated_ids = {q_id for q_id, count in id_counts.items() if count > 1}
    if duplicated_ids:
        result: list[tuple[str, str]] = []
        dup_counters: dict[str, int] = {}
        for q_id, content in merged:
            if q_id in duplicated_ids:
                dup_counters[q_id] = dup_counters.get(q_id, 0) + 1
                result.append((f"{q_id}-{dup_counters[q_id]}", content))
            else:
                result.append((q_id, content))
        return result

    return merged


def extract_text_section(block: str) -> str:
    """ブロックから ## Text セクションの内容を抽出する。

    複数の ## Text がある場合は連結する（東京大 Q1 の(A)(B)対応）。
    Text が空（[ ] のみ等）の場合、## Data → ## Instructions の順にフォールバック。
    """
    # 任意の ## ヘッダーをセクション境界とする（Options, Part A 等にも対応）
    SECTION_BOUNDARY = r"^## \S"

    # 全 ## Text セクションを収集
    text_parts = []
    for m in re.finditer(r"^## Text\s*\n", block, re.MULTILINE):
        start = m.end()
        next_section = re.search(SECTION_BOUNDARY, block[start:], re.MULTILINE)
        end = start + next_section.start() if next_section else len(block)
        part = block[start:end].strip()
        # [ ] や空のテキストは除外
        if part and not re.match(r"^\[[\s]*\]$", part):
            text_parts.append(part)

    if text_parts:
        return "\n\n".join(text_parts)

    # Text が空の場合、## Data セクションをフォールバック（グラフ・表付き英作文）
    data_match = re.search(r"^## Data\s*\n", block, re.MULTILINE)
    if data_match:
        start = data_match.end()
        next_section = re.search(SECTION_BOUNDARY, block[start:], re.MULTILINE)
        end = start + next_section.start() if next_section else len(block)
        data_text = block[start:end].strip()
        if data_text:
            return data_text

    # ## Instructions 後の本文をテキストとみなす
    inst_match = re.search(r"^## Instructions\s*\n", block, re.MULTILINE)
    if inst_match:
        start = inst_match.end()
        next_section = re.search(SECTION_BOUNDARY, block[start:], re.MULTILINE)
        end = start + next_section.start() if next_section else len(block)
        return block[start:end].strip()

    return block.strip()


def extract_questions_section(block: str) -> str:
    """ブロックから設問情報を抽出する。

    全 ## Instructions + ## Data + ## Questions を結合して返す。
    これにより要約指示・英作文指示・視覚情報なども設問分析に含まれる。
    """
    # 任意の ## ヘッダーをセクション境界とする
    SECTION_BOUNDARY = r"^## \S"
    parts = []

    # 全 ## Instructions セクション（設問指示: 要約せよ、日本語で説明しなさい等）
    for m in re.finditer(r"^## Instructions\s*\n", block, re.MULTILINE):
        start = m.end()
        next_section = re.search(SECTION_BOUNDARY, block[start:], re.MULTILINE)
        end = start + next_section.start() if next_section else len(block)
        content = block[start:end].strip()
        if content:
            parts.append(content)

    # ## Data セクション（視覚情報検出用）
    data_match = re.search(r"^## Data\s*\n", block, re.MULTILINE)
    if data_match:
        start = data_match.end()
        next_section = re.search(SECTION_BOUNDARY, block[start:], re.MULTILINE)
        end = start + next_section.start() if next_section else len(block)
        content = block[start:end].strip()
        if content:
            parts.append(content)

    # ## Questions セクション
    q_match = re.search(r"^## Questions\s*\n", block, re.MULTILINE)
    if q_match:
        start = q_match.end()
        next_section = re.search(SECTION_BOUNDARY, block[start:], re.MULTILINE)
        end = start + next_section.start() if next_section else len(block)
        content = block[start:end].strip()
        if content:
            parts.append(content)

    # ## Options セクション（選択肢リスト）
    opt_match = re.search(r"^## Options\s*\n", block, re.MULTILINE)
    if opt_match:
        start = opt_match.end()
        next_section = re.search(SECTION_BOUNDARY, block[start:], re.MULTILINE)
        end = start + next_section.start() if next_section else len(block)
        content = block[start:end].strip()
        if content:
            parts.append(content)

    return "\n\n".join(parts)



def _split_kyotsu_shisaku(body: str) -> list[tuple[str, str]]:
    """### 第A問 / ### 第B問 形式で分割する（共通テスト試作問題用フォールバック）。

    split_questions() が空を返した場合のフォールバック。
    """
    pattern = re.compile(r"^### 第([A-Z])問\s*$", re.MULTILINE)
    matches = list(pattern.finditer(body))
    if len(matches) < 1:
        return []

    blocks = []
    for i, m in enumerate(matches):
        q_id = m.group(1)  # "A", "B"
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        block_content = body[start:end].strip()
        # 後続の ## セクション（## Data 等）は除外
        h2_match = re.search(r"^## \S", block_content, re.MULTILINE)
        if h2_match:
            block_content = block_content[:h2_match.start()].strip()
        blocks.append((q_id, block_content))

    return blocks


def detect_copyright_omitted(block: str) -> bool:
    """ブロック内に著作権による本文省略を検出する。"""
    # Geminiマーカー
    if "<!-- COPYRIGHT_OMITTED" in block:
        return True
    # フォールバック: 日本語の著作権省略パターン
    patterns = [
        r"著作権.*?(?:省略|非掲載|割愛|掲載.{0,4}できません)",
        r"本文.*?省略",
        r"出典.*?都合.*?省略",
        r"著作物.*?のため.*?(?:省略|非掲載)",
        r"著作権.*?(?:理由|関係).*?(?:省略|非掲載|割愛)",
    ]
    for pat in patterns:
        if re.search(pat, block):
            return True
    return False


def detect_ab_split(text: str) -> list[tuple[str, str]]:
    """テキスト内の (A)/(B) 分割を検出する。

    大阪大のように、Text内に独立した(A)(B)パッセージがある場合に分割する。
    選択肢リスト（各項目が短い）は分割しない。
    """
    # (A) で始まるブロックを検出
    parts = re.split(r"(?m)^(\([A-Z]\))", text)
    if len(parts) < 3:
        return [("1", text)]

    result = []
    idx = 1
    while idx < len(parts) - 1:
        label = parts[idx].strip("()")
        content = parts[idx + 1]
        passage_idx = str(ord(label) - ord("A") + 1)
        result.append((passage_idx, content.strip()))
        idx += 2

    # 各パートが十分な長さ（100語以上）の場合のみ分割とみなす
    # 短い場合は選択肢リストやオプション一覧の可能性が高い
    if len(result) >= 2:
        avg_words = sum(len(c.split()) for _, c in result) / len(result)
        if avg_words >= 100:
            return result

    return [("1", text)]


def generate_passage_id(year: int, university: str, question_number: str, passage_index: int) -> str:
    """パッセージIDを生成する。"""
    return f"{year}_{university}_{question_number}_{passage_index}"


def parse_md(content: str, filename: str) -> list[ParsedQuestion]:
    """MDファイルをパースし、大問ごとのParsedQuestionリストを返す。"""
    fm, body = parse_frontmatter(content)

    # 大学名は常にファイル名から取得（括弧付き名称をそのまま使用）
    university = extract_university_from_filename(filename)

    year = normalize_year(fm.get("year", ""))
    if year is None:
        m = re.match(r"(\d{4})", filename)
        year = int(m.group(1)) if m else 0

    # facultyは使用しない（括弧部分が大学名に含まれるため）
    faculty = ""

    # 大問分割
    question_blocks = split_questions(body)
    if not question_blocks:
        # フォールバック: ### 第A問 / ### 第B問 形式（共通テスト試作問題）
        question_blocks = _split_kyotsu_shisaku(body)

    results: list[ParsedQuestion] = []
    for q_id_raw, block in question_blocks:
        q_num = normalize_question_number(q_id_raw)
        text = extract_text_section(block)
        questions = extract_questions_section(block)

        # 著作権省略チェック（ブロック全体を検査）
        is_copyright_omitted = detect_copyright_omitted(block)

        # テキストが空でも著作権省略の場合はパッセージとして登録する
        if not text.strip() and not is_copyright_omitted:
            continue

        # (A)/(B) 分割チェック
        ab_parts = detect_ab_split(text) if text.strip() else [("1", text)]
        for passage_idx_str, passage_text in ab_parts:
            passage_idx = int(passage_idx_str)
            pid = generate_passage_id(year, university, q_num, passage_idx)
            results.append(
                ParsedQuestion(
                    university=university,
                    year=year,
                    faculty=faculty,
                    question_number=q_num,
                    passage_index=passage_idx,
                    text_section=passage_text,
                    questions_section=questions,
                    passage_id=pid,
                    copyright_omitted=is_copyright_omitted,
                )
            )

    return results
