"""FastAPIアプリケーション。"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time

import bcrypt
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import (
    ADMIN_PASSWORD_HASH,
    COMP_TYPE_LIST,
    GENRE_MAIN_LIST,
    SECRET_KEY,
    SESSION_MAX_AGE,
    TEXT_STYLE_LIST,
    TEXT_TYPE_LIST,
)
from app.db import get_connection, init_db
from app.routers import dashboard, export, passages, upload

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="入試問題分析システム")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ルーター登録
app.include_router(upload.router)
app.include_router(passages.router)
app.include_router(dashboard.router)
app.include_router(export.router)

PUBLIC_PATHS = ("/login", "/static", "/favicon.ico")


def _make_session_token(timestamp: int) -> str:
    """HMACベースのセッショントークンを生成する。"""
    msg = f"session:{timestamp}".encode()
    sig = hmac.new(SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()
    return f"{timestamp}:{sig}"


def _verify_session_token(token: str) -> bool:
    """セッショントークンを検証する。"""
    try:
        ts_str, sig = token.split(":", 1)
        timestamp = int(ts_str)
        if time.time() - timestamp > SESSION_MAX_AGE:
            return False
        expected = _make_session_token(timestamp)
        return hmac.compare_digest(token, expected)
    except (ValueError, AttributeError):
        return False


@app.on_event("startup")
async def startup():
    init_db()
    logger.info("Database initialized")


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # 認証が未設定の場合はスキップ
    if not ADMIN_PASSWORD_HASH:
        return await call_next(request)

    # ポータル経由の場合はスキップ（Caddyのforward_authが認証済み）
    if os.environ.get("BEHIND_PORTAL") == "true" and request.headers.get("X-Portal-Role"):
        return await call_next(request)

    if any(request.url.path.startswith(p) for p in PUBLIC_PATHS):
        return await call_next(request)

    session = request.cookies.get("session")
    if not session or not _verify_session_token(session):
        return RedirectResponse("/login", status_code=302)

    return await call_next(request)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(request: Request):
    form = await request.form()
    password = form.get("password", "")

    if ADMIN_PASSWORD_HASH and bcrypt.checkpw(
        password.encode(), ADMIN_PASSWORD_HASH.encode()
    ):
        token = _make_session_token(int(time.time()))
        response = RedirectResponse("/", status_code=302)
        response.set_cookie(
            "session", token,
            max_age=SESSION_MAX_AGE,
            httponly=True,
            samesite="lax",
        )
        return response

    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "パスワードが正しくありません"},
    )


@app.post("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("session")
    return response


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    conn = get_connection()
    try:
        # フィルタ用のデータ取得
        years = [r["year"] for r in conn.execute("SELECT DISTINCT year FROM passages ORDER BY year DESC").fetchall()]
        universities = [r["university"] for r in conn.execute("SELECT DISTINCT university FROM passages ORDER BY university").fetchall()]
        total = conn.execute("SELECT COUNT(*) as cnt FROM passages").fetchone()["cnt"]
        reviewed = conn.execute("SELECT COUNT(*) as cnt FROM passages WHERE reviewed = 1").fetchone()["cnt"]
    finally:
        conn.close()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "years": years,
            "universities": universities,
            "genre_list": GENRE_MAIN_LIST,
            "text_type_list": TEXT_TYPE_LIST,
            "text_style_list": TEXT_STYLE_LIST,
            "comp_type_list": COMP_TYPE_LIST,
            "total": total,
            "reviewed": reviewed,
        },
    )
