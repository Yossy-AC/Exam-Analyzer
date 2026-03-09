"""ファイルアップロード・解析エンドポイント。"""

from __future__ import annotations

import asyncio
import logging
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.auth import is_student
from app.classifier import classify_passage
from app.config import (
    GEMINI_PROMPT_FILE,
    GEMINI_REQUEST_INTERVAL_SEC,
    INPUT_MD_DIR,
    TEMP_PDF_DIR,
)
from app.db import get_connection
from app.embedding import embed_text, encode_embedding
from app.gemini_convert import convert_pdf_to_markdown, is_scanned_pdf, parse_filename
from app.parser import parse_md
from app.vocab_analyzer import analyze_vocab

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="templates")


async def _save_passage(data: dict) -> None:
    """分類結果をDBに保存する。既存IDはスキップ。未登録大学は自動追加。"""
    # long_readingの場合、語彙分析を実行
    import json
    text_body = data.get("text_body", "")
    vocab = {}
    embedding_blob = None
    if data.get("text_type") == "long_reading" and text_body:
        vocab = analyze_vocab(text_body)
        # embedding生成（エラーは無視してNULLのまま保存）
        try:
            vec = await embed_text(text_body)
            if vec:
                embedding_blob = encode_embedding(vec)
        except Exception as e:
            logger.warning("embedding生成失敗 %s: %s", data.get("id"), e)

    conn = get_connection()
    try:
        # 未登録大学を universities テーブルに自動追加（FK制約対応）
        conn.execute(
            "INSERT OR IGNORE INTO universities (name, is_kyutei, is_national, is_private) VALUES (?, 0, 1, 0)",
            (data["university"],),
        )
        conn.execute(
            """INSERT OR IGNORE INTO passages
            (id, university, year, faculty, question_number, passage_index,
             text_type, text_style, word_count,
             source_title, source_author, source_year,
             genre_main, genre_sub, theme,
             has_jp_written, has_en_written, has_summary, has_wabun_eiyaku, has_jiyu_eisakubun,
             has_jp_translation, has_jp_explanation, has_en_explanation,
             has_jp_summary, has_en_summary,
             has_visual_info, visual_info_type,
             low_confidence, low_confidence_fields,
             text_body, avg_sentence_length,
             cefr_j_beyond_rate, cefr_j_profile,
             ngsl_uncovered_rate, nawl_rate,
             target1900_coverage, target1900_profile,
             leap_coverage, leap_profile, embedding)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data["id"], data["university"], data["year"], data["faculty"],
                data["question_number"], data["passage_index"],
                data["text_type"], data.get("text_style"),
                data.get("word_count"),
                data.get("source_title"), data.get("source_author"),
                data.get("source_year"),
                data["genre_main"], data.get("genre_sub", ""),
                data.get("theme", ""),
                data.get("has_jp_written", False),
                data.get("has_en_written", False),
                data.get("has_summary", False),
                data.get("has_wabun_eiyaku", False),
                data.get("has_jiyu_eisakubun", False),
                data.get("has_jp_translation", False),
                data.get("has_jp_explanation", False),
                data.get("has_en_explanation", False),
                data.get("has_jp_summary", False),
                data.get("has_en_summary", False),
                data.get("has_visual_info", False),
                data.get("visual_info_type", ""),
                data.get("low_confidence", False),
                data.get("low_confidence_fields", ""),
                text_body,
                vocab.get("avg_sentence_length"),
                vocab.get("cefr_j_beyond_rate"),
                json.dumps(vocab.get("cefr_j_profile", {})),
                vocab.get("ngsl_uncovered_rate"),
                vocab.get("nawl_rate"),
                vocab.get("target1900_coverage"),
                json.dumps(vocab.get("target1900_profile", {})),
                vocab.get("leap_coverage"),
                json.dumps(vocab.get("leap_profile", {})),
                embedding_blob,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _update_job(
    job_id: int,
    status: str,
    passages_created: int = 0,
    error_message: str = None,
    current_step: str = "",
) -> None:
    conn = get_connection()
    try:
        if status in ("completed", "error"):
            conn.execute(
                "UPDATE analysis_jobs SET status=?, passages_created=?, error_message=?, current_step=?, completed_at=? WHERE id=?",
                (status, passages_created, error_message, current_step, datetime.now().isoformat(), job_id),
            )
        else:
            conn.execute(
                "UPDATE analysis_jobs SET status=?, passages_created=?, error_message=?, current_step=? WHERE id=?",
                (status, passages_created, error_message, current_step, job_id),
            )
        conn.commit()
    finally:
        conn.close()


async def _process_file(job_id: int, filename: str, content: str) -> None:
    """1ファイルを解析する非同期タスク。"""
    _update_job(job_id, "processing")
    try:
        passages = parse_md(content, filename)
        if not passages:
            _update_job(job_id, "completed", 0, f"[MD解析] パッセージが抽出できませんでした。見出し構造(## )を確認してください")
            return

        # 既にDB登録済みのIDをチェック
        conn = get_connection()
        existing_ids = set()
        try:
            rows = conn.execute("SELECT id FROM passages").fetchall()
            existing_ids = {r["id"] for r in rows}
        finally:
            conn.close()

        new_passages = [p for p in passages if p.passage_id not in existing_ids]
        if not new_passages:
            _update_job(job_id, "completed", 0, "全パッセージが登録済みです")
            return

        count = 0
        errors = []
        for pq in new_passages:
            try:
                result = await classify_passage(pq)
                await _save_passage(result)
                count += 1
                logger.info("Classified: %s", result["id"])
            except Exception as e:
                logger.error("Classification failed for %s: %s", pq.passage_id, e)
                errors.append(f"{pq.passage_id}")

        error_msg = f"[Claude分類] {len(errors)}件失敗: {', '.join(errors)}" if errors else None
        _update_job(job_id, "completed", count, error_msg)

    except Exception as e:
        logger.error("Processing failed for %s: %s", filename, e)
        _update_job(job_id, "error", 0, f"[MD解析] {e}")


@router.post("/api/upload")
async def upload_files(request: Request, files: list[UploadFile], background_tasks: BackgroundTasks):
    """MDファイルをアップロードして解析を開始する。"""
    if is_student(request):
        return JSONResponse({"error": "権限がありません"}, status_code=403)
    Path(INPUT_MD_DIR).mkdir(parents=True, exist_ok=True)
    job_ids = []

    MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB

    for file in files:
        if not file.filename or not file.filename.endswith(".md"):
            continue

        content_bytes = await file.read()
        if len(content_bytes) > MAX_UPLOAD_SIZE:
            logger.warning("Upload too large: %s (%d bytes)", file.filename, len(content_bytes))
            continue
        try:
            content = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            logger.warning("Non-UTF-8 file skipped: %s", file.filename)
            continue

        # ファイルを保存
        save_path = Path(INPUT_MD_DIR) / file.filename
        save_path.write_text(content, encoding="utf-8")

        # ジョブ作成
        conn = get_connection()
        try:
            cursor = conn.execute(
                "INSERT INTO analysis_jobs (filename, status) VALUES (?, 'pending')",
                (file.filename,),
            )
            job_id = cursor.lastrowid
            conn.commit()
        finally:
            conn.close()

        job_ids.append(job_id)
        background_tasks.add_task(_process_file, job_id, file.filename, content)

    return templates.TemplateResponse(
        "partials/upload_progress.html",
        {"request": request, "job_ids": job_ids, "total": len(job_ids)},
    )


@router.post("/api/upload-all")
async def upload_all_files(request: Request, files: list[UploadFile], background_tasks: BackgroundTasks):
    """MD/PDFファイルを自動判別してアップロード・解析を開始する。"""
    if is_student(request):
        return JSONResponse({"error": "権限がありません"}, status_code=403)

    Path(INPUT_MD_DIR).mkdir(parents=True, exist_ok=True)
    temp_dir = Path(TEMP_PDF_DIR)
    temp_dir.mkdir(parents=True, exist_ok=True)
    job_ids = []

    MAX_MD_SIZE = 10 * 1024 * 1024   # 10MB
    MAX_PDF_SIZE = 50 * 1024 * 1024  # 50MB

    for file in files:
        if not file.filename:
            continue
        fname_lower = file.filename.lower()

        if fname_lower.endswith(".md"):
            content_bytes = await file.read()
            if len(content_bytes) > MAX_MD_SIZE:
                logger.warning("MD too large: %s (%d bytes)", file.filename, len(content_bytes))
                continue
            try:
                content = content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                logger.warning("Non-UTF-8 file skipped: %s", file.filename)
                continue

            save_path = Path(INPUT_MD_DIR) / file.filename
            save_path.write_text(content, encoding="utf-8")

            conn = get_connection()
            try:
                cursor = conn.execute(
                    "INSERT INTO analysis_jobs (filename, status, source_type) VALUES (?, 'pending', 'md')",
                    (file.filename,),
                )
                job_id = cursor.lastrowid
                conn.commit()
            finally:
                conn.close()

            job_ids.append(job_id)
            background_tasks.add_task(_process_file, job_id, file.filename, content)

        elif fname_lower.endswith(".pdf"):
            content_bytes = await file.read()
            if len(content_bytes) > MAX_PDF_SIZE:
                logger.warning("PDF too large: %s (%d bytes)", file.filename, len(content_bytes))
                continue

            pdf_path = temp_dir / file.filename
            pdf_path.write_bytes(content_bytes)

            conn = get_connection()
            try:
                cursor = conn.execute(
                    "INSERT INTO analysis_jobs (filename, status, source_type) VALUES (?, 'pending', 'pdf')",
                    (file.filename,),
                )
                job_id = cursor.lastrowid
                conn.commit()
            finally:
                conn.close()

            job_ids.append(job_id)
            background_tasks.add_task(_process_pdf_file, job_id, file.filename, str(pdf_path))

    return templates.TemplateResponse(
        "partials/upload_progress.html",
        {"request": request, "job_ids": job_ids, "total": len(job_ids)},
    )


@router.get("/api/jobs")
async def get_jobs(request: Request):
    """解析ジョブの状況一覧を返す。"""
    if is_student(request):
        return JSONResponse({"error": "権限がありません"}, status_code=403)
    conn = get_connection()
    try:
        jobs = conn.execute(
            "SELECT * FROM analysis_jobs ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
    finally:
        conn.close()

    return templates.TemplateResponse(
        "partials/job_status.html",
        {"request": request, "jobs": jobs},
    )


@router.get("/api/review-list")
async def get_review_list(request: Request):
    """要確認リスト（エラージョブ・低抽出数・データ問題）を返す。"""
    if is_student(request):
        return JSONResponse({"error": "権限がありません"}, status_code=403)
    conn = get_connection()
    try:
        problem_jobs = conn.execute("""
            SELECT id, filename, status, passages_created, error_message, created_at
            FROM analysis_jobs j
            WHERE (status = 'error'
               OR (status = 'completed' AND passages_created <= 2))
              AND error_message IS NOT '全パッセージが登録済みです'
              AND COALESCE(reviewed, 0) = 0
              AND NOT EXISTS (
                  SELECT 1 FROM analysis_jobs j2
                  WHERE j2.filename = j.filename
                    AND j2.id > j.id
                    AND j2.status = 'completed'
                    AND j2.passages_created > 2
              )
              AND j.id = (
                  SELECT MAX(j3.id) FROM analysis_jobs j3
                  WHERE j3.filename = j.filename
              )
            ORDER BY created_at DESC
        """).fetchall()

        problem_passages = conn.execute("""
            SELECT id, university, year, question_number, passage_index,
                   genre_main, theme, low_confidence, low_confidence_fields
            FROM passages
            WHERE genre_main = 'その他'
               OR theme IN ('不明', '内容不明')
               OR low_confidence = 1
            ORDER BY low_confidence DESC, year DESC, university, question_number
        """).fetchall()
    finally:
        conn.close()

    return templates.TemplateResponse(
        "partials/review_list.html",
        {"request": request, "problem_jobs": problem_jobs, "problem_passages": problem_passages},
    )


@router.delete("/api/review-list/job/{job_id}")
async def dismiss_review_job(request: Request, job_id: int):
    """要確認リストからジョブを除外する（reviewed フラグを立てる）。"""
    if is_student(request):
        return JSONResponse({"error": "権限がありません"}, status_code=403)
    conn = get_connection()
    try:
        conn.execute("UPDATE analysis_jobs SET reviewed = 1 WHERE id = ?", (job_id,))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


# =============================================
# PDF一括アップロード
# =============================================

_pdf_semaphore = asyncio.Semaphore(1)


async def _process_pdf_file(job_id: int, filename: str, pdf_path: str) -> None:
    """PDFファイルをGemini変換→MD解析→Claude分類→DB保存する非同期タスク。"""
    async with _pdf_semaphore:
        current_step = "gemini_converting"
        try:
            # Step 1: Gemini変換
            _update_job(job_id, "processing", current_step="gemini_converting")
            stem = Path(pdf_path).stem
            year, university = parse_filename(stem)

            prompt_text = GEMINI_PROMPT_FILE.read_text(encoding="utf-8")
            filled_prompt = prompt_text.replace("{university}", university).replace("{year}", year)

            scanned = is_scanned_pdf(pdf_path)
            if scanned:
                logger.info("スキャンPDFと判定: %s", filename)

            md_text, in_tok, out_tok = await convert_pdf_to_markdown(pdf_path, filled_prompt)
            logger.info("Gemini変換完了: %s (in=%d, out=%d)", filename, in_tok, out_tok)

            # 変換後MDを保存
            md_filename = stem + ".md"
            Path(INPUT_MD_DIR).mkdir(parents=True, exist_ok=True)
            md_path = Path(INPUT_MD_DIR) / md_filename
            md_path.write_text(md_text, encoding="utf-8")

            # 一時PDFを削除
            try:
                Path(pdf_path).unlink()
            except OSError:
                pass

            # Step 2: MD解析
            current_step = "parsing"
            _update_job(job_id, "processing", current_step="parsing")
            passages = parse_md(md_text, md_filename)
            if not passages:
                _update_job(job_id, "completed", 0, "[MD解析] Gemini変換後のMDからパッセージが抽出できませんでした")
                return

            # 既存ID重複チェック
            conn = get_connection()
            try:
                rows = conn.execute("SELECT id FROM passages").fetchall()
                existing_ids = {r["id"] for r in rows}
            finally:
                conn.close()

            new_passages = [p for p in passages if p.passage_id not in existing_ids]
            if not new_passages:
                _update_job(job_id, "completed", 0, "全パッセージが登録済みです")
                return

            # Step 3: Claude分類 + DB保存
            current_step = "classifying"
            _update_job(job_id, "processing", current_step="classifying")
            count = 0
            errors = []
            for pq in new_passages:
                try:
                    result = await classify_passage(pq)
                    await _save_passage(result)
                    count += 1
                    logger.info("Classified: %s", result["id"])
                except Exception as e:
                    logger.error("Classification failed for %s: %s", pq.passage_id, e)
                    errors.append(f"{pq.passage_id}")

            error_msg = f"[Claude分類] {len(errors)}件失敗: {', '.join(errors)}" if errors else None
            _update_job(job_id, "completed", count, error_msg)

        except Exception as e:
            step_label = {"gemini_converting": "Gemini変換", "parsing": "MD解析", "classifying": "Claude分類"}.get(current_step, current_step)
            logger.error("PDF processing failed at %s for %s: %s", step_label, filename, e)
            _update_job(job_id, "error", 0, f"[{step_label}] {e}", current_step=current_step)

        # Gemini APIレート制限対策
        await asyncio.sleep(GEMINI_REQUEST_INTERVAL_SEC)


@router.post("/api/upload-pdf")
async def upload_pdf_files(request: Request, files: list[UploadFile], background_tasks: BackgroundTasks):
    """PDFファイルをアップロードしてGemini変換→解析を開始する。"""
    if is_student(request):
        return JSONResponse({"error": "権限がありません"}, status_code=403)

    temp_dir = Path(TEMP_PDF_DIR)
    temp_dir.mkdir(parents=True, exist_ok=True)
    job_ids = []

    MAX_PDF_SIZE = 50 * 1024 * 1024  # 50MB

    for file in files:
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            continue

        content_bytes = await file.read()
        if len(content_bytes) > MAX_PDF_SIZE:
            logger.warning("PDF too large: %s (%d bytes)", file.filename, len(content_bytes))
            continue

        # 一時ディレクトリにPDF保存
        pdf_path = temp_dir / file.filename
        pdf_path.write_bytes(content_bytes)

        # ジョブ作成
        conn = get_connection()
        try:
            cursor = conn.execute(
                "INSERT INTO analysis_jobs (filename, status, source_type) VALUES (?, 'pending', 'pdf')",
                (file.filename,),
            )
            job_id = cursor.lastrowid
            conn.commit()
        finally:
            conn.close()

        job_ids.append(job_id)
        background_tasks.add_task(_process_pdf_file, job_id, file.filename, str(pdf_path))

    return templates.TemplateResponse(
        "partials/upload_progress.html",
        {"request": request, "job_ids": job_ids, "total": len(job_ids)},
    )
