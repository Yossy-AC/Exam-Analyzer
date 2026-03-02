"""ファイルアップロード・解析エンドポイント。"""

from __future__ import annotations

import asyncio
import logging
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.classifier import classify_passage
from app.config import INPUT_MD_DIR
from app.db import get_connection
from app.parser import parse_md

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _save_passage(data: dict) -> None:
    """分類結果をDBに保存する。既存IDはスキップ。"""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO passages
            (id, university, year, faculty, question_number, passage_index,
             text_type, text_style, word_count,
             source_title, source_author, source_year,
             genre_main, genre_sub, theme,
             has_jp_written, has_en_written, has_summary, comp_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                data.get("comp_type", "none"),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _update_job(job_id: int, status: str, passages_created: int = 0, error_message: str = None) -> None:
    conn = get_connection()
    try:
        if status in ("completed", "error"):
            conn.execute(
                "UPDATE analysis_jobs SET status=?, passages_created=?, error_message=?, completed_at=? WHERE id=?",
                (status, passages_created, error_message, datetime.now().isoformat(), job_id),
            )
        else:
            conn.execute(
                "UPDATE analysis_jobs SET status=?, passages_created=?, error_message=? WHERE id=?",
                (status, passages_created, error_message, job_id),
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
            _update_job(job_id, "completed", 0, "パッセージが抽出できませんでした")
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
        for pq in new_passages:
            try:
                result = await classify_passage(pq)
                _save_passage(result)
                count += 1
                logger.info("Classified: %s", result["id"])
            except Exception as e:
                logger.error("Classification failed for %s: %s", pq.passage_id, e)

        _update_job(job_id, "completed", count)

    except Exception as e:
        logger.error("Processing failed for %s: %s", filename, e)
        _update_job(job_id, "error", 0, str(e))


@router.post("/api/upload")
async def upload_files(request: Request, files: list[UploadFile], background_tasks: BackgroundTasks):
    """MDファイルをアップロードして解析を開始する。"""
    Path(INPUT_MD_DIR).mkdir(parents=True, exist_ok=True)
    job_ids = []

    for file in files:
        if not file.filename or not file.filename.endswith(".md"):
            continue

        content_bytes = await file.read()
        content = content_bytes.decode("utf-8")

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


@router.get("/api/jobs")
async def get_jobs(request: Request):
    """解析ジョブの状況一覧を返す。"""
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
