"""大学分類・地域設定の取得・更新ルーター。"""

from fastapi import APIRouter, HTTPException, Request

from app.db import get_all_universities, get_connection, update_university

router = APIRouter(prefix="/api/universities", tags=["universities"])


@router.get("")
def list_universities():
    conn = get_connection()
    try:
        return get_all_universities(conn)
    finally:
        conn.close()


@router.put("/{name}")
async def update_university_route(name: str, request: Request):
    body = await request.json()
    university_class = body.get("university_class", "")
    region = body.get("region", "")
    conn = get_connection()
    try:
        ok = update_university(conn, name, university_class, region)
    finally:
        conn.close()
    if not ok:
        raise HTTPException(status_code=404, detail="大学が見つかりません")
    return {"ok": True}
