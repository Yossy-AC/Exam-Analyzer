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
    """
    match = re.match(r"\d{4}(.+?)_問題", filename)
    return match.group(1) if match else filename.replace(".md", "")


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
    arabic_to_roman = {
        "1": "I", "2": "II", "3": "III", "4": "IV", "5": "V",
        "6": "VI", "7": "VII", "8": "VIII", "9": "IX", "10": "X",
    }
    # ハイフン付きサブ番号の場合、先頭部分のみ変換 (例: "3-1" -> "III-1")
    m = re.match(r"^(\d+)(-\d+)$", raw)
    if m and m.group(1) in arabic_to_roman:
        return arabic_to_roman[m.group(1)] + m.group(2)
    return arabic_to_roman.get(raw, raw)


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
        # 第1問 / # 第2問

    Returns:
        List of (question_identifier, block_content)
        question_identifier は '1', 'I', 'A', 'III-1' などの番号部分
    """
    # 全角ローマ数字を半角に変換してからマッチ
    normalized_body = normalize_fullwidth_roman(body)

    # 識別子パターン: ローマ数字、アラビア数字、アルファベット（ハイフン付きサブ番号含む）
    IDENT = r"[IVX]+(?:-\d+)?|\d+(?:-\d+)?|[A-Z]"
    pattern = re.compile(
        r"^# (?:"
        r"(?:Question|Problem|Section)\s+[\[\(]?(" + IDENT + r")[\]\)]?(?:\s+\(.*?\))?"
        r"|問題\s*(" + IDENT + r")"
        r"|第(\d+)問"
        r")\s*$",
        re.MULTILINE
    )
    matches = list(pattern.finditer(normalized_body))
    if not matches:
        return []

    blocks: list[tuple[str, str, bool]] = []
    for i, m in enumerate(matches):
        q_id = m.group(1) or m.group(2) or m.group(3)
        is_continued = "(Continued)" in m.group(0)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        # body（元テキスト）から切り出す（normalized_bodyと同じ長さ保証）
        block_content = body[start:end].strip()
        blocks.append((q_id, block_content, is_continued))

    # (Continued) ブロックを前の大問にマージ
    merged: list[tuple[str, str]] = []
    for q_id, content, is_continued in blocks:
        if is_continued and merged and merged[-1][0] == q_id:
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
        return []

    results: list[ParsedQuestion] = []
    for q_id_raw, block in question_blocks:
        q_num = normalize_question_number(q_id_raw)
        text = extract_text_section(block)
        questions = extract_questions_section(block)

        if not text.strip():
            continue

        # (A)/(B) 分割チェック
        ab_parts = detect_ab_split(text)
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
                )
            )

    return results
