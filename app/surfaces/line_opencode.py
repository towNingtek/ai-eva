"""LINE ↔ opencode session 映射（workflow 層）。

當 `OPENCODE_SERVE_BASE` 有值時，`line_session.chat()` 把對話路由到 opencode serve：
- 每個 LINE 對話（line_session）對應一個 opencode session（1:1），記憶在 opencode 那側
- 映射存 PG 表 `line_opencode_sessions`，ai-eva 重啟不掉
- 新 opencode session 的第一則訊息先注入 persona（EVA_SYSTEM_PROMPT），維持既有語氣
- 模型策略：
  - 純文字：不強制 model，session 目前模型繼續（Desktop 換的模型 LINE 跟著用）
  - 圖片：session 目前模型支援多模態就沿用；不支援就暫切 vision 模型，
    記 `temp_vision` 旗標，下一則文字自動切回原本的 model

HTTP 細節（建 session / 送訊息 / 查模型）在 `app/core/opencode.py`（無狀態 primitive）；
這層只管 LINE 專屬的 session 映射與模型切換 workflow。
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import asyncpg

from app.core import opencode

logger = logging.getLogger(__name__)

_DATABASE_URL = os.getenv("DATABASE_URL", "")

# re-export：caller（line_session.py）只需要認得這個模組
is_enabled = opencode.is_enabled


def _pg_url() -> str:
    return _DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


async def ensure_line_opencode_table() -> None:
    if not _DATABASE_URL:
        return
    conn = await asyncpg.connect(_pg_url())
    try:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS line_opencode_sessions (
                line_session_id     BIGINT PRIMARY KEY
                                    REFERENCES line_sessions(id) ON DELETE CASCADE,
                user_id             TEXT NOT NULL,
                opencode_session_id TEXT NOT NULL,
                model               TEXT,
                temp_vision         BOOLEAN NOT NULL DEFAULT FALSE,
                created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_used_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
        await conn.execute(
            "ALTER TABLE line_opencode_sessions "
            "ADD COLUMN IF NOT EXISTS temp_vision BOOLEAN NOT NULL DEFAULT FALSE"
        )
    finally:
        await conn.close()


async def _get_mapping_row(line_session_id: int) -> Optional[dict]:
    """回完整 mapping row：{opencode_session_id, model, temp_vision} 或 None。"""
    if not _DATABASE_URL:
        return None
    conn = await asyncpg.connect(_pg_url())
    try:
        row = await conn.fetchrow(
            "SELECT opencode_session_id, model, temp_vision "
            "FROM line_opencode_sessions WHERE line_session_id = $1",
            line_session_id,
        )
        return dict(row) if row else None
    finally:
        await conn.close()


async def _store_mapping(
    line_session_id: int, user_id: str, opencode_session_id: str
) -> None:
    if not _DATABASE_URL:
        return
    conn = await asyncpg.connect(_pg_url())
    try:
        await conn.execute(
            """
            INSERT INTO line_opencode_sessions
                (line_session_id, user_id, opencode_session_id, model, temp_vision)
            VALUES ($1, $2, $3, $4, FALSE)
            ON CONFLICT (line_session_id) DO UPDATE SET
                opencode_session_id = EXCLUDED.opencode_session_id,
                model = EXCLUDED.model,
                last_used_at = NOW()
            """,
            line_session_id,
            user_id,
            opencode_session_id,
            opencode.DEFAULT_MODEL_STR,
        )
    finally:
        await conn.close()


async def _update_mapping(
    line_session_id: int,
    model: Optional[str] = None,
    temp_vision: Optional[bool] = None,
) -> None:
    if not _DATABASE_URL:
        return
    conn = await asyncpg.connect(_pg_url())
    try:
        sets = ["last_used_at = NOW()"]
        args: list = []
        if model is not None:
            sets.append("model = $1")
            args.append(model)
        if temp_vision is not None:
            sets.append(f"temp_vision = ${len(args) + 1}")
            args.append(temp_vision)
        args.append(line_session_id)
        await conn.execute(
            f"UPDATE line_opencode_sessions SET {', '.join(sets)} "
            "WHERE line_session_id = $" + str(len(args)),
            *args,
        )
    finally:
        await conn.close()


async def _touch_mapping(line_session_id: int) -> None:
    if not _DATABASE_URL:
        return
    conn = await asyncpg.connect(_pg_url())
    try:
        await conn.execute(
            "UPDATE line_opencode_sessions SET last_used_at = NOW() "
            "WHERE line_session_id = $1",
            line_session_id,
        )
    finally:
        await conn.close()


async def _get_display_name(user_id: str) -> Optional[str]:
    if not _DATABASE_URL:
        return None
    conn = await asyncpg.connect(_pg_url())
    try:
        row = await conn.fetchrow(
            "SELECT display_name FROM line_users WHERE user_id = $1", user_id
        )
        return row["display_name"] if row and row["display_name"] else None
    finally:
        await conn.close()


async def chat(
    session_key: str,
    text: str,
    line_session_id: int,
    persona: Optional[str] = None,
    image_path: Optional[str] = None,
    image_mime: Optional[str] = None,
) -> str:
    """把一則訊息送進 LINE 對應的 opencode session，回傳回覆字串。

    - 沒有映射 → 開新 opencode session，title 用 LINE 使用者名稱（方便在 opencode UI 認人）
    - 新 session 的第一則訊息先注入 persona（以系統指令形式，不佔對話），再送 user 的訊息
    """
    mapping = await _get_mapping_row(line_session_id)
    if not mapping:
        if opencode.SESSION_TITLE:
            title = opencode.SESSION_TITLE
        else:
            display_name = await _get_display_name(session_key)
            title = f"LINE:{display_name or session_key}"
        opencode_session_id = await opencode.create_session(title=title)
        await _store_mapping(line_session_id, session_key, opencode_session_id)
        logger.info(
            "created opencode session %s for LINE user %s", opencode_session_id, session_key
        )
        if persona:
            await opencode.send_message(
                opencode_session_id,
                f"（系統指令，不是對話內容，請在之後所有回覆遵守，也不要再複述這段）\n{persona}",
            )
        mapping = {
            "opencode_session_id": opencode_session_id,
            "model": opencode.DEFAULT_MODEL_STR,
            "temp_vision": False,
        }
    else:
        await _touch_mapping(line_session_id)
    opencode_session_id = mapping["opencode_session_id"]

    current = await opencode.get_session_model(opencode_session_id)
    model_str: Optional[str] = None

    if image_path:
        if not (current and opencode.is_vision_model(*current)):
            model_str = opencode.VISION_MODEL
            await _update_mapping(line_session_id, temp_vision=True)
    elif opencode.MODEL:
        model_str = opencode.MODEL
        await _update_mapping(line_session_id, model=model_str, temp_vision=False)
    elif mapping.get("temp_vision") and current and opencode.is_vision_model(*current):
        # 圖片暫時切走之後的第一則文字 → 自動切回原本 model
        base = mapping.get("model")
        if base:
            bp, _, bm = base.partition("/")
            if bp and bm and not opencode.is_vision_model(bp, bm):
                model_str = base
        await _update_mapping(line_session_id, temp_vision=False)
    elif current:
        # 一般文字：把 session 目前的模型同步進 mapping（Desktop 換的模型也會被記住）
        await _update_mapping(line_session_id, model=f"{current[0]}/{current[1]}")

    return await opencode.send_message(
        opencode_session_id, text, image_path, image_mime, model_str
    )
