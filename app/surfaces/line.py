"""LINE Messaging API adapter — M3。

掛在 Chainlit 的 FastAPI app 上的 `/webhook/line`：
- 收 LINE 事件 → 簽章驗證 → 處理 message / follow / unfollow
- message → LiteLLM (走 LITELLM_LINE_KEY 獨立 virtual key) → reply
- follow → 把 userId 存進 PG `line_users`（給 M4 push 用）

push helper `push_to_user()` 預先寫好，等 M4 cron worker 來呼叫。
"""
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
from typing import Optional

import asyncpg
import httpx
from chainlit.server import app as fastapi_app
from fastapi import HTTPException, Request

from app.core.llm import make_llm
from app.settings import (
    LINE_CHANNEL_ACCESS_TOKEN,
    LINE_CHANNEL_SECRET,
    LITELLM_LINE_KEY,
)

logger = logging.getLogger(__name__)

_LINE_API = "https://api.line.me/v2/bot"
_DATABASE_URL = os.getenv("DATABASE_URL", "")


def _pg_url() -> str:
    """SQLAlchemy URL → asyncpg-compatible URL."""
    return _DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


async def ensure_line_table() -> None:
    """啟動時跑：建 line_users 表（沒就建，有就跳過）。"""
    if not _DATABASE_URL:
        logger.warning("DATABASE_URL not set; LINE follow events won't be persisted")
        return
    conn = await asyncpg.connect(_pg_url())
    try:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS line_users (
                user_id       TEXT PRIMARY KEY,
                display_name  TEXT,
                followed_at   TIMESTAMPTZ DEFAULT NOW(),
                unfollowed_at TIMESTAMPTZ,
                metadata      JSONB DEFAULT '{}'::jsonb
            )
            """
        )
    finally:
        await conn.close()


async def _save_follow(user_id: str) -> None:
    if not _DATABASE_URL:
        return
    conn = await asyncpg.connect(_pg_url())
    try:
        await conn.execute(
            """
            INSERT INTO line_users (user_id, followed_at, unfollowed_at)
            VALUES ($1, NOW(), NULL)
            ON CONFLICT (user_id) DO UPDATE SET
                followed_at = NOW(),
                unfollowed_at = NULL
            """,
            user_id,
        )
    finally:
        await conn.close()


async def _mark_unfollow(user_id: str) -> None:
    if not _DATABASE_URL:
        return
    conn = await asyncpg.connect(_pg_url())
    try:
        await conn.execute(
            "UPDATE line_users SET unfollowed_at = NOW() WHERE user_id = $1",
            user_id,
        )
    finally:
        await conn.close()


async def _line_reply(reply_token: str, text: str) -> None:
    if not LINE_CHANNEL_ACCESS_TOKEN:
        logger.warning("LINE access token missing; skipping reply")
        return
    async with httpx.AsyncClient(timeout=10) as cx:
        r = await cx.post(
            f"{_LINE_API}/message/reply",
            headers={"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"},
            json={"replyToken": reply_token, "messages": [{"type": "text", "text": text[:5000]}]},
        )
        if r.status_code >= 400:
            logger.error("LINE reply failed: %s %s", r.status_code, r.text[:200])


async def push_to_user(user_id: str, text: str) -> bool:
    """M4 cron worker 會 import 來用。沒有 access token 就 no-op。"""
    if not LINE_CHANNEL_ACCESS_TOKEN:
        return False
    async with httpx.AsyncClient(timeout=10) as cx:
        r = await cx.post(
            f"{_LINE_API}/message/push",
            headers={"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"},
            json={"to": user_id, "messages": [{"type": "text", "text": text[:5000]}]},
        )
        if r.status_code >= 400:
            logger.error("LINE push failed: %s %s", r.status_code, r.text[:200])
            return False
    return True


def _verify_signature(body: bytes, signature: str) -> bool:
    if not LINE_CHANNEL_SECRET or not signature:
        return False
    expected = base64.b64encode(
        hmac.new(LINE_CHANNEL_SECRET.encode(), body, hashlib.sha256).digest()
    ).decode()
    return hmac.compare_digest(signature, expected)


def _llm_answer_sync(text: str) -> str:
    return make_llm(
        api_key=LITELLM_LINE_KEY or None,  # 帳單算進 line-bot virtual key
        streaming=False,
    ).invoke(text).content


@fastapi_app.post("/webhook/line")
async def line_webhook(req: Request):
    if not LINE_CHANNEL_SECRET:
        raise HTTPException(503, "LINE not configured (LINE_CHANNEL_SECRET missing)")

    body = await req.body()
    signature = req.headers.get("x-line-signature", "")
    if not _verify_signature(body, signature):
        logger.warning("LINE webhook bad signature")
        raise HTTPException(403, "Invalid signature")

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(400, "Bad JSON")

    for event in data.get("events", []):
        await _handle_event(event)

    return {"ok": True}


async def _handle_event(event: dict) -> None:
    evt_type = event.get("type")
    source = event.get("source", {}) or {}
    user_id: Optional[str] = source.get("userId")

    if evt_type == "follow" and user_id:
        await _save_follow(user_id)
        logger.info("LINE follow: %s", user_id)
        return

    if evt_type == "unfollow" and user_id:
        await _mark_unfollow(user_id)
        logger.info("LINE unfollow: %s", user_id)
        return

    if evt_type != "message":
        return

    msg = event.get("message", {}) or {}
    if msg.get("type") != "text":
        return

    text = (msg.get("text") or "").strip()
    reply_token = event.get("replyToken")
    if not text or not reply_token:
        return

    logger.info("LINE message from %s: %r", user_id, text[:80])

    # 順手把 message sender 也 upsert 進 line_users（如果之前 follow 沒抓到）
    if user_id:
        await _save_follow(user_id)

    try:
        answer = (await asyncio.to_thread(_llm_answer_sync, text)).strip()
    except Exception as e:
        logger.exception("LLM call failed for LINE message")
        answer = f"⚠️ 處理失敗，請稍後再試（{type(e).__name__}）"

    await _line_reply(reply_token, answer)
