"""ポータル連携のロールチェック。"""

from __future__ import annotations

import os

from fastapi import Request


def is_student(request: Request) -> bool:
    """ポータル経由のstudentロールかどうか。"""
    return (
        os.environ.get("BEHIND_PORTAL") == "true"
        and request.headers.get("X-Portal-Role") == "student"
    )
