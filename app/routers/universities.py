"""大学分類・地域設定の取得・更新ルーター。"""

from fastapi import APIRouter, HTTPException, Request

from app.db import (
    delete_university,
    get_all_universities,
    get_connection,
    rename_university,
    update_university,
)

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


@router.patch("/{name}")
async def rename_university_route(name: str, request: Request):
    body = await request.json()
    new_name = body.get("new_name", "").strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="新しい大学名を入力してください")
    conn = get_connection()
    try:
        ok = rename_university(conn, name, new_name)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    finally:
        conn.close()
    if not ok:
        raise HTTPException(status_code=404, detail="大学が見つかりません")
    return {"ok": True, "new_name": new_name}


@router.delete("/{name}")
async def delete_university_route(name: str):
    conn = get_connection()
    try:
        ok, deleted_passages = delete_university(conn, name)
    finally:
        conn.close()
    if not ok:
        raise HTTPException(status_code=404, detail="大学が見つかりません")
    return {"ok": True, "deleted_passages": deleted_passages}
