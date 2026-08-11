"""Discord 語音 surface — Node voice bot 的 HTTP bridge。

Node 端（https://github.com/towNingtek/ai-cat-discord-voice）收使用者語音 →
whisper-1 轉文字 → POST 這裡；這裡把文字送進 opencode session，回傳回覆文字，
Node 端再 TTS 播回。

- `POST /discord-voice/chat`：body `{channel_id, text}` + header `X-Voice-Token`
  （token 防呆，等同 SESSION_SCAN_TOKEN 的做法，避免裸跑）
- 記憶可「共用」LINE 的 ai-cat opencode session（`OPENCODE_SHARED_SESSION_ID`）
  → 跨 surface 連續記憶；空 → 每個語音頻道自建 session
- 頻道 ↔ opencode session 映射存 PG 表 `discord_voice_sessions`

HTTP 細節在 `app/core/opencode.py`；這層只管 Discord 專屬的 session 映射。
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import asyncpg
from chainlit.server import app as fastapi_app
from fastapi import HTTPException, Request

from app.core import opencode

logger = logging.getLogger(__name__)

_DATABASE_URL = os.getenv("DATABASE_URL", "")
_DISCORD_VOICE_TOKEN = os.getenv("DISCORD_VOICE_TOKEN", "").strip()
# Discord 語音要「共用」的 opencode session（例：跟 LINE 的 ai-cat 同一個）。
# 空 → 每個語音頻道自建自己的 session。
_OPENCODE_SHARED_SESSION_ID = os.getenv("OPENCODE_SHARED_SESSION_ID", "").strip()


def _pg_url() -> str:
    return _DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


async def ensure_discord_voice_table() -> None:
    if not _DATABASE_URL:
        return
    conn = await asyncpg.connect(_pg_url())
    try:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS discord_voice_sessions (
                discord_key         TEXT PRIMARY KEY,
                opencode_session_id TEXT NOT NULL,
                created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_used_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    finally:
        await conn.close()


async def _get_session_id(discord_key: str) -> Optional[str]:
    if not _DATABASE_URL:
        return None
    conn = await asyncpg.connect(_pg_url())
    try:
        row = await conn.fetchrow(
            "SELECT opencode_session_id FROM discord_voice_sessions "
            "WHERE discord_key = $1",
            discord_key,
        )
        return row["opencode_session_id"] if row else None
    finally:
        await conn.close()


async def _store_mapping(discord_key: str, opencode_session_id: str) -> None:
    if not _DATABASE_URL:
        return
    conn = await asyncpg.connect(_pg_url())
    try:
        await conn.execute(
            """
            INSERT INTO discord_voice_sessions (discord_key, opencode_session_id)
            VALUES ($1, $2)
            ON CONFLICT (discord_key) DO UPDATE SET
                opencode_session_id = EXCLUDED.opencode_session_id,
                last_used_at = NOW()
            """,
            discord_key,
            opencode_session_id,
        )
    finally:
        await conn.close()


async def _touch_mapping(discord_key: str) -> None:
    if not _DATABASE_URL:
        return
    conn = await asyncpg.connect(_pg_url())
    try:
        await conn.execute(
            "UPDATE discord_voice_sessions SET last_used_at = NOW() "
            "WHERE discord_key = $1",
            discord_key,
        )
    finally:
        await conn.close()


async def chat(discord_key: str, text: str) -> str:
    """Discord 語音文字對話 → 共用 LINE 的 ai-cat session（或自建）。

    text-only：模型跟著 session 走（Desktop 換的模型有效）；
    OPENCODE_MODEL 有設就強制。
    """
    opencode_session_id = await _get_session_id(discord_key)
    if not opencode_session_id:
        opencode_session_id = _OPENCODE_SHARED_SESSION_ID or await opencode.create_session(
            title=opencode.SESSION_TITLE or "ai-cat-voice"
        )
        await _store_mapping(discord_key, opencode_session_id)
        logger.info(
            "created discord-voice opencode session %s for %s", opencode_session_id, discord_key
        )
    else:
        await _touch_mapping(discord_key)
    return await opencode.send_message(
        opencode_session_id, text, model_str=opencode.MODEL or None
    )


@fastapi_app.post("/discord-voice/chat")
async def discord_voice_chat(req: Request):
    if not _DISCORD_VOICE_TOKEN:
        raise HTTPException(503, "Discord voice not configured (DISCORD_VOICE_TOKEN missing)")
    if req.headers.get("x-voice-token", "") != _DISCORD_VOICE_TOKEN:
        raise HTTPException(403, "Invalid token")
    if not opencode.is_enabled():
        raise HTTPException(503, "opencode bridge not configured (OPENCODE_SERVE_BASE missing)")

    try:
        body = await req.json()
    except Exception:  # noqa: BLE001
        raise HTTPException(400, "Bad JSON")

    channel_id = str(body.get("channel_id") or "").strip()
    text = (body.get("text") or "").strip()
    if not channel_id or not text:
        raise HTTPException(400, "channel_id + text required")

    try:
        reply = await chat(f"discord:{channel_id}", text)
    except Exception as e:  # noqa: BLE001
        logger.exception("discord voice chat failed for %s", channel_id)
        reply = f"⚠️ 我這邊暫時遇到問題，再試一次（{type(e).__name__}）"

    return {"reply": reply}
