"""MDファイルパーサー: 入試問題MDを大問単位に分割し、Text/Questionsセクションを抽出する。"""

from __future__ import annotations

import re
from typing import Optional

import yaml

from app.models import ParsedQuestion


def extract_university_from_filename(filename: str) -> str:
    """ファイル名から大学名を抽出（フロントマター異常時のフォールバック）。

    Examples:
        '2025東京大_問題.md' -> '東京大'
        '2025大阪大（外国語以外）_問題.md' -> '大阪大'
    """
    match = re.match(r"\d{4}(.+?)(?:[（(].+?[）)])?_問題", filename)
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


def normalize_question_number(raw: str) -> str:
    """Question番号を統一形式に変換する。

    'Question 1' -> 'I', 'Question II' -> 'II', 'Question IV' -> 'IV'
    """
    raw = raw.strip()
    # ローマ数字ならそのまま
    if re.match(r"^[IVX]+$", raw):
        return raw
    # アラビア数字ならローマ数字に変換
    arabic_to_roman = {
        "1": "I", "2": "II", "3": "III", "4": "IV", "5": "V",
        "6": "VI", "7": "VII", "8": "VIII", "9": "IX", "10": "X",
    }
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
    """本文を `# Question ...` で大問ブロックに分割する。

    Returns:
        List of (question_identifier, block_content)
        question_identifier は '1', 'I', '2', 'II' などの番号部分
    """
    # `# Question 1`, `# Question I`, `# Question [1]`, `# Question 1 (Continued)` にマッチ
    # `# Question [ ]` のような不正パターンは除外
    pattern = re.compile(
        r"^# Question\s+\[?([IVX]+|\d+)\]?(?:\s+\(Continued\))?\s*$", re.MULTILINE
    )
    matches = list(pattern.finditer(body))
    if not matches:
        return []

    blocks: list[tuple[str, str, bool]] = []
    for i, m in enumerate(matches):
        q_id = m.group(1)
        is_continued = "(Continued)" in m.group(0)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
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

    return merged


def extract_text_section(block: str) -> str:
    """ブロックから ## Text セクションの内容を抽出する。

    ## Text がない場合、## Instructions の後～次の ## の前をTextとみなす。
    """
    # ## Text セクションを探す
    text_match = re.search(r"^## Text\s*\n", block, re.MULTILINE)
    if text_match:
        start = text_match.end()
        # 次の ## (ただし ## Vocabulary, ## Data, ## Questions, ## Instructions)
        next_section = re.search(r"^## (?:Questions|Vocabulary|Data|Instructions)\s*$", block[start:], re.MULTILINE)
        end = start + next_section.start() if next_section else len(block)
        return block[start:end].strip()

    # ## Text がない場合は Instructions 後の本文をテキストとみなす
    inst_match = re.search(r"^## Instructions\s*\n", block, re.MULTILINE)
    if inst_match:
        start = inst_match.end()
        # Instructions直後の1行目をスキップ（設問指示文）して残りをテキストとして扱う
        next_section = re.search(r"^## ", block[start:], re.MULTILINE)
        end = start + next_section.start() if next_section else len(block)
        text = block[start:end].strip()
        return text

    return block.strip()


def extract_questions_section(block: str) -> str:
    """ブロックから ## Questions セクション以降を抽出する。

    ## Data セクションがある場合は設問情報に含める（視覚情報検出のため）。
    """
    q_match = re.search(r"^## Questions\s*\n", block, re.MULTILINE)
    if q_match:
        return block[q_match.end():].strip()

    # ## Questions がない場合は ## Instructions + ## Data の内容を返す
    inst_match = re.search(r"^## Instructions\s*\n", block, re.MULTILINE)
    if inst_match:
        start = inst_match.end()
        text_match = re.search(r"^## Text\s*\n", block[start:], re.MULTILINE)
        end = start + text_match.start() if text_match else len(block)
        return block[start:end].strip()

    return ""


def detect_ab_split(text: str) -> list[tuple[str, str]]:
    """テキスト内の (A)/(B) 分割を検出する。

    大阪大のように、Text内に独立した(A)(B)パッセージがある場合に分割する。
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

    return result if len(result) >= 2 else [("1", text)]


def generate_passage_id(year: int, university: str, question_number: str, passage_index: int, faculty: str = "") -> str:
    """パッセージIDを生成する。facultyがある場合はIDに含めて一意性を確保。"""
    if faculty:
        return f"{year}_{university}_{faculty}_{question_number}_{passage_index}"
    return f"{year}_{university}_{question_number}_{passage_index}"


def parse_md(content: str, filename: str) -> list[ParsedQuestion]:
    """MDファイルをパースし、大問ごとのParsedQuestionリストを返す。"""
    fm, body = parse_frontmatter(content)

    # フロントマター正規化
    university = fm.get("university", "") or ""
    university = str(university)
    if not university or university == "(不明)" or "不明" in university:
        university = extract_university_from_filename(filename)
    # 「大阪大（外国語）」→ 大学名は「大阪大」、括弧内はfacultyへ
    uni_match = re.match(r"^(.+?)[（(](.+?)[）)]$", university)
    if uni_match:
        university = uni_match.group(1)
        # facultyが空ならフロントマターの括弧情報をfacultyに
        if not fm.get("faculty"):
            fm["faculty"] = uni_match.group(2)

    year = normalize_year(fm.get("year", ""))
    if year is None:
        # ファイル名からフォールバック
        m = re.match(r"(\d{4})", filename)
        year = int(m.group(1)) if m else 0

    faculty = fm.get("faculty", "") or ""
    if isinstance(faculty, list):
        faculty = ", ".join(str(f) for f in faculty) if faculty else ""
    faculty = str(faculty)

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
            pid = generate_passage_id(year, university, q_num, passage_idx, faculty)
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
